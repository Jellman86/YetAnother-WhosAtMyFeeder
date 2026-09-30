"""Automatic full-visit work must respect deliberate cache-budget evictions."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta
from io import BytesIO
import os
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
    monkeypatch.setattr(clips.settings.media_cache, "enabled", True)
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
@pytest.mark.parametrize("enabled", [False, True])
async def test_post_commit_cleanup_failure_is_recovered_without_cache_caps(
    budget_visit_history, monkeypatch, failure, enabled
):
    from app.services import frigate_missing_policy as policy

    database, media, _ = budget_visit_history
    monkeypatch.setattr(policy, "media_cache", media)
    monkeypatch.setattr(policy.settings.maintenance, "frigate_missing_behavior", "delete")
    monkeypatch.setattr(policy.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(policy.settings.media_cache, "max_size_mb", 0)
    monkeypatch.setattr(policy.settings.media_cache, "enabled", enabled)
    monkeypatch.setattr(media, "delete_cached_media", AsyncMock(side_effect=failure))
    async with database() as db:
        with pytest.raises(type(failure)):
            await policy.apply_missing_policy(
                repo=DetectionRepository(db),
                frigate_event="budget-old",
                error="missing",
                source="fixture",
                media_kind="snapshot",
            )
        assert await DetectionRepository(db).get_by_frigate_event("budget-old") is None
    assert await media.get_snapshot("budget-old") is not None
    result = await storage.MediaStorageService().enforce_limits()
    assert result["bytes_freed"] > 0
    assert await media.get_snapshot("budget-old") is None
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
    original_delete = media._delete_visit_files_sync

    def check_writer_available(event, paths=None):
        # This real independent writer would fail if cleanup held SQLite's write lock across I/O.
        with closing(sqlite3.connect(os.environ["RF4_DB_PATH"], timeout=0.1)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return original_delete(event, paths)

    # The fixture exposes its isolated path rather than ever touching production.
    async with database() as db:
        file_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    monkeypatch.setenv("RF4_DB_PATH", file_path)
    monkeypatch.setattr(media, "_delete_visit_files_sync", check_writer_available)
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] > 0


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
    original_delete = media._delete_visit_files_sync

    def paused_delete(event, paths=None):
        entered.set()
        assert release.wait(5)
        return original_delete(event, paths)

    monkeypatch.setattr(media, "_delete_visit_files_sync", paused_delete)
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
    original_delete = media._delete_visit_files_sync
    failures = 0

    def fail_once(event, paths=None):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise OSError("fixture unavailable disk")
        return original_delete(event, paths)

    monkeypatch.setattr(media, "_delete_visit_files_sync", fail_once)
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] == 0
    assert await media.get_snapshot("budget-old") is not None
    assert (await storage.MediaStorageService().enforce_limits())["bytes_freed"] > 0
    assert await media.get_snapshot("budget-old") is None


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
