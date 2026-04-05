from datetime import datetime, timezone
from pathlib import Path
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
    original_clips_enabled = settings.frigate.clips_enabled
    original_recording_enabled = settings.frigate.recording_clip_enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.frigate.clips_enabled = original_clips_enabled
    settings.frigate.recording_clip_enabled = original_recording_enabled


async def _insert_detection(event_id: str, species_name: str, camera_name: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.88,
                species_name,
                species_name,
                event_id,
                camera_name,
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_ai_analysis_prefers_cached_recording_clip(client: httpx.AsyncClient, tmp_path: Path):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True

    event_id = "evt-ai-recording-preferred"
    await _insert_detection(event_id, "Robin", "cam1")
    recording_path = tmp_path / f"{event_id}_recording.mp4"
    recording_path.write_bytes(b"recording-bytes")

    try:
        with patch("app.routers.ai._get_valid_cached_recording_clip_path", new=AsyncMock(return_value=(str(recording_path), "cam1", 1700000000, 1700000030))), \
             patch("app.routers.ai.frigate_client.get_clip_with_error", new=AsyncMock(return_value=(b"event-bytes", None))) as mock_event_clip, \
             patch("app.routers.ai.ai_service.extract_frames_from_clip", return_value=[b"frame-1", b"frame-2"]) as mock_extract, \
             patch("app.routers.ai.ai_service.analyze_detection", new=AsyncMock(return_value="analysis")) as mock_analyze:
            response = await client.post(f"/api/events/{event_id}/analyze", params={"force": "true"})

        assert response.status_code == 200, response.text
        mock_event_clip.assert_not_awaited()
        mock_extract.assert_called_once_with(b"recording-bytes", frame_count=5, clip_variant="recording")
        assert mock_analyze.await_args.kwargs["metadata"]["frame_source"] == "recording"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_ai_analysis_falls_back_to_event_clip_when_recording_missing(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True

    event_id = "evt-ai-event-fallback"
    await _insert_detection(event_id, "Robin", "cam1")

    try:
        with patch("app.routers.ai._get_valid_cached_recording_clip_path", new=AsyncMock(return_value=(None, None, None, None))), \
             patch("app.routers.ai.frigate_client.get_clip_with_error", new=AsyncMock(return_value=(b"event-bytes", None))) as mock_event_clip, \
             patch("app.routers.ai.ai_service.extract_frames_from_clip", return_value=[b"frame-1", b"frame-2"]) as mock_extract, \
             patch("app.routers.ai.ai_service.analyze_detection", new=AsyncMock(return_value="analysis")) as mock_analyze:
            response = await client.post(f"/api/events/{event_id}/analyze", params={"force": "true"})

        assert response.status_code == 200, response.text
        mock_event_clip.assert_awaited_once()
        mock_extract.assert_called_once_with(b"event-bytes", frame_count=5, clip_variant="event")
        assert mock_analyze.await_args.kwargs["metadata"]["frame_source"] == "event"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_ai_analysis_falls_back_to_snapshot_when_clip_frames_unavailable(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True

    event_id = "evt-ai-snapshot-fallback"
    await _insert_detection(event_id, "Robin", "cam1")

    try:
        with patch("app.routers.ai._get_valid_cached_recording_clip_path", new=AsyncMock(return_value=(None, None, None, None))), \
             patch("app.routers.ai.frigate_client.get_clip_with_error", new=AsyncMock(return_value=(b"event-bytes", None))), \
             patch("app.routers.ai.ai_service.extract_frames_from_clip", return_value=[]), \
             patch("app.routers.ai.frigate_client.get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")) as mock_snapshot, \
             patch("app.routers.ai.ai_service.analyze_detection", new=AsyncMock(return_value="analysis")) as mock_analyze:
            response = await client.post(f"/api/events/{event_id}/analyze", params={"force": "true"})

        assert response.status_code == 200, response.text
        mock_snapshot.assert_awaited_once()
        assert mock_analyze.await_args.kwargs["image_data"] == b"snapshot-bytes"
        assert mock_analyze.await_args.kwargs["metadata"]["frame_source"] == "snapshot"
        assert mock_analyze.await_args.kwargs["image_list"] is None
    finally:
        await _delete_detection(event_id)
