"""Once budget files are deleted, cancellation cannot undo durable admission guards."""

import asyncio
import sqlite3
import threading
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services import full_visit_clip_service as clips
from app.services import high_quality_snapshot_service as photos
from app.services import media_storage_service as storage
from test_full_visit_budget_eviction import budget_visit_history as budget_visit_history


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["delete", "commit"])
async def test_cancelled_budget_eviction_completes_files_and_durable_markers(budget_visit_history, monkeypatch, phase):
    database, media, _ = budget_visit_history
    entered, release = asyncio.Event(), asyncio.Event()
    disk_entered, disk_release = threading.Event(), threading.Event()
    if phase == "delete":
        original_delete = media._delete_visit_files_sync

        def paused_delete(event, paths=None):
            disk_entered.set()
            assert disk_release.wait(5)
            return original_delete(event, paths)

        monkeypatch.setattr(media, "_delete_visit_files_sync", paused_delete)
    else:
        original_commit = aiosqlite.Connection.commit

        async def paused_commit(db):
            if db.in_transaction:
                entered.set()
                await release.wait()
            await original_commit(db)

        monkeypatch.setattr(aiosqlite.Connection, "commit", paused_commit)
    sweep = asyncio.create_task(storage.MediaStorageService().enforce_limits())
    try:
        if phase == "delete":
            assert await asyncio.to_thread(disk_entered.wait, 2)
        else:
            await asyncio.wait_for(entered.wait(), 2)
        sweep.cancel()
        await asyncio.sleep(0)
        sweep.cancel()
        await asyncio.sleep(0)
    finally:
        release.set()
        disk_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(sweep, 2)
    assert await media.get_snapshot("budget-old") is None
    async with database() as db:
        for pipeline in (photos.HQ_PROCESSING_PIPELINE, clips.FULL_VISIT_PROCESSING_PIPELINE):
            state = await ProcessingJobRepository(db).get(pipeline, "budget-old")
            assert state is not None and state.status == "terminal" and state.last_error == "storage_evicted"
    restarted = clips.FullVisitClipService()
    fetch = AsyncMock(return_value="complete")
    monkeypatch.setattr(restarted, "_fetch_once", fetch)
    assert not await restarted.trigger_for_event("budget-old")
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_budget_final_favourite_guard_preserves_real_files(budget_visit_history, monkeypatch):
    database, media, _ = budget_visit_history
    async with database() as db:
        path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    original_select = storage.select_media_evictions

    def favourite_after_selection(*args, **kwargs):
        result = original_select(*args, **kwargs)
        with sqlite3.connect(path) as db:
            db.execute(
                "INSERT INTO detection_favorites(detection_id,created_by) "
                "SELECT id,'owner' FROM detections WHERE frigate_event='budget-old'"
            )
        return result

    monkeypatch.setattr(storage, "select_media_evictions", favourite_after_selection)
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 0
    assert await media.get_snapshot("budget-old") is not None
    async with database() as db:
        assert await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old") is None


@pytest.mark.asyncio
async def test_budget_disk_failure_before_deletion_rolls_back_markers(budget_visit_history, monkeypatch):
    database, media, _ = budget_visit_history

    def unavailable_disk(*args):
        raise OSError("fixture disk unavailable before mutation")

    monkeypatch.setattr(media, "_delete_visit_files_sync", unavailable_disk)
    with pytest.raises(OSError):
        await storage.MediaStorageService().enforce_limits()
    assert await media.get_snapshot("budget-old") is not None
    async with database() as db:
        assert await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old") is None
