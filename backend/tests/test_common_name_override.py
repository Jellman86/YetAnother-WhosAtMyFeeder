from datetime import datetime, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services.taxonomy.taxonomy_service import TaxonomyService


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


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
async def test_provider_refresh_preserves_manual_common_name():
    service = TaxonomyService()
    async with get_db() as db:
        scientific_name = f"Testus override-{uuid.uuid4().hex[:8]}"
        await db.execute(
            """INSERT INTO taxonomy_cache
               (scientific_name, common_name, manual_common_name, taxa_id, is_not_found)
               VALUES (?, ?, ?, ?, 0)""",
            (scientific_name, "Provider Name", "Garden Name", 990001),
        )
        await service._insert_cache(
            db,
            {
                "scientific_name": scientific_name,
                "common_name": "Updated Provider Name",
                "taxa_id": 990001,
            },
        )
        await db.commit()

        result = await service.get_names(scientific_name, db=db)
        async with db.execute(
            "SELECT common_name, manual_common_name FROM taxonomy_cache WHERE scientific_name = ?",
            (scientific_name,),
        ) as cursor:
            stored = await cursor.fetchone()
        await db.execute("DELETE FROM taxonomy_cache WHERE scientific_name = ?", (scientific_name,))
        await db.commit()

    assert stored == ("Updated Provider Name", "Garden Name")
    assert result["common_name"] == "Garden Name"


@pytest.mark.asyncio
async def test_owner_can_set_read_and_clear_common_name_override(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    suffix = uuid.uuid4().hex[:8]
    scientific_name = f"Testus familiaris-{suffix}"
    event_id = f"common-name-{suffix}"
    taxa_id = 990000 + int(suffix[:4], 16)
    now = datetime.now(timezone.utc).isoformat(sep=" ")

    async with get_db() as db:
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            (scientific_name, "Provider Finch", taxa_id),
        )
        await db.execute(
            """INSERT INTO detections (
                   detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, scientific_name, common_name, taxa_id
               ) VALUES (?, 1, 0.9, ?, ?, ?, 'test-camera', ?, ?, ?)""",
            (now, "Provider Finch", scientific_name, event_id, scientific_name, "Provider Finch", taxa_id),
        )
        await db.commit()

    try:
        response = await client.put(
            "/api/species/common-name-override",
            json={"scientific_name": scientific_name, "common_name": "My Feeder Finch"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["manual_common_name"] == "My Feeder Finch"

        response = await client.get(
            "/api/species/common-name-override",
            params={"scientific_name": scientific_name},
        )
        assert response.status_code == 200, response.text
        assert response.json()["effective_common_name"] == "My Feeder Finch"

        async with get_db() as db:
            async with db.execute("SELECT common_name FROM detections WHERE frigate_event = ?", (event_id,)) as cursor:
                assert (await cursor.fetchone())[0] == "My Feeder Finch"

        response = await client.delete(
            "/api/species/common-name-override",
            params={"scientific_name": scientific_name},
        )
        assert response.status_code == 200, response.text
        assert response.json()["manual_common_name"] is None
        assert response.json()["effective_common_name"] == "Provider Finch"
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
            await db.execute("DELETE FROM taxonomy_cache WHERE scientific_name = ?", (scientific_name,))
            await db.commit()
