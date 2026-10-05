"""Periodic orphan recovery and optional cache limits; history and favourite archives remain."""

import asyncio
from contextlib import AsyncExitStack
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
            if not directory.exists():
                continue
            for path in directory.iterdir():
                temporary = path.name.endswith(".tmp") or path.name.startswith(".")
                if not temporary and path.is_file() and path.name.endswith((".jpg", ".mp4", ".json")):
                    try:
                        event_id = cache_module.cache_file_event_id(path)
                        sizes[event_id] += path.stat().st_size
                        files[event_id].append(path)
                    except FileNotFoundError:
                        continue
        return dict(sizes), dict(files)

    @staticmethod
    def _protected_event_ids() -> set[str]:
        from app.services.high_quality_snapshot_service import high_quality_snapshot_service
        from app.services.full_visit_clip_service import full_visit_clip_service

        protected = (
            high_quality_snapshot_service.get_active_event_ids() | cache_module.media_cache.get_active_write_event_ids()
        )
        protected.update(
            str(job["event_id"])
            for job in full_visit_clip_service.get_jobs_snapshot()
            if job.get("status") == "running"
        )
        return protected

    @staticmethod
    def _possible_owners(event_id: str, paths: list[Path]) -> set[str]:
        """A generated variant name may also be a supported literal visit ID."""
        owners = {event_id}
        for path in paths:
            for suffix in (".jpg.meta.json", ".mp4.meta.json", ".jpg", ".mp4", ".json"):
                if path.name.endswith(suffix):
                    stem = path.name[: -len(suffix)]
                    owners.add(stem)
                    # A literal candidate visit may have only its generated thumbnail.
                    # Preserve the intermediate ID before canonicalizing candidate keys.
                    for variant in ("_thumb", "_recording", "_preview"):
                        if stem.endswith(variant):
                            owners.add(stem[: -len(variant)])
                            break
                    break
        owners.update(cache_module.media_cache._media_write_owner(owner) for owner in tuple(owners))
        return owners

    async def _recover_orphaned_media(self, files: dict[str, list[Path]]) -> int:
        """Retry post-delete filesystem cleanup independently of optional cache budgets."""
        async with get_db() as db:
            valid_ids = set(await DetectionRepository(db).get_all_frigate_event_ids())
        freed = 0
        media = cache_module.media_cache
        for event_id in files.keys() - valid_ids - self._protected_event_ids():
            # A legacy variant suffix can also be part of a literal event ID.
            # Keep ambiguous files while any possible parent still exists.
            possible_owners = self._possible_owners(event_id, files[event_id])
            if possible_owners & (valid_ids | self._protected_event_ids()):
                continue
            async with (
                media._snapshot_commit_lock(event_id),
                media._recording_clip_commit_lock(event_id),
                AsyncExitStack() as leases,
            ):
                # Protect raw IDs as well as variant interpretations. Canonicalize
                # and sort once so aliases neither acquire the same lock twice nor
                # allow a new alias writer to enter while deletion is in progress.
                owners = {media._media_write_owner(owner) for owner in possible_owners}
                for owner in sorted(owners):
                    await leases.enter_async_context(media._media_lifecycle_lock(owner))
                if possible_owners & self._protected_event_ids():
                    continue
                # Recheck births after inventory and release the connection before disk I/O.
                async with get_db() as db:
                    placeholders = ",".join("?" for _ in possible_owners)
                    async with db.execute(
                        f"SELECT 1 FROM detections WHERE frigate_event IN ({placeholders}) LIMIT 1",
                        tuple(possible_owners),
                    ) as cursor:
                        if await cursor.fetchone():
                            continue
                try:
                    freed += await media._complete_file_operation(
                        media._delete_visit_files_sync, event_id, files[event_id]
                    )
                except OSError as exc:
                    log.warning("Orphaned media recovery failed; will retry", event_id=event_id, error=str(exc))
        return freed

    async def _evict_budget_visit(self, event_id: str, paths: list[Path]) -> int | None:
        from app.repositories.processing_job_repository import ProcessingJobRepository
        from app.services.high_quality_snapshot_service import HQ_PROCESSING_PIPELINE
        from app.services.full_visit_clip_service import FULL_VISIT_PROCESSING_PIPELINE

        # This transaction belongs to the admitted operation, not its cancelled caller.
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                possible_owners = self._possible_owners(event_id, paths)
                current = await DetectionRepository(db).list_cached_media_visits(sorted(possible_owners))
                # Reserve the final DB decision for every possible parent, including
                # a newly inserted literal suffix owner. Ambiguity cannot destroy it.
                if (
                    not current
                    or any(row["event_id"] != event_id or row["is_favorite"] for row in current)
                    or possible_owners & self._protected_event_ids()
                ):
                    await db.rollback()
                    return None
                await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
                await ProcessingJobRepository(db).mark_storage_evicted(FULL_VISIT_PROCESSING_PIPELINE, event_id)
                freed = await cache_module.media_cache._complete_file_operation(
                    cache_module.media_cache._delete_visit_files_sync, event_id, paths
                )
                await db.commit()
                return freed
            except BaseException:
                await db.rollback()
                raise

    async def _finish_budget_eviction(self, event_id: str, paths: list[Path]) -> int | None:
        """Hold lifecycle locks until irreversible deletion and its durable commit finish."""
        task = asyncio.create_task(self._evict_budget_visit(event_id, paths), name="media_budget_eviction")
        cancellation = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancellation = exc
            except BaseException:
                break
        if cancellation is not None:
            if not task.cancelled():
                task.exception()
            raise cancellation
        return task.result()

    async def enforce_limits(self) -> dict[str, int]:
        result = {"visits_evicted": 0, "bytes_freed": 0}
        options = settings.media_cache
        async with self._lock:
            sizes, files = await asyncio.to_thread(self._inventory)
            result["bytes_freed"] += await self._recover_orphaned_media(files)
            if not (options.per_species_maximum or options.max_size_mb):
                return result
            sizes, files = await asyncio.to_thread(self._inventory)
            owners = {event_id: self._possible_owners(event_id, paths) for event_id, paths in files.items()}
            async with get_db() as db:
                all_rows = await DetectionRepository(db).list_cached_media_visits(
                    sorted(set().union(*owners.values())) if owners else []
                )
            rows = [row for row in all_rows if row["event_id"] in sizes]
            visits = [CachedVisit(**row, bytes_on_disk=sizes[row["event_id"]]) for row in rows]
            # In-flight clip/frame commits must finish before their visit can be evicted.
            protected = self._protected_event_ids()
            live_ids = {row["event_id"] for row in all_rows}
            protected.update(
                event_id
                for event_id, possible in owners.items()
                if possible & protected or (possible - {event_id}) & live_ids
            )
            evictions = select_media_evictions(
                visits,
                per_species_maximum=options.per_species_maximum,
                max_bytes=options.max_size_mb * 1024 * 1024,
                protected_event_ids=protected,
            )
            for event_id in evictions:
                async with (
                    cache_module.media_cache._snapshot_commit_lock(event_id),
                    cache_module.media_cache._recording_clip_commit_lock(event_id),
                    AsyncExitStack() as leases,
                ):
                    write_owners = {cache_module.media_cache._media_write_owner(owner) for owner in owners[event_id]}
                    for owner in sorted(write_owners):
                        await leases.enter_async_context(cache_module.media_cache._media_lifecycle_lock(owner))
                    if owners[event_id] & self._protected_event_ids():
                        continue
                    freed = await self._finish_budget_eviction(event_id, files[event_id])
                    if freed is None:
                        continue
                    result["visits_evicted"] += 1
                    result["bytes_freed"] += freed
            if result["visits_evicted"]:
                log.info("Media cache limits enforced", **result)
        return result


media_storage_service = MediaStorageService()
