from datetime import datetime, timezone
from urllib.parse import quote
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


async def _seed_taxon_and_detections(taxa_id: int, event_prefix: str) -> None:
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id)
            VALUES (?, ?, ?)
            """,
            ("Cyanistes caeruleus", "Blue Tit", taxa_id),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name)
            VALUES (?, ?, ?)
            """,
            (taxa_id, "es", "Herrerillo comun"),
        )
        for idx, display_name in enumerate(["Blue Tit", "Cyanistes caeruleus"], start=1):
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
                    idx,
                    0.9,
                    display_name,
                    display_name,
                    f"{event_prefix}_{idx}",
                    "test-camera",
                    "Cyanistes caeruleus",
                    "Blue Tit",
                    taxa_id,
                ),
            )
        await db.commit()


async def _cleanup_taxon_and_detections(taxa_id: int, event_prefix: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE ?", (f"{event_prefix}_%",))
        await db.execute("DELETE FROM taxonomy_translations WHERE taxa_id = ?", (taxa_id,))
        await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_species_stats_accepts_localized_common_name_and_aggregates_aliases(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    suffix = uuid.uuid4().hex[:8]
    taxa_id = 900000 + int(suffix[:4], 16)
    event_prefix = f"speciesstats-{suffix}"
    await _seed_taxon_and_detections(taxa_id=taxa_id, event_prefix=event_prefix)

    try:
        response = await client.get(
            f"/api/species/{quote('Herrerillo comun', safe='')}/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["species_name"] == "Herrerillo comun"
        assert data["taxa_id"] == taxa_id
        assert data["scientific_name"] == "Cyanistes caeruleus"
        assert data["common_name"] == "Herrerillo comun"
        assert data["total_sightings"] == 2
        assert len(data["recent_sightings"]) == 2
    finally:
        await _cleanup_taxon_and_detections(taxa_id=taxa_id, event_prefix=event_prefix)
