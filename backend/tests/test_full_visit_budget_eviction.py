"""Automatic full-visit work must respect deliberate cache-budget evictions."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta
from io import BytesIO
import os
from pathlib import Path
import sqlite3
import threading
from unittest.mock import AsyncMock

import aiosqlite
from PIL import Image
import pytest
import pytest_asyncio

from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services import full_visit_clip_service as clips
from app.services import high_quality_snapshot_service as photos
from app.services import media_cache as cache
from app.services import media_storage_service as storage


@pytest_asyncio.fixture
async def budget_visit_history(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for name in ("SNAPSHOTS_DIR", "CLIPS_DIR", "PREVIEWS_DIR"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(cache, name, directory)
    media = cache.MediaCacheService()
    service = clips.FullVisitClipService()
    monkeypatch.setattr(cache, "media_cache", media)
    monkeypatch.setattr(clips, "media_cache", media)
    monkeypatch.setattr(clips, "full_visit_clip_service", service)
    monkeypatch.setattr(clips, "get_db", database)
    monkeypatch.setattr(storage, "get_db", database)
    monkeypatch.setattr(clips.settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(clips.settings.frigate, "recording_clip_enabled", True)
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 1)
    monkeypatch.setattr(clips.settings.media_cache, "max_size_mb", 0)
    image = BytesIO()
    Image.new("RGB", (300, 300), "red").save(image, format="JPEG")
    async with database() as db:
        for index, event in enumerate(("budget-old", "budget-new")):
            await DetectionRepository(db).create(
                Detection(
                    datetime.now() - timedelta(minutes=20 - index * 10), 1, 0.9, "Robin", "Robin", event, "camera"
                )
            )
            await media.cache_snapshot(event, image.getvalue())
    monkeypatch.setattr(service, "_wait_until_recording_window_complete", AsyncMock(return_value=1.0))
    return database, media, service


@pytest.mark.asyncio
async def test_budget_eviction_before_first_clip_marker_stops_reconcile_and_late_mqtt(
    budget_visit_history, monkeypatch
):
    database, media, service = budget_visit_history
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 1
    assert await media.get_snapshot("budget-old") is None
    async with database() as db:
        state = await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old")
        assert state is not None and state.status == "terminal" and state.last_error == "storage_evicted"
    fetch = AsyncMock(return_value="complete")
    monkeypatch.setattr(service, "_fetch_once", fetch)
    await service.reconcile_recent_detections()
    assert all(call.args[0] != "budget-old" for call in fetch.await_args_list)
    assert not await service.trigger_for_event("budget-old", source="mqtt_end")
    restarted = clips.FullVisitClipService()
    monkeypatch.setattr(restarted, "_fetch_once", fetch)
    assert not await restarted.trigger_for_event("budget-old", source="mqtt_end")
    assert all(call.args[0] != "budget-old" for call in fetch.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("ready", [False, True])
async def test_late_clip_outcome_does_not_replace_storage_eviction(budget_visit_history, ready):
    database, _, service = budget_visit_history
    await storage.MediaStorageService().enforce_limits()
    await service._record_reconcile_outcome("budget-old", ready=ready)
    async with database() as db:
        state = await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old")
        assert state.status == "terminal" and state.last_error == "storage_evicted"


@pytest.mark.asyncio
async def test_direct_automatic_fetch_is_protected_until_it_finishes(budget_visit_history, monkeypatch):
    database, media, service = budget_visit_history
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(*args, **kwargs):
        entered.set()
        await release.wait()
        return "complete"

    monkeypatch.setattr(service, "_fetch_once", pending)
    task = asyncio.create_task(service.trigger_for_event("budget-old"))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        await storage.MediaStorageService().enforce_limits()
        assert await media.get_snapshot("budget-old") is not None
        async with database() as db:
            state = await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old")
            assert state is None or state.last_error != "storage_evicted"
    finally:
        release.set()
    assert await task
    assert not service.get_jobs_snapshot()
    assert not service._job_timestamps
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 1


@pytest.mark.asyncio
async def test_eviction_winning_during_failure_read_cannot_be_overwritten(budget_visit_history, monkeypatch):
    database, _, service = budget_visit_history
    original_get = ProcessingJobRepository.get
    called = False

    async def racing_read(repo, pipeline, event):
        nonlocal called
        old = await original_get(repo, pipeline, event)
        if not called:
            called = True
            async with database() as db:
                await ProcessingJobRepository(db).mark_storage_evicted(pipeline, event)
                await db.commit()
        return old

    monkeypatch.setattr(ProcessingJobRepository, "get", racing_read)
    await service._record_reconcile_outcome("budget-old", ready=False)
    async with database() as db:
        state = await original_get(ProcessingJobRepository(db), clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old")
        assert state.status == "terminal" and state.last_error == "storage_evicted"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError("fixture disk failure"), asyncio.CancelledError()])
async def test_post_commit_cleanup_failure_is_recovered_without_cache_caps(budget_visit_history, monkeypatch, failure):
    from app.services import frigate_missing_policy as policy

    database, media, _ = budget_visit_history
    monkeypatch.setattr(policy, "media_cache", media)
    monkeypatch.setattr(policy.settings.maintenance, "frigate_missing_behavior", "delete")
    monkeypatch.setattr(policy.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(policy.settings.media_cache, "max_size_mb", 0)
    # A record YA-WAMF holds its own photo for is never deleted, so this one has only a clip.
    assert await media.delete_snapshot("budget-old")
    assert await media.cache_clip("budget-old", b"\x00\x00\x00\x18ftypmp42" + b"v" * 4096)
    monkeypatch.setattr(media, "delete_cached_media", AsyncMock(side_effect=failure))
    async with database() as db:
        with pytest.raises(type(failure)):
            await policy.apply_missing_policy(
                repo=DetectionRepository(db),
                frigate_event="budget-old",
                error="missing",
                source="fixture",
                media_kind="clip",
            )
        assert await DetectionRepository(db).get_by_frigate_event("budget-old") is None
    assert media.get_clip_path("budget-old") is not None
    result = await storage.MediaStorageService().enforce_limits()
    assert result["bytes_freed"] > 0
    assert media.get_clip_path("budget-old") is None
    assert await media.get_snapshot("budget-new") is not None
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] == 0


@pytest.mark.asyncio
async def test_orphan_recovery_and_immediate_delete_preserve_an_active_clip_stream(budget_visit_history, monkeypatch):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(clips.settings.media_cache, "max_size_mb", 0)
    entered, release = asyncio.Event(), asyncio.Event()

    async def chunks():
        yield b"one" * 1024
        entered.set()
        await release.wait()
        yield b"two" * 1024

    task = asyncio.create_task(media.cache_clip_streaming("budget-old", chunks()))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        async with database() as db:
            await DetectionRepository(db).delete_by_frigate_event("budget-old")
        await media.delete_cached_media("budget-old")
        await storage.MediaStorageService().enforce_limits()
        assert await media.get_snapshot("budget-old") is not None
        assert media._clip_path("budget-old").exists()
    finally:
        release.set()
    assert await task is not None
    await storage.MediaStorageService().enforce_limits()
    assert await media.get_snapshot("budget-old") is None
    assert not media._clip_path("budget-old").exists()


@pytest.mark.asyncio
async def test_orphan_cleanup_rechecks_a_parent_created_after_inventory_and_holds_no_db_writer(
    budget_visit_history, monkeypatch
):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(clips.settings.media_cache, "max_size_mb", 0)
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
    original_ids = DetectionRepository.get_all_frigate_event_ids
    restored = False

    async def restore_after_first_read(repo):
        nonlocal restored
        ids = await original_ids(repo)
        if not restored:
            restored = True
            async with database() as db:
                await DetectionRepository(db).create(
                    Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "budget-old", "camera")
                )
        return ids

    monkeypatch.setattr(DetectionRepository, "get_all_frigate_event_ids", restore_after_first_read)
    await storage.MediaStorageService().enforce_limits()
    assert restored
    assert await media.get_snapshot("budget-old") is not None
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    original_unlink = Path.unlink
    inserted_during_unlink = False

    def create_parent_during_unlink(path, *args, **kwargs):
        nonlocal inserted_during_unlink
        if path.is_relative_to(cache.SNAPSHOTS_DIR) and not inserted_during_unlink:
            with closing(sqlite3.connect(file_path, timeout=0.1)) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO detections (detection_time,detection_index,score,category_name,display_name,"
                    "frigate_event,camera_name) VALUES (datetime('now'),1,0.9,'Robin','Robin','budget-old','camera')"
                )
                db.commit()
            inserted_during_unlink = True
            assert not (cache.SNAPSHOTS_DIR / "budget-old.jpg").exists()
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", create_parent_during_unlink)
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] > 0
    assert inserted_during_unlink
    async with database() as db:
        assert await DetectionRepository(db).get_by_frigate_event("budget-old") is not None
    assert await media.get_snapshot("budget-old") is None


@pytest.mark.asyncio
async def test_orphan_files_return_when_their_parent_appears_while_they_are_staged(budget_visit_history, monkeypatch):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(clips.settings.media_cache, "max_size_mb", 0)
    photo = await media.get_snapshot("budget-old")
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    original_stage = media._stage_visit_deletion_sync

    def create_parent_then_stage(event_id, paths):
        with closing(sqlite3.connect(file_path, timeout=0.1)) as db:
            db.execute(
                "INSERT INTO detections (detection_time,detection_index,score,category_name,display_name,"
                "frigate_event,camera_name) VALUES (datetime('now'),1,0.9,'Robin','Robin','budget-old','camera')"
            )
            db.commit()
        return original_stage(event_id, paths)

    monkeypatch.setattr(media, "_stage_visit_deletion_sync", create_parent_then_stage)
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] == 0
    assert await media.get_snapshot("budget-old") == photo
    assert media._staged_deletions_sync() == []


async def _age_cache_files(days: int) -> None:
    aged = (datetime.now() - timedelta(days=days)).timestamp()
    for directory in (cache.SNAPSHOTS_DIR, cache.CLIPS_DIR, cache.PREVIEWS_DIR):
        for path in directory.iterdir():
            os.utime(path, (aged, aged))


@pytest.mark.asyncio
async def test_age_cleanup_holds_no_database_writer_while_it_unlinks(budget_visit_history, monkeypatch):
    import app.database as db_module

    database, media, _ = budget_visit_history
    monkeypatch.setattr(db_module, "get_db", database)
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    await _age_cache_files(10)
    original_unlink = Path.unlink
    writes_during_unlink: list[str] = []

    def write_during_unlink(path, *args, **kwargs):
        if path.is_relative_to(cache.SNAPSHOTS_DIR) and not writes_during_unlink:
            # A real independent writer, as ingest is, fails here if cleanup holds the writer lock.
            with closing(sqlite3.connect(file_path, timeout=0.1)) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO detections (detection_time,detection_index,score,category_name,display_name,"
                    "frigate_event,camera_name) VALUES (datetime('now'),1,0.9,'Robin','Robin','age-ingest','camera')"
                )
                db.commit()
            writes_during_unlink.append(path.name)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", write_during_unlink)
    stats = await media.cleanup_old_media(1)
    assert writes_during_unlink
    assert stats["snapshots_deleted"] >= 2
    assert await media.get_snapshot("budget-old") is None
    async with database() as db:
        assert await DetectionRepository(db).get_by_frigate_event("age-ingest") is not None
        state = await ProcessingJobRepository(db).get(photos.HQ_PROCESSING_PIPELINE, "budget-old")
    assert state is not None and state.last_error == "storage_evicted"


@pytest.mark.asyncio
async def test_age_cleanup_returns_files_favourited_while_they_are_staged(budget_visit_history, monkeypatch):
    import app.database as db_module

    database, media, _ = budget_visit_history
    monkeypatch.setattr(db_module, "get_db", database)
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    photo = await media.get_snapshot("budget-old")
    await _age_cache_files(10)
    original_stage = media._stage_paths_sync

    def favourite_then_stage(paths, *args):
        with closing(sqlite3.connect(file_path, timeout=0.1)) as db:
            db.execute(
                "INSERT OR IGNORE INTO detection_favorites(detection_id,created_by) "
                "SELECT id,'owner' FROM detections WHERE frigate_event='budget-old'"
            )
            db.commit()
        return original_stage(paths, *args)

    monkeypatch.setattr(media, "_stage_paths_sync", favourite_then_stage)
    await media.cleanup_old_media(1)
    assert await media.get_snapshot("budget-old") == photo
    assert media._staged_deletions_sync() == []
    async with database() as db:
        assert await ProcessingJobRepository(db).get(photos.HQ_PROCESSING_PIPELINE, "budget-old") is None


@pytest.mark.asyncio
async def test_age_cleanup_returns_the_main_photo_of_a_capture_confirmed_while_staged(
    budget_visit_history, monkeypatch
):
    import app.database as db_module

    database, media, _ = budget_visit_history
    monkeypatch.setattr(db_module, "get_db", database)
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    photo = await media.get_snapshot("budget-old")
    await _age_cache_files(10)
    original_stage = media._stage_paths_sync

    def confirm_then_stage(paths, *args):
        with closing(sqlite3.connect(file_path, timeout=0.1)) as db:
            db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = 'budget-old'")
            db.commit()
        return original_stage(paths, *args)

    monkeypatch.setattr(media, "_stage_paths_sync", confirm_then_stage)
    await media.cleanup_old_media(1)
    assert await media.get_snapshot("budget-old") == photo
    assert await media.get_snapshot("budget-new") is None
    assert media._staged_deletions_sync() == []


class _ObservedLock(asyncio.Lock):
    """A lock that says when a second caller has to wait for it."""

    def __init__(self) -> None:
        super().__init__()
        self.contended = asyncio.Event()

    async def acquire(self) -> bool:
        if self.locked():
            self.contended.set()
        return await super().acquire()


def _owner_acts(file_path: str, change: str) -> None:
    with closing(sqlite3.connect(file_path, timeout=1)) as db:
        if change == "favourite":
            db.execute(
                "INSERT OR IGNORE INTO detection_favorites(detection_id,created_by) "
                "SELECT id,'owner' FROM detections WHERE frigate_event='budget-old'"
            )
        else:
            db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = 'budget-old'")
        db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["favourite", "confirm"])
async def test_a_storage_sweep_during_age_cleanup_never_deletes_files_it_gives_back(
    budget_visit_history, monkeypatch, change
):
    import app.database as db_module

    database, media, _ = budget_visit_history
    monkeypatch.setattr(db_module, "get_db", database)
    monkeypatch.setattr(storage.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    photo = await media.get_snapshot("budget-old")
    await _age_cache_files(10)
    housekeeping = _ObservedLock()
    monkeypatch.setattr(media, "housekeeping_lock", housekeeping, raising=False)
    sweeps: list[asyncio.Task] = []
    original_settle = media._settle_staged_age_group

    async def settle_while_a_sweep_runs(kind, event_id, owners, staged):
        if event_id == "budget-old" and not sweeps:
            # The owner acts after the first read, and the five-minute sweep starts meanwhile.
            await asyncio.to_thread(_owner_acts, file_path, change)
            sweep = asyncio.create_task(storage.MediaStorageService().enforce_limits())
            sweeps.append(sweep)
            contended = asyncio.create_task(housekeeping.contended.wait())
            # Either the sweep runs to the end now, or it waits for age cleanup to finish.
            await asyncio.wait({sweep, contended}, return_when=asyncio.FIRST_COMPLETED)
            contended.cancel()
        return await original_settle(kind, event_id, owners, staged)

    monkeypatch.setattr(media, "_settle_staged_age_group", settle_while_a_sweep_runs)
    await media.cleanup_old_media(1)
    sweep_result = await sweeps[0]
    assert await media.get_snapshot("budget-old") == photo
    # A capture with a row is never counted as an orphan.
    assert sweep_result["orphan_snapshots_deleted"] == 0
    assert media._staged_deletions_sync() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["favourite", "confirm"])
async def test_files_staged_by_age_cleanup_before_a_crash_come_back_on_the_next_sweep(
    budget_visit_history, monkeypatch, change
):
    import app.database as db_module

    database, media, _ = budget_visit_history
    monkeypatch.setattr(db_module, "get_db", database)
    monkeypatch.setattr(storage.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    photo = await media.get_snapshot("budget-old")
    await _age_cache_files(10)

    class ProcessDied(BaseException):
        pass

    with monkeypatch.context() as crash:
        # A process that dies after staging restores nothing and finishes nothing.
        crash.setattr(media, "_settle_staged_age_group", AsyncMock(side_effect=ProcessDied()))
        crash.setattr(media, "_restore_staged_deletion_sync", lambda staged: None)
        with pytest.raises(ProcessDied):
            await media.cleanup_old_media(1)
    assert await media.get_snapshot("budget-old") is None

    await asyncio.to_thread(_owner_acts, file_path, change)
    restarted = storage.MediaStorageService()
    result = await restarted.enforce_limits()
    assert result["orphan_snapshots_deleted"] == 0
    assert await media.get_snapshot("budget-old") == photo
    # The next age cleanup judges the returned files again, with every check.
    await media.cleanup_old_media(1)
    assert await media.get_snapshot("budget-old") == photo


@pytest.mark.asyncio
async def test_temporary_recording_candidates_are_never_orphan_eviction_inventory(budget_visit_history, monkeypatch):
    _, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    candidate = cache.CLIPS_DIR / ".budget-old.fixture.tmp.mp4"
    candidate.write_bytes(b"unfinished recording")
    await storage.MediaStorageService().enforce_limits()
    assert candidate.exists()


@pytest.mark.asyncio
async def test_cancelled_orphan_sweep_waits_for_disk_deletion_before_releasing_writers(
    budget_visit_history, monkeypatch
):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
    entered, release = threading.Event(), threading.Event()
    original_unlink = Path.unlink

    def paused_unlink(path, *args, **kwargs):
        if path.is_relative_to(cache.SNAPSHOTS_DIR):
            entered.set()
            assert release.wait(5)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", paused_unlink)
    sweep = asyncio.create_task(storage.MediaStorageService().enforce_limits())
    assert await asyncio.to_thread(entered.wait, 2)
    sweep.cancel()
    image = BytesIO()
    Image.new("RGB", (300, 300), "blue").save(image, format="JPEG")
    writer = asyncio.create_task(media.cache_snapshot("budget-old", image.getvalue()))
    try:
        await asyncio.wait({writer}, timeout=0.05)
        assert not writer.done()
        sweep.cancel()  # Repeated cancellation must not release the still-running deletion.
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await sweep
    assert await writer is not None
    assert await media.get_snapshot("budget-old") == image.getvalue()
    assert media.get_active_write_event_ids() == set()


@pytest.mark.asyncio
async def test_orphan_disk_failure_is_retried_on_the_next_sweep(budget_visit_history, monkeypatch):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
    original_unlink = Path.unlink
    failures: list[Path] = []

    def fail_media_unlink(path, *args, **kwargs):
        if path.is_relative_to(cache.SNAPSHOTS_DIR):
            failures.append(path)
            raise OSError("fixture unavailable disk")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as disk:
        disk.setattr(Path, "unlink", fail_media_unlink)
        assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] == 0
    assert await media.get_snapshot("budget-old") is None
    assert failures and all(path.exists() for path in failures)

    # A new parent and photo at the original path must be safe while a fresh
    # service drains the previous sweep's staged files.
    async with database() as db:
        await DetectionRepository(db).create(
            Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "budget-old", "camera")
        )
    photo = await media.get_snapshot("budget-new")
    assert await media.cache_snapshot("budget-old", photo)
    recovered = await storage.MediaStorageService().recover_orphaned_media()
    assert recovered["bytes_freed"] > 0
    assert recovered["snapshots_deleted"] == 1
    assert all(not path.exists() for path in failures)
    assert await media.get_snapshot("budget-old") == photo


@pytest.mark.asyncio
async def test_cancelled_clip_writer_releases_its_lifecycle_lease(budget_visit_history):
    _, media, _ = budget_visit_history
    entered = asyncio.Event()

    async def chunks():
        yield b"one" * 1024
        entered.set()
        await asyncio.Future()

    task = asyncio.create_task(media.cache_clip_streaming("budget-old", chunks()))
    await asyncio.wait_for(entered.wait(), 2)
    assert media.get_active_write_event_ids() == {"budget-old"}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert media.get_active_write_event_ids() == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["live_recording", "live_thumb", "live_preview"])
async def test_mandatory_recovery_preserves_live_raw_clip_ids_with_variant_suffixes(
    budget_visit_history, monkeypatch, event
):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        await DetectionRepository(db).create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", event, "camera"))
    path = await media.cache_clip(event, b"fixture-clip" * 100)
    assert path is not None
    await storage.MediaStorageService().enforce_limits()
    assert path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["stream_recording", "stream_thumb", "stream_preview"])
async def test_orphan_recovery_protects_active_raw_variant_suffix_streams_after_parent_delete(
    budget_visit_history, monkeypatch, event
):
    database, media, _ = budget_visit_history
    monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
    async with database() as db:
        await DetectionRepository(db).create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", event, "camera"))
    entered, release = asyncio.Event(), asyncio.Event()

    async def chunks():
        yield b"one" * 1024
        entered.set()
        await release.wait()
        yield b"two" * 1024

    writer = asyncio.create_task(media.cache_clip_streaming(event, chunks()))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        async with database() as db:
            await DetectionRepository(db).delete_by_frigate_event(event)
        await storage.MediaStorageService().enforce_limits()
        assert media._clip_path(event).exists()
    finally:
        release.set()
    assert await writer is not None
    await storage.MediaStorageService().enforce_limits()
    assert not media._clip_path(event).exists()
