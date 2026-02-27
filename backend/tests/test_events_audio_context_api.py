from datetime import datetime, timedelta, timezone
import json

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
def reset_auth_and_mapping():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_mapping = dict(settings.frigate.camera_audio_mapping)
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.frigate.camera_audio_mapping = original_mapping


@pytest.mark.asyncio
async def test_events_include_audio_context_species_for_unmatched_audio(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-audio-context-{int(target.timestamp())}"

    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target - timedelta(minutes=5)).isoformat(sep=" "),
                (target + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                audio_confirmed, audio_species, audio_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (
                target.isoformat(sep=" "),
                1,
                0.82,
                "Great Tit",
                "Great Tit",
                event_id,
                "feeder-cam",
                "Corvus corone",
                0.75,
            ),
        )

        audio_rows = [
            (
                (target - timedelta(seconds=20)).isoformat(sep=" "),
                "Corvus corone",
                0.75,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Corvus corone",
            ),
            (
                (target + timedelta(seconds=10)).isoformat(sep=" "),
                "Passer domesticus",
                0.66,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Passer domesticus",
            ),
            (
                (target + timedelta(seconds=5)).isoformat(sep=" "),
                "Turdus merula",
                0.7,
                "OtherMic",
                json.dumps({"nm": "OtherMic", "src": "rtsp_other"}),
                "Turdus merula",
            ),
        ]
        for row in audio_rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/events", params={"camera": "feeder-cam", "limit": 10})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload, "Expected at least one event row"

    event = next(item for item in payload if item["frigate_event"] == event_id)
    assert event["audio_confirmed"] is False
    assert event["audio_species"] == "Corvus corone"
    assert event["audio_context_species"] == ["Corvus corone", "Passer domesticus"]


@pytest.mark.asyncio
async def test_events_handles_mixed_naive_and_aware_timestamps_for_audio_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target_aware = datetime.now(timezone.utc).replace(microsecond=0)
    target_naive = target_aware.replace(tzinfo=None)
    event_id = f"evt-audio-mixed-ts-{int(target_aware.timestamp())}"

    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target_aware - timedelta(minutes=5)).isoformat(sep=" "),
                (target_aware + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                audio_confirmed, audio_species, audio_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (
                target_naive.isoformat(sep=" "),
                1,
                0.77,
                "Blue Tit",
                "Blue Tit",
                event_id,
                "feeder-cam",
                "Passer domesticus",
                0.61,
            ),
        )
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (target_aware + timedelta(seconds=8)).isoformat(sep=" "),
                "Passer domesticus",
                0.61,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Passer domesticus",
            ),
        )
        await db.commit()

    response = await client.get("/api/events", params={"camera": "feeder-cam", "limit": 10})
    assert response.status_code == 200, response.text
    payload = response.json()
    event = next(item for item in payload if item["frigate_event"] == event_id)
    assert event["audio_context_species"] == ["Passer domesticus"]
