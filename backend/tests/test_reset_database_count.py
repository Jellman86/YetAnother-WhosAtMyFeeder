"""The reset states the number it will delete, and deletes only that number.

"Delete all history" removes every detection row, hidden ones included. Its
confirmation used the maintenance total, which leaves hidden rows out, so a
database holding one hidden detection was told "0" and lost 1. The count now
comes from the reset's own scope, and the reset refuses to run when the number
it was shown is no longer the number it would delete.
"""

import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import _get_db_path, get_db
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


@pytest.mark.asyncio
async def test_a_detection_recorded_between_the_count_and_the_delete_stops_the_reset(client, monkeypatch):
    """An MQTT handler already running when ingest is paused can still write a row.

    The count and the delete used to be two statements, so a row written between them was
    deleted on a number nobody confirmed. Both now sit in one transaction that holds the
    database's write lock from before the count, so that row either lands first and the count
    refuses the reset, or waits until the reset is over.
    """
    await _add_detection("reset-counted", hidden=False)
    counted = DetectionRepository._count_all_in_transaction

    async def count_then_late_ingest(self) -> int:
        count = await counted(self)
        # A handler that was already past the pause flag writes now, on its own connection.
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            late = sqlite3.connect(_get_db_path(), timeout=0.2)
            try:
                late.execute(
                    "INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,"
                    " frigate_event, camera_name, is_hidden) VALUES ('2026-11-16 07:01:00', 0, 0.9, 'Robin', 'Robin',"
                    " 'reset-late-handler', 'feeder', 0)"
                )
                late.commit()
            finally:
                late.close()
        return count

    monkeypatch.setattr(DetectionRepository, "_count_all_in_transaction", count_then_late_ingest)

    response = await client.delete("/api/backfill/reset", params={"expected_count": 1})

    assert response.status_code == 200, response.text
    # Exactly the one confirmed row went; the late writer was held out by the write lock.
    assert response.json()["deleted_count"] == 1
    assert await _rows() == 0


@pytest.mark.asyncio
async def test_a_mismatch_inside_the_transaction_rolls_back_and_releases_the_lock(client):
    await _add_detection("reset-one", hidden=False)
    await _add_detection("reset-two", hidden=True)

    async with get_db() as db:
        deleted, count = await DetectionRepository(db).delete_all_if_count_is(1)

    assert (deleted, count) == (None, 2)
    assert await _rows() == 2
    # The write lock is released: another writer can proceed at once.
    await _add_detection("reset-after-refusal", hidden=False)
    assert await _rows() == 3


@pytest.mark.asyncio
async def test_the_guarded_delete_removes_everything_when_the_count_holds(client):
    await _add_detection("reset-one", hidden=False)
    await _add_detection("reset-two", hidden=True)

    async with get_db() as db:
        assert await DetectionRepository(db).delete_all_if_count_is(2) == (2, 2)
    assert await _rows() == 0


def test_the_contract_declares_the_refusal_and_its_fresh_count():
    schema = app.openapi()
    refusal = schema["paths"]["/api/backfill/reset"]["delete"]["responses"]["409"]

    name = refusal["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
    detail = schema["components"]["schemas"][name]["properties"]["detail"]
    changed = next(option["$ref"].rsplit("/", 1)[-1] for option in detail["anyOf"] if "$ref" in option)
    fields = schema["components"]["schemas"][changed]["properties"]

    assert fields["code"]["const"] == "reset_count_changed"
    assert fields["detection_count"]["type"] == "integer"
    # A reset already under way is refused with the same status and a sentence.
    assert {"type": "string"} in detail["anyOf"]


@pytest.mark.asyncio
async def test_the_refusal_sent_matches_the_declared_model(client):
    await _add_detection("reset-declared", hidden=False)

    refused = await client.delete("/api/backfill/reset", params={"expected_count": 4})

    assert backfill_router.BackfillResetRefusal.model_validate(refused.json()).detail == (
        backfill_router.BackfillResetCountChanged(detection_count=1)
    )
