from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, Detection
from app.routers import settings as settings_router
from app.services.error_diagnostics import error_diagnostics_history


@pytest.fixture(autouse=True)
def reset_missing_policy_settings():
    original_clips_enabled = settings.frigate.clips_enabled
    original_behavior = getattr(settings.maintenance, "frigate_missing_behavior", "mark_missing")
    yield
    settings.frigate.clips_enabled = original_clips_enabled
    settings.maintenance.frigate_missing_behavior = original_behavior


@pytest_asyncio.fixture(autouse=True)
async def clear_detections_table():
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.delete_all()
    yield
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.delete_all()


async def _insert_detection(event_id: str) -> None:
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=settings_router.utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="Bird",
                category_name="Bird",
                frigate_event=event_id,
                camera_name="cam_1",
            )
        )


@pytest.mark.asyncio
async def test_purge_missing_media_marks_detection_when_behavior_is_mark_missing():
    settings.frigate.clips_enabled = True
    settings.maintenance.frigate_missing_behavior = "mark_missing"
    error_diagnostics_history.clear()
    await _insert_detection("evt-purge-mark")

    with patch.object(settings_router.frigate_client, "get_version", new=AsyncMock(return_value="0.17.1")), \
         patch.object(settings_router.frigate_client, "get_event_with_error", new=AsyncMock(return_value=(None, "event_not_found"))), \
         patch.object(settings_router.media_cache, "delete_cached_media", new=AsyncMock()) as delete_cached_media:
        result = await settings_router._purge_missing_media("clip")

    assert result["status"] == "completed"
    assert result["deleted_count"] == 0
    assert result["marked_missing_count"] == 1
    delete_cached_media.assert_not_awaited()

    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event("evt-purge-mark")

    assert detection is not None
    assert detection.frigate_status == "missing"
    assert detection.frigate_last_error == "event_not_found"
    history = error_diagnostics_history.snapshot(limit=10)
    assert any(
        event.get("reason_code") == "frigate_missing_marked"
        and event.get("event_id") == "evt-purge-mark"
        for event in history["events"]
    )


@pytest.mark.asyncio
async def test_purge_missing_media_deletes_detection_when_behavior_is_delete():
    settings.frigate.clips_enabled = True
    settings.maintenance.frigate_missing_behavior = "delete"
    error_diagnostics_history.clear()
    await _insert_detection("evt-purge-delete")

    with patch.object(settings_router.frigate_client, "get_version", new=AsyncMock(return_value="0.17.1")), \
         patch.object(settings_router.frigate_client, "get_event_with_error", new=AsyncMock(return_value=(None, "event_not_found"))), \
         patch.object(settings_router.media_cache, "delete_cached_media", new=AsyncMock()) as delete_cached_media:
        result = await settings_router._purge_missing_media("clip")

    assert result["status"] == "completed"
    assert result["deleted_count"] == 1
    assert result["marked_missing_count"] == 0
    delete_cached_media.assert_awaited_once_with("evt-purge-delete")

    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event("evt-purge-delete")

    assert detection is None
    history = error_diagnostics_history.snapshot(limit=10)
    assert any(
        event.get("reason_code") == "frigate_missing_deleted"
        and event.get("event_id") == "evt-purge-delete"
        for event in history["events"]
    )


@pytest.mark.parametrize(
    "event_data,expected_error",
    [
        ({"has_clip": False, "has_snapshot": True}, "clip_unavailable"),
        ({"has_clip": True, "has_snapshot": False}, "snapshot_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_purge_missing_all_media_marks_if_either_clip_or_snapshot_is_missing(event_data, expected_error):
    settings.frigate.clips_enabled = True
    settings.maintenance.frigate_missing_behavior = "mark_missing"
    await _insert_detection("evt-purge-all")

    with patch.object(settings_router.frigate_client, "get_version", new=AsyncMock(return_value="0.17.1")), \
         patch.object(
             settings_router.frigate_client,
             "get_event_with_error",
             new=AsyncMock(return_value=(event_data, None)),
         ):
        result = await settings_router._purge_missing_all_media()

    assert result["status"] == "completed"
    assert result["checked"] == 1
    assert result["missing"] == 1
    assert result["marked_missing_count"] == 1

    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event("evt-purge-all")

    assert detection is not None
    assert detection.frigate_status == "missing"
    assert detection.frigate_last_error == expected_error


@pytest.mark.asyncio
async def test_purge_missing_all_media_clears_stale_missing_state_when_media_returns():
    settings.frigate.clips_enabled = True
    settings.maintenance.frigate_missing_behavior = "mark_missing"
    await _insert_detection("evt-purge-all-restored")
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.mark_frigate_missing("evt-purge-all-restored", error="clip_unavailable")

    with patch.object(settings_router.frigate_client, "get_version", new=AsyncMock(return_value="0.17.1")), \
         patch.object(
             settings_router.frigate_client,
             "get_event_with_error",
             new=AsyncMock(return_value=({"has_clip": True, "has_snapshot": True}, None)),
         ):
        result = await settings_router._purge_missing_all_media()

    assert result["status"] == "completed"
    assert result["checked"] == 1
    assert result["missing"] == 0
    assert result["cleared_missing_count"] == 1

    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event("evt-purge-all-restored")

    assert detection is not None
    assert detection.frigate_status == "present"
    assert detection.frigate_last_error is None
