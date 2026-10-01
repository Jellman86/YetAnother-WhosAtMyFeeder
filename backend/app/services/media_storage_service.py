"""Periodic opt-in cache limits. History and the favourite archive are never evicted."""

import asyncio
from collections import defaultdict
from pathlib import Path

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.services import media_cache as cache_module
from app.utils.tasks import create_background_task
from app.services.media_storage_policy import CachedVisit, select_media_evictions

log = structlog.get_logger()


class MediaStorageService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = create_background_task(self._loop(), name="media_storage_limits")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.enforce_limits()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Media cache limit sweep failed", error=str(exc))
            await asyncio.sleep(300)

    @staticmethod
    def _inventory() -> tuple[dict[str, int], dict[str, list[Path]]]:
        sizes: dict[str, int] = defaultdict(int)
        files: dict[str, list[Path]] = defaultdict(list)
        for directory in (cache_module.SNAPSHOTS_DIR, cache_module.CLIPS_DIR, cache_module.PREVIEWS_DIR):
            for path in directory.iterdir():
                if path.is_file() and path.name.endswith((".jpg", ".mp4", ".json")):
                    try:
                        event_id = cache_module.cache_file_event_id(path)
                        sizes[event_id] += path.stat().st_size
                        files[event_id].append(path)
                    except FileNotFoundError:
                        continue
        return dict(sizes), dict(files)

    async def enforce_limits(self) -> dict[str, int]:
        result = {"visits_evicted": 0, "bytes_freed": 0}
        options = settings.media_cache
        if not options.enabled or not (options.per_species_maximum or options.max_size_mb):
            return result
        async with self._lock:
            from app.services.high_quality_snapshot_service import high_quality_snapshot_service

            async with get_db() as db:
                valid_ids = set(await DetectionRepository(db).get_all_frigate_event_ids())
            orphan_stats = await cache_module.media_cache.cleanup_orphaned_media(
                valid_ids | high_quality_snapshot_service.get_active_event_ids()
            )
            result["bytes_freed"] += orphan_stats["bytes_freed"]
            sizes, files = await asyncio.to_thread(self._inventory)
            async with get_db() as db:
                rows = await DetectionRepository(db).list_cached_media_visits(list(sizes))
            visits = [CachedVisit(**row, bytes_on_disk=sizes[row["event_id"]]) for row in rows]
            from app.services.high_quality_snapshot_service import high_quality_snapshot_service, HQ_PROCESSING_PIPELINE
            from app.services.full_visit_clip_service import full_visit_clip_service, FULL_VISIT_PROCESSING_PIPELINE

            # In-flight clip/frame commits must finish before their visit can be evicted.
            protected = set(high_quality_snapshot_service.get_active_event_ids())
            protected.update(
                str(job["event_id"])
                for job in full_visit_clip_service.get_jobs_snapshot()
                if job.get("status") == "running"
            )
            evictions = select_media_evictions(
                visits,
                per_species_maximum=options.per_species_maximum,
                max_bytes=options.max_size_mb * 1024 * 1024,
                protected_event_ids=protected,
            )
            for event_id in evictions:
                async with cache_module.media_cache._snapshot_commit_lock(event_id):
                    active_clips = {
                        str(job["event_id"])
                        for job in full_visit_clip_service.get_jobs_snapshot()
                        if job.get("status") == "running"
                    }
                    if event_id in high_quality_snapshot_service.get_active_event_ids() | active_clips:
                        continue
                    # Lock DB writers while rechecking favourite protection and removing files.
                    async with get_db() as db:
                        await db.execute("BEGIN IMMEDIATE")
                        try:
                            current = await DetectionRepository(db).list_cached_media_visits([event_id])
                            if not current or current[0]["is_favorite"]:
                                await db.rollback()
                                continue
                            from app.repositories.processing_job_repository import ProcessingJobRepository

                            await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
                            await ProcessingJobRepository(db).mark_storage_evicted(
                                FULL_VISIT_PROCESSING_PIPELINE, event_id
                            )
                            freed = await asyncio.to_thread(
                                cache_module.media_cache._delete_visit_files_sync, event_id, files[event_id]
                            )
                            await db.commit()
                        except BaseException:
                            await db.rollback()
                            raise
                    result["visits_evicted"] += 1
                    result["bytes_freed"] += freed
            if result["visits_evicted"]:
                log.info("Media cache limits enforced", **result)
        return result


media_storage_service = MediaStorageService()
