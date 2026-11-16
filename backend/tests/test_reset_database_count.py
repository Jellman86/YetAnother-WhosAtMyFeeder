"""The reset states the number it will delete, and deletes only that number.

"Delete all history" removes every detection row, hidden ones included. Its
confirmation used the maintenance total, which leaves hidden rows out, so a
database holding one hidden detection was told "0" and lost 1. The count now
comes from the reset's own scope, and the reset refuses to run when the number
it was shown is no longer the number it would delete.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository
from app.routers import backfill as backfill_router


@pytest_asyncio.fixture
async def client(monkeypatch):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()
    backfill_router._JOB_TASKS.clear()
    monkeypatch.setattr(backfill_router.auto_video_classifier, "reset_state", AsyncMock())
    monkeypatch.setattr(
        backfill_router.media_cache,
        "clear_all",
        AsyncMock(return_value={"snapshots_deleted": 0, "clips_deleted": 0, "bytes_freed": 0}),
    )
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()


async def _add_detection(event: str, *, hidden: bool) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden
            ) VALUES (?, 0, 0.9, 'Robin', 'Robin', ?, 'feeder', ?)
            """,
            (datetime(2026, 11, 16, 7, 0).isoformat(sep=" "), event, 1 if hidden else 0),
        )
        await db.commit()


async def _rows() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM detections") as cursor:
            return int((await cursor.fetchone())[0])


@pytest.mark.asyncio
async def test_the_count_is_the_resets_own_scope_hidden_detections_included(client):
    await _add_detection("reset-hidden", hidden=True)

    async with get_db() as db:
        visible_total = await DetectionRepository(db).get_count()
    preview = await client.get("/api/backfill/reset/preview")

    assert visible_total == 0, "the maintenance total leaves hidden rows out"
    assert preview.status_code == 200, preview.text
    assert preview.json()["detection_count"] == 1

    response = await client.delete("/api/backfill/reset", params={"expected_count": 1})

    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 1
    assert await _rows() == 0


@pytest.mark.asyncio
async def test_a_detection_that_arrives_after_the_count_stops_the_reset(client):
    await _add_detection("reset-first", hidden=False)
    shown = (await client.get("/api/backfill/reset/preview")).json()["detection_count"]
    assert shown == 1

    # A visit is recorded while "Delete all 1 detection" is still on screen.
    await _add_detection("reset-arrived-late", hidden=False)
    refused = await client.delete("/api/backfill/reset", params={"expected_count": shown})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == {"code": "reset_count_changed", "detection_count": 2}
    assert await _rows() == 2, "a refused reset deletes nothing"
    backfill_router.media_cache.clear_all.assert_not_awaited()

    confirmed = await client.delete("/api/backfill/reset", params={"expected_count": 2})

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["deleted_count"] == 2
    assert await _rows() == 0


@pytest.mark.asyncio
async def test_a_refused_reset_leaves_ingest_running_and_can_be_asked_again(client):
    await _add_detection("reset-only", hidden=False)

    refused = await client.delete("/api/backfill/reset", params={"expected_count": 5})

    assert refused.status_code == 409
    assert backfill_router._RESET_IN_PROGRESS is False
    assert (await client.get("/api/backfill/reset/preview")).json()["detection_count"] == 1


@pytest.mark.asyncio
async def test_a_reset_asked_without_a_number_still_deletes_everything(client):
    await _add_detection("reset-a", hidden=False)
    await _add_detection("reset-b", hidden=True)

    response = await client.delete("/api/backfill/reset")

    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 2
