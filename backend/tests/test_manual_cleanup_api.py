"""Purge Old Records does what the scheduled cleanup does, now."""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def owner_with_century_retention():
    original = (
        settings.auth.enabled,
        settings.maintenance.retention_days,
        settings.media_cache.per_species_minimum,
    )
    settings.auth.enabled = False
    # A century keeps every other test's rows out of reach; only the 1900 rows are old enough.
    settings.maintenance.retention_days = 36500
    settings.media_cache.per_species_minimum = 0
    yield
    (
        settings.auth.enabled,
        settings.maintenance.retention_days,
        settings.media_cache.per_species_minimum,
    ) = original


@pytest.mark.asyncio
async def test_purge_old_records_removes_old_audio_as_the_scheduled_cleanup_does(client: httpx.AsyncClient):
    """The docs say the button runs the cleanup now; it used to leave old audio behind."""
    tag = uuid.uuid4().hex[:8]
    species = f"Purgebird {tag}"
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                                       frigate_event, camera_name, is_hidden, manual_tagged)
               VALUES ('1900-01-01 12:00:00', 1, 0.9, ?, ?, ?, 'feeder', 0, 0)""",
            (species, species, f"evt-purge-{tag}"),
        )
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES ('1900-01-01 12:00:00', ?, 0.8, 'mic', '{}', ?)""",
            (species, species),
        )
        await db.commit()

    try:
        response = await client.post("/api/maintenance/cleanup")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["deleted_count"] >= 1
        assert payload["audio_deleted_count"] >= 1

        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(*) FROM detections WHERE frigate_event = ?", (f"evt-purge-{tag}",)
            ) as cur:
                assert (await cur.fetchone())[0] == 0
            async with db.execute("SELECT COUNT(*) FROM audio_detections WHERE species = ?", (species,)) as cur:
                assert (await cur.fetchone())[0] == 0
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (f"evt-purge-{tag}",))
            await db.execute("DELETE FROM audio_detections WHERE species = ?", (species,))
            await db.commit()


@pytest.mark.asyncio
async def test_purge_with_unlimited_retention_deletes_nothing(client: httpx.AsyncClient):
    settings.maintenance.retention_days = 0
    response = await client.post("/api/maintenance/cleanup")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "skipped"
