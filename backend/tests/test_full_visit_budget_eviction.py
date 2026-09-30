"""Automatic full-visit work must respect deliberate cache-budget evictions."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta
from io import BytesIO
import os
import sqlite3
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
