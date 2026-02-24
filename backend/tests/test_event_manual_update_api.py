from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

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


async def _seed_detection_and_taxonomy(event_id: str, taxa_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", taxa_id),
        )
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (taxa_id, "es", "Herrerillo comun"),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                now,
                1,
                0.91,
                "Blue Tit",
                "Blue Tit",
                event_id,
                "test-camera",
                "Cyanistes caeruleus",
                "Blue Tit",
                taxa_id,
            ),
        )
        await db.commit()


async def _cleanup_detection_and_taxonomy(event_id: str, taxa_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute("DELETE FROM taxonomy_translations WHERE taxa_id = ?", (taxa_id,))
        await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_manual_update_treats_localized_alias_of_same_species_as_unchanged(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 910000 + int(uuid.uuid4().hex[:4], 16)
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        with patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock()) as mock_get_names, \
             patch("app.routers.events.audio_service.correlate_species", new=AsyncMock()) as mock_audio, \
             patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()) as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Herrerillo com\u00fan"},
                headers={"Accept-Language": "es"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "unchanged"

        mock_get_names.assert_not_awaited()
        mock_audio.assert_not_awaited()
        mock_broadcast.assert_not_awaited()

        async with get_db() as db:
            async with db.execute(
                "SELECT display_name, category_name, scientific_name, common_name, taxa_id, manual_tagged FROM detections WHERE frigate_event = ?",
                (event_id,),
            ) as cursor:
                row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "Blue Tit"
        assert row[1] == "Blue Tit"
        assert row[2] == "Cyanistes caeruleus"
        assert row[3] == "Blue Tit"
        assert row[4] == taxa_id
        assert row[5] == 0
    finally:
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)
