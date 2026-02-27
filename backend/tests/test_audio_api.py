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
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_show_camera_names = settings.public_access.show_camera_names
    original_camera_audio_mapping = dict(settings.frigate.camera_audio_mapping)
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.public_access.show_camera_names = original_show_camera_names
    settings.frigate.camera_audio_mapping = original_camera_audio_mapping


@pytest.mark.asyncio
async def test_audio_sources_returns_recent_distinct_source_names(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc)
    rows = [
        (
            (now - timedelta(minutes=1)).isoformat(sep=" "),
            "Dunnock",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_new", "Source": {"id": "rtsp_new", "displayName": "BirdCam"}}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(minutes=5)).isoformat(sep=" "),
            "Woodpigeon",
            0.8,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_old", "Source": {"id": "rtsp_old", "displayName": "BirdCam"}}),
            "Columba palumbus",
        ),
        (
            (now - timedelta(minutes=2)).isoformat(sep=" "),
            "Blue Tit",
            0.85,
            "Garden Mic",
            json.dumps({"Source": {"id": "rtsp_garden", "displayName": "Garden Mic"}}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert [item["source_name"] for item in payload] == ["BirdCam", "Garden Mic"]

    birdcam = payload[0]
    assert birdcam["sample_source_id"] == "rtsp_new"
    assert birdcam["seen_count"] == 2
    assert birdcam["last_seen"].startswith(now.strftime("%Y-%m-%d"))


@pytest.mark.asyncio
async def test_audio_context_supports_multi_source_camera_mapping(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"front": "BirdCam, Garden Mic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (target - timedelta(seconds=15)).isoformat(sep=" "),
            "Dunnock",
            0.81,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
        (
            (target + timedelta(seconds=12)).isoformat(sep=" "),
            "Blue Tit",
            0.74,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic", "src": "rtsp_garden"}),
            "Cyanistes caeruleus",
        ),
        (
            (target + timedelta(seconds=8)).isoformat(sep=" "),
            "Woodpigeon",
            0.7,
            "Other Mic",
            json.dumps({"nm": "Other Mic", "src": "rtsp_other"}),
            "Columba palumbus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={
            "timestamp": target.isoformat(),
            "camera": "front",
            "window_seconds": 60,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    species = [item["species"] for item in payload]
    assert "Dunnock" in species
    assert "Blue Tit" in species
    assert "Woodpigeon" not in species
