from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.database import get_db, init_db, close_db
from app.config import settings


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


@pytest.mark.asyncio
async def test_event_classification_status_returns_current_video_fields(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = "classification-status-test-1"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden,
                video_classification_status, video_classification_error, video_classification_timestamp,
                video_classification_provider, video_classification_backend, video_classification_model_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.isoformat(sep=" "),
                1,
                0.91,
                "Test Bird",
                "Test Bird",
                event_id,
                "test-camera",
                "failed",
                "video_timeout",
                now.isoformat(sep=" "),
                "intel_gpu",
                "openvino",
                "convnext_large_inat21",
            ),
        )
        await db.commit()

    response = await client.get(f"/api/events/{event_id}/classification-status")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["event_id"] == event_id
    assert payload["video_classification_status"] == "failed"
    assert payload["video_classification_error"] == "video_timeout"
    assert payload["video_classification_timestamp"] is not None
    assert payload["video_classification_provider"] == "intel_gpu"
    assert payload["video_classification_backend"] == "openvino"
    assert payload["video_classification_model_id"] == "convnext_large_inat21"
    assert payload["video_classification_model_name"] == "ConvNeXt Large (High Accuracy)"


@pytest.mark.asyncio
async def test_events_list_includes_video_runtime_metadata(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = "classification-status-test-2"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden,
                video_classification_status, video_classification_error, video_classification_timestamp,
                video_classification_provider, video_classification_backend, video_classification_model_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.isoformat(sep=" "),
                1,
                0.93,
                "Blue Jay",
                "Blue Jay",
                event_id,
                "test-camera",
                "completed",
                None,
                now.isoformat(sep=" "),
                "intel_gpu",
                "openvino",
                "convnext_large_inat21",
            ),
        )
        await db.commit()

    response = await client.get("/api/events", params={"limit": 10, "camera": "test-camera"})
    assert response.status_code == 200, response.text
    payload = response.json()
    row = next(item for item in payload if item["frigate_event"] == event_id)
    assert row["video_classification_provider"] == "intel_gpu"
    assert row["video_classification_backend"] == "openvino"
    assert row["video_classification_model_id"] == "convnext_large_inat21"
    assert row["video_classification_model_name"] == "ConvNeXt Large (High Accuracy)"


@pytest.mark.asyncio
async def test_events_list_reports_cached_media_when_frigate_event_is_missing(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = "classification-status-test-cached-media"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden,
                video_classification_status, video_classification_error, video_classification_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                now.isoformat(sep=" "),
                1,
                0.88,
                "Unknown Bird",
                "Unknown Bird",
                event_id,
                "test-camera",
                "failed",
                "event_not_found",
                now.isoformat(sep=" "),
            ),
        )
        await db.commit()

    with patch("app.routers.events.frigate_client.get_event", new=AsyncMock(return_value=None)), \
         patch("app.services.media_cache.media_cache.has_snapshot", return_value=True), \
         patch("app.services.media_cache.media_cache.has_clip", return_value=False), \
         patch("app.services.media_cache.media_cache.has_recording_clip", return_value=True):
        response = await client.get("/api/events", params={"limit": 10, "camera": "test-camera"})

    assert response.status_code == 200, response.text
    payload = response.json()
    row = next(item for item in payload if item["frigate_event"] == event_id)
    assert row["has_frigate_event"] is False
    assert row["has_snapshot"] is True
    assert row["has_clip"] is True


@pytest.mark.asyncio
async def test_event_classification_status_returns_404_for_missing_event(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    response = await client.get("/api/events/missing-event-123/classification-status")
    assert response.status_code == 404, response.text
