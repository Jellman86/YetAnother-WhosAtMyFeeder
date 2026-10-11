"""Cached or failing heads must not starve an older uncached full-visit clip."""

from contextlib import asynccontextmanager, closing
import asyncio
from datetime import datetime, timedelta, timezone
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import full_visit_clip_service as module


@pytest_asyncio.fixture
async def clip_history(tmp_path, monkeypatch):
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

    monkeypatch.setattr(module, "get_db", database)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with database() as db:
        repo = DetectionRepository(db)
        for index in range(101):
            await repo.create(
                Detection(
                    now - timedelta(minutes=5, seconds=index), 1, 0.9, "Robin", "Robin", f"visit-{index:03}", "camera"
                )
            )
    monkeypatch.setattr(module.settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(module.settings.frigate, "recording_clip_enabled", True)
    monkeypatch.setattr(module.media_cache, "get_recording_clip_duration_seconds", lambda _event_id: None)
    return database


@pytest.mark.asyncio
async def test_cached_hundred_cannot_starve_the_older_clip_even_after_restart(clip_history, monkeypatch):
    database = clip_history
    cached = {f"visit-{index:03}" for index in range(100)}
    monkeypatch.setattr(
        module.media_cache,
        "get_recording_clip_path",
        lambda event_id, **_kwargs: "fixture.mp4" if event_id in cached else None,
    )
    first = module.FullVisitClipService()
    fetch = AsyncMock(return_value=True)
    monkeypatch.setattr(first, "trigger_for_event", fetch)
    assert await first.reconcile_recent_detections() == 0
    fetch.assert_not_awaited()
    restarted = module.FullVisitClipService()
    monkeypatch.setattr(restarted, "trigger_for_event", fetch)
    assert await restarted.reconcile_recent_detections() == 1
    fetch.assert_awaited_once_with("visit-100", "camera", source="reconcile", lang="en")
    assert await restarted.reconcile_recent_detections() == 0
    fetch.assert_awaited_once()
    async with database() as db:
        assert (await (await db.execute("PRAGMA foreign_key_check")).fetchall()) == []


@pytest.mark.asyncio
async def test_failing_hundred_wait_for_retry_without_starving_the_next_clip(clip_history, monkeypatch):
    monkeypatch.setattr(module.media_cache, "get_recording_clip_path", lambda _event_id, **_kwargs: None)
    first = module.FullVisitClipService()
    fail = AsyncMock(return_value=False)
    monkeypatch.setattr(first, "trigger_for_event", fail)
    assert await first.reconcile_recent_detections() == 0
    assert fail.await_count == 100
    restarted = module.FullVisitClipService()
    succeed = AsyncMock(return_value=True)
    monkeypatch.setattr(restarted, "trigger_for_event", succeed)
    assert await restarted.reconcile_recent_detections() == 1
    succeed.assert_awaited_once_with("visit-100", "camera", source="reconcile", lang="en")


@pytest.mark.asyncio
async def test_cancelled_clip_reconciliation_leaves_unfinished_work_retryable(clip_history, monkeypatch):
    monkeypatch.setattr(module.media_cache, "get_recording_clip_path", lambda _event_id, **_kwargs: None)
    service = module.FullVisitClipService()
    monkeypatch.setattr(service, "trigger_for_event", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await service.reconcile_recent_detections()
    async with clip_history() as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM processing_job_state")).fetchone())[0] == 0
        candidates = await DetectionRepository(db).get_recent_full_visit_candidates(
            detected_before=datetime.now(timezone.utc), detected_after=datetime.now(timezone.utc) - timedelta(hours=24)
        )
    assert len(candidates) == 100


@pytest.mark.asyncio
async def test_due_clip_retry_returns_and_finished_state_cascades_with_its_visit(clip_history, monkeypatch):
    monkeypatch.setattr(module.media_cache, "get_recording_clip_path", lambda _event_id, **_kwargs: None)
    service = module.FullVisitClipService()
    monkeypatch.setattr(service, "trigger_for_event", AsyncMock(return_value=False))
    await service.reconcile_recent_detections()
    async with clip_history() as db:
        await db.execute("UPDATE processing_job_state SET retry_after = '2000-01-01' WHERE event_id = 'visit-000'")
        await db.commit()
    succeed = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "trigger_for_event", succeed)
    assert await service.reconcile_recent_detections() == 2
    assert {call.args[0] for call in succeed.await_args_list} == {"visit-000", "visit-100"}
    async with clip_history() as db:
        assert await DetectionRepository(db).delete_by_frigate_event("visit-000")
        assert (
            await (await db.execute("SELECT COUNT(*) FROM processing_job_state WHERE event_id='visit-000'")).fetchone()
        )[0] == 0
        assert (await (await db.execute("PRAGMA foreign_key_check")).fetchall()) == []


@pytest.mark.asyncio
async def test_manual_uploads_cannot_occupy_the_entire_reconciliation_page(clip_history, monkeypatch):
    async with clip_history() as db:
        await db.execute(
            "UPDATE detections SET frigate_event = 'manual_' || frigate_event WHERE frigate_event != 'visit-100'"
        )
        await db.commit()
    monkeypatch.setattr(module.media_cache, "get_recording_clip_path", lambda _event_id, **_kwargs: None)
    service = module.FullVisitClipService()
    fetch = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "trigger_for_event", fetch)
    assert await service.reconcile_recent_detections() == 1
    fetch.assert_awaited_once_with("visit-100", "camera", source="reconcile", lang="en")
