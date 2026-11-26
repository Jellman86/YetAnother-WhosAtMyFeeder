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
from app.utils.tasks import create_background_task, finish_started_operation
from app.services.media_storage_policy import CachedVisit, plan_media_evictions, select_media_evictions
from app.services.garden_media_policy import capture_id_from_eviction_key, eviction_key

log = structlog.get_logger()


class MediaStorageService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

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
        return cache_module.possible_cache_owners(event_id, paths)

    @staticmethod
    def _photo_protection_inventory(files: dict[str, list[Path]]) -> tuple[dict[str, int], set[str]]:
        photo_sizes: dict[str, int] = {}
        manual_selected: set[str] = set()
        for event_id, paths in files.items():
            photo_bytes = 0
            for path in paths:
                if cache_module.is_canonical_snapshot_file(event_id, path):
                    try:
                        photo_bytes += path.stat().st_size
                    except FileNotFoundError:
                        continue
            if photo_bytes:
                photo_sizes[event_id] = photo_bytes
            if cache_module.has_manual_snapshot_selection(event_id):
                manual_selected.add(event_id)
        return photo_sizes, manual_selected

    @staticmethod
    async def _has_cached_media_parent(possible_owners: set[str]) -> bool:
        # A plain read: it holds no SQLite lock once it returns.
        async with get_db() as db:
            return bool(await DetectionRepository(db).list_cached_media_visits(sorted(possible_owners)))

    async def _delete_orphan_visit(self, event_id: str, paths: list[Path]) -> dict[str, int] | None:
        """Delete an orphan's files without holding SQLite's writer lock across disk I/O.

        The caller holds every possible owner's media locks, so no writer can add files meanwhile.
        A parent created after the first check is caught by the second and gets its files back.
        """
        media = cache_module.media_cache
        possible_owners = self._possible_owners(event_id, paths)
        if possible_owners & self._protected_event_ids() or await self._has_cached_media_parent(possible_owners):
            return None
        staged = await media._complete_file_operation(media._stage_visit_deletion_sync, event_id, paths)
        if await self._has_cached_media_parent(possible_owners):
            await media._complete_file_operation(media._restore_staged_deletion_sync, staged)
            return None
        return await media._complete_file_operation(
            media._remove_staged_deletions_sync, [target for _original, target in staged]
        )

    async def _recover_orphaned_media_stats(self, files: dict[str, list[Path]]) -> dict[str, int]:
        """Retry post-delete filesystem cleanup independently of optional cache budgets."""
        media = cache_module.media_cache
        # Files staged by an earlier orphan cleanup were already proved orphaned; finish deleting them.
        staged = await asyncio.to_thread(media._staged_deletions_sync)
        stats = await media._complete_file_operation(media._remove_staged_deletions_sync, staged)
        async with get_db() as db:
            valid_ids = set(await DetectionRepository(db).get_all_frigate_event_ids())
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
                try:
                    deleted = await finish_started_operation(
                        self._delete_orphan_visit(event_id, files[event_id]), name="media_orphan_recovery"
                    )
                    if deleted is None:
                        continue
                    stats["bytes_freed"] += deleted["bytes_freed"]
                    stats["snapshots_deleted"] += deleted["snapshots_deleted"]
                    stats["clips_deleted"] += deleted["clips_deleted"]
                    stats["previews_deleted"] += deleted["previews_deleted"]
                except OSError as exc:
                    log.warning("Orphaned media recovery failed; will retry", event_id=event_id, error=str(exc))
        return stats

    @staticmethod
    async def _return_interrupted_age_cleanup() -> None:
        """A safety net behind the startup step. The caller holds the housekeeping lock, so no age
        cleanup is running and any age-staged file was left by one that was interrupted. Returning
        it before the inventory lets this pass weigh it."""
        await cache_module.media_cache.return_age_staged_files()

    async def recover_orphaned_media(self) -> dict[str, int]:
        """Run locked orphan cleanup with full lifecycle guards for manual cache cleanup."""
        async with cache_module.media_cache.housekeeping_lock:
            await self._return_interrupted_age_cleanup()
            _sizes, files = await asyncio.to_thread(self._inventory)
            return await self._recover_orphaned_media_stats(files)

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
                keep_photo = any(row.get("owner_confirmed") for row in current) or await asyncio.to_thread(
                    cache_module.has_manual_snapshot_selection, event_id
                )
                target_paths = (
                    [path for path in paths if not cache_module.is_canonical_snapshot_file(event_id, path)]
                    if keep_photo
                    else paths
                )
                if not target_paths:
                    await db.rollback()
                    return None
                await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
                await ProcessingJobRepository(db).mark_storage_evicted(FULL_VISIT_PROCESSING_PIPELINE, event_id)
                freed = await cache_module.media_cache._complete_file_operation(
                    cache_module.media_cache._delete_visit_files_sync, event_id, target_paths
                )
                await db.commit()
                return freed
            except BaseException:
                await db.rollback()
                raise

    @classmethod
    async def _garden_visits(cls) -> list[CachedVisit]:
        """Garden's kept media shares the byte budget, oldest first. A per-species maximum counts birds only."""
        from app.services.garden_media_cache import garden_media_cache, kept_bytes_on_disk

        # A kept file that has gone missing frees nothing, so only bytes really on disk are weighed.
        entries = await garden_media_cache.entries()
        on_disk = await asyncio.to_thread(kept_bytes_on_disk, [entry.capture_id for entry in entries])
        return [
            CachedVisit(
                event_id=eviction_key(entry.capture_id),
                species_key=eviction_key(entry.capture_id),
                # Bird detection times read 'YYYY-MM-DD HH:MM:SS'; compare like with like.
                detected_at=entry.observed_at.replace("T", " "),
                bytes_on_disk=on_disk[entry.capture_id],
            )
            for entry in entries
            if on_disk[entry.capture_id] > 0
        ]

    async def _weigh_cached_visits(
        self,
    ) -> tuple[list[CachedVisit], dict[str, list[Path]], dict[str, set[str]], set[str]]:
        """Every cached visit as the limits weigh it now: its files, possible owners and protection."""
        sizes, files = await asyncio.to_thread(self._inventory)
        photo_sizes, manual_selected = await asyncio.to_thread(self._photo_protection_inventory, files)
        owners = {event_id: self._possible_owners(event_id, paths) for event_id, paths in files.items()}
        async with get_db() as db:
            all_rows = await DetectionRepository(db).list_cached_media_visits(
                sorted(set().union(*owners.values())) if owners else []
            )
        visits = [
            CachedVisit(
                event_id=row["event_id"],
                species_key=row["species_key"],
                detected_at=row["detected_at"],
                bytes_on_disk=sizes[row["event_id"]],
                is_favorite=bool(row["is_favorite"]),
                keep_photo=bool(row.get("owner_confirmed")) or (row["event_id"] in manual_selected),
                photo_bytes=photo_sizes.get(row["event_id"], 0),
            )
            for row in all_rows
            if row["event_id"] in sizes
        ]
        visits.extend(await self._garden_visits())
        # In-flight clip/frame commits must finish before their visit can be evicted.
        protected = self._protected_event_ids()
        live_ids = {row["event_id"] for row in all_rows}
        protected.update(
            event_id
            for event_id, possible in owners.items()
            if possible & protected or (possible - {event_id}) & live_ids
        )
        return visits, files, owners, protected

    async def _evict_bird_visit(self, event_id: str, paths: list[Path], possible_owners: set[str]) -> int | None:
        media = cache_module.media_cache
        async with (
            media._snapshot_commit_lock(event_id),
            media._recording_clip_commit_lock(event_id),
            AsyncExitStack() as leases,
        ):
            for owner in sorted({media._media_write_owner(owner) for owner in possible_owners}):
                await leases.enter_async_context(media._media_lifecycle_lock(owner))
            if possible_owners & self._protected_event_ids():
                return None
            return await finish_started_operation(
                self._evict_budget_visit(event_id, paths), name="media_budget_eviction"
            )

    async def enforce_limits(self) -> dict[str, int]:
        from app.services.garden_media_cache import garden_media_cache

        result = {
            "visits_evicted": 0,
            "bytes_freed": 0,
            "orphan_snapshots_deleted": 0,
            "orphan_clips_deleted": 0,
            "orphan_previews_deleted": 0,
        }
        options = settings.media_cache
        async with cache_module.media_cache.housekeeping_lock:
            await self._return_interrupted_age_cleanup()
            _sizes, files = await asyncio.to_thread(self._inventory)
            orphan_stats = await self._recover_orphaned_media_stats(files)
            result["bytes_freed"] += orphan_stats["bytes_freed"]
            result["orphan_snapshots_deleted"] = orphan_stats["snapshots_deleted"]
            result["orphan_clips_deleted"] = orphan_stats["clips_deleted"]
            result["orphan_previews_deleted"] = orphan_stats["previews_deleted"]
            if not (options.per_species_maximum or options.max_size_mb):
                return result
            visits, files, owners, protected = await self._weigh_cached_visits()
            max_bytes = options.max_size_mb * 1024 * 1024
            evictions = select_media_evictions(
                visits,
                per_species_maximum=options.per_species_maximum,
                max_bytes=max_bytes,
                protected_event_ids=protected,
            )
            species_cap_ids = (
                set(
                    plan_media_evictions(
                        visits,
                        per_species_maximum=options.per_species_maximum,
                        max_bytes=0,
                        protected_event_ids=protected,
                    )[0]
                )
                if max_bytes > 0
                else set()
            )
            # Apply the species cap first. Only then is the optional byte-budget work known.
            evictions.sort(key=lambda event_id: event_id not in species_cap_ids)
            attempted: set[str] = set()
            while evictions:
                remaining_bytes = sum(visit.bytes_on_disk for visit in visits)
                garden_sizes = {
                    visit.event_id: visit.bytes_on_disk
                    for visit in visits
                    if capture_id_from_eviction_key(visit.event_id)
                }
                garden_batch: list[str] = []
                garden_batch_bytes = 0

                async def release_garden_batch() -> None:
                    # Garden captures are released together; only the bytes really removed count.
                    nonlocal garden_batch, garden_batch_bytes, remaining_bytes
                    if not garden_batch:
                        return
                    freed_by_capture = await garden_media_cache.evict(garden_batch)
                    garden_batch, garden_batch_bytes = [], 0
                    result["visits_evicted"] += sum(1 for freed in freed_by_capture.values() if freed > 0)
                    result["bytes_freed"] += sum(freed_by_capture.values())
                    remaining_bytes -= sum(freed_by_capture.values())

                for event_id in evictions:
                    if max_bytes > 0 and event_id not in species_cap_ids:
                        if remaining_bytes - garden_batch_bytes <= max_bytes:
                            break
                    attempted.add(event_id)
                    capture_id = capture_id_from_eviction_key(event_id)
                    if capture_id:
                        garden_batch.append(capture_id)
                        garden_batch_bytes += garden_sizes[event_id]
                        continue
                    await release_garden_batch()
                    freed = await self._evict_bird_visit(event_id, files[event_id], owners[event_id])
                    if freed is None:
                        continue
                    result["visits_evicted"] += 1
                    result["bytes_freed"] += freed
                    remaining_bytes -= freed
                await release_garden_batch()
                if max_bytes <= 0 or remaining_bytes <= max_bytes:
                    break
                # A visit protected late, or refused at its final check, freed less than planned.
                # Weigh what is really on disk and plan again from the candidates not yet tried.
                visits, files, owners, protected = await self._weigh_cached_visits()
                species_cap_ids = set()
                evictions = plan_media_evictions(
                    visits, per_species_maximum=0, max_bytes=max_bytes, protected_event_ids=protected | attempted
                )[1]
            if result["visits_evicted"]:
                log.info("Media cache limits enforced", **result)
        return result


media_storage_service = MediaStorageService()
