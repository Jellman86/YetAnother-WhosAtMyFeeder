from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository
from app.services.timezone_repair_service import TimezoneRepairService


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        yield
    finally:
        await close_db()


async def _insert_detection(event_id: str, detection_time: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                detection_time,
                1,
                0.91,
                "Common Wood-Pigeon",
                "Columba palumbus",
                event_id,
                "front-yard",
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def _fetch_detection_time(detection_id: int) -> str:
    async with get_db() as db:
        cursor = await db.execute("SELECT detection_time FROM detections WHERE id = ?", (detection_id,))
        row = await cursor.fetchone()
        assert row is not None
        return str(row[0])


@pytest.mark.asyncio
async def test_timezone_repair_preview_marks_legacy_local_naive_rows_as_repair_candidates(
    monkeypatch: pytest.MonkeyPatch,
):
    detection_id = await _insert_detection("evt-legacy-local", "2026-04-01 08:15:00")

    async def _fake_get_event_with_error(event_id: str, timeout: float = 10.0):
        assert event_id == "evt-legacy-local"
        return {
            "id": event_id,
            "start_time": datetime(2026, 4, 1, 12, 15, tzinfo=timezone.utc).timestamp(),
        }, None

    service = TimezoneRepairService()
    monkeypatch.setattr(service._frigate_client, "get_event_with_error", _fake_get_event_with_error)

    preview = await service.preview()

    assert preview["summary"]["repair_candidate_count"] == 1
    assert preview["summary"]["missing_frigate_event_count"] == 0
    assert preview["summary"]["unsupported_delta_count"] == 0
    assert preview["summary"]["scanned_count"] == 1

    candidate = preview["candidates"][0]
    assert candidate["status"] == "repair_candidate"
    assert candidate["detection_id"] == detection_id
    assert candidate["frigate_event"] == "evt-legacy-local"
    assert candidate["delta_hours"] == 4
    assert candidate["stored_detection_time"] == "2026-04-01 08:15:00"
    assert candidate["frigate_start_time"] == "2026-04-01T12:15:00Z"
    assert candidate["repaired_detection_time"] == "2026-04-01T12:15:00Z"


@pytest.mark.asyncio
async def test_timezone_repair_preview_marks_missing_frigate_events_without_guessing(
    monkeypatch: pytest.MonkeyPatch,
):
    await _insert_detection("evt-missing", "2026-04-01 08:15:00")

    async def _fake_get_event_with_error(event_id: str, timeout: float = 10.0):
        assert event_id == "evt-missing"
        return None, "event_not_found"

    service = TimezoneRepairService()
    monkeypatch.setattr(service._frigate_client, "get_event_with_error", _fake_get_event_with_error)

    preview = await service.preview()

    assert preview["summary"]["repair_candidate_count"] == 0
    assert preview["summary"]["missing_frigate_event_count"] == 1
    assert preview["candidates"][0]["status"] == "missing_frigate_event"
    assert preview["candidates"][0]["error"] == "event_not_found"
    assert preview["candidates"][0]["repaired_detection_time"] is None


@pytest.mark.asyncio
async def test_timezone_repair_preview_surfaces_transient_frigate_lookup_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    await _insert_detection("evt-timeout", "2026-04-01 08:15:00")

    async def _fake_get_event_with_error(event_id: str, timeout: float = 10.0):
        assert event_id == "evt-timeout"
        return None, "event_timeout"

    service = TimezoneRepairService()
    monkeypatch.setattr(service._frigate_client, "get_event_with_error", _fake_get_event_with_error)

    preview = await service.preview()

    assert preview["summary"]["repair_candidate_count"] == 0
    assert preview["summary"]["missing_frigate_event_count"] == 0
    assert preview["summary"]["lookup_error_count"] == 1
    assert preview["candidates"][0]["status"] == "lookup_error"
    assert preview["candidates"][0]["error"] == "event_timeout"
    assert preview["candidates"][0]["repaired_detection_time"] is None


@pytest.mark.asyncio
async def test_timezone_repair_apply_updates_only_validated_candidates(
    monkeypatch: pytest.MonkeyPatch,
):
    candidate_id = await _insert_detection("evt-repair", "2026-04-01 08:15:00")
    ok_id = await _insert_detection("evt-ok", "2026-04-01 12:15:00")
    unsupported_id = await _insert_detection("evt-unsupported", "2026-04-01 10:45:00")

    async def _fake_get_event_with_error(event_id: str, timeout: float = 10.0):
        if event_id == "evt-repair":
            return {"id": event_id, "start_time": datetime(2026, 4, 1, 12, 15, tzinfo=timezone.utc).timestamp()}, None
        if event_id == "evt-ok":
            return {"id": event_id, "start_time": datetime(2026, 4, 1, 12, 15, tzinfo=timezone.utc).timestamp()}, None
        if event_id == "evt-unsupported":
            return {"id": event_id, "start_time": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc).timestamp()}, None
        raise AssertionError(f"unexpected event_id {event_id}")

    service = TimezoneRepairService()
    monkeypatch.setattr(service._frigate_client, "get_event_with_error", _fake_get_event_with_error)

    result = await service.apply(confirm=True)

    assert result["repaired_count"] == 1
    assert result["skipped_count"] == 2
    assert result["preview"]["summary"]["repair_candidate_count"] == 1
    assert result["preview"]["summary"]["ok_count"] == 1
    assert result["preview"]["summary"]["unsupported_delta_count"] == 1

    assert await _fetch_detection_time(candidate_id) == "2026-04-01 12:15:00"
    assert await _fetch_detection_time(ok_id) == "2026-04-01 12:15:00"
    assert await _fetch_detection_time(unsupported_id) == "2026-04-01 10:45:00"

    async with get_db() as db:
        repo = DetectionRepository(db)
        repaired = await repo.get_by_id(candidate_id)
        assert repaired is not None
        assert repaired.detection_time == datetime(2026, 4, 1, 12, 15, 0)


@pytest.mark.asyncio
async def test_timezone_repair_preview_ignores_rows_outside_legacy_regression_window(
    monkeypatch: pytest.MonkeyPatch,
):
    await _insert_detection("evt-before-regression", "2026-03-30 08:15:00")
    repair_id = await _insert_detection("evt-in-regression", "2026-04-01 08:15:00")

    async def _fake_get_event_with_error(event_id: str, timeout: float = 10.0):
        if event_id == "evt-in-regression":
            return {
                "id": event_id,
                "start_time": datetime(2026, 4, 1, 12, 15, tzinfo=timezone.utc).timestamp(),
            }, None
        raise AssertionError(f"unexpected event_id {event_id}")

    service = TimezoneRepairService()
    monkeypatch.setattr(service._frigate_client, "get_event_with_error", _fake_get_event_with_error)

    preview = await service.preview()

    assert preview["summary"]["scanned_count"] == 1
    assert preview["summary"]["repair_candidate_count"] == 1
    assert [candidate["detection_id"] for candidate in preview["candidates"]] == [repair_id]
