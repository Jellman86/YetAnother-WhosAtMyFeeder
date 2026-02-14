import uuid
from datetime import datetime, timezone

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


async def _insert_detection(event_id: str, species_name: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.91,
                species_name,
                species_name,
                event_id,
                "test-camera",
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_favorite_endpoints_are_idempotent_and_filterable(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"fav-{uuid.uuid4().hex[:10]}"
    species = f"Favorite Test Bird {uuid.uuid4().hex[:6]}"
    await _insert_detection(event_id, species)

    try:
        first = await client.post(f"/api/events/{event_id}/favorite")
        assert first.status_code == 200
        assert first.json()["is_favorite"] is True

        second = await client.post(f"/api/events/{event_id}/favorite")
        assert second.status_code == 200
        assert second.json()["is_favorite"] is True

        events_resp = await client.get(
            "/api/events",
            params={"favorites": "true", "species": species, "limit": 10},
        )
        assert events_resp.status_code == 200
        rows = events_resp.json()
        assert len(rows) == 1
        assert rows[0]["frigate_event"] == event_id
        assert rows[0]["is_favorite"] is True

        count_resp = await client.get(
            "/api/events/count",
            params={"favorites": "true", "species": species},
        )
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 1

        remove_first = await client.delete(f"/api/events/{event_id}/favorite")
        assert remove_first.status_code == 200
        assert remove_first.json()["is_favorite"] is False

        remove_second = await client.delete(f"/api/events/{event_id}/favorite")
        assert remove_second.status_code == 200
        assert remove_second.json()["is_favorite"] is False
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_guest_cannot_modify_favorites(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True

    event_id = f"fav-{uuid.uuid4().hex[:10]}"
    await _insert_detection(event_id, "Guest Auth Bird")

    try:
        response = await client.post(f"/api/events/{event_id}/favorite")
        assert response.status_code == 403
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_owner_can_clear_all_favorites(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_a = f"fav-{uuid.uuid4().hex[:10]}"
    event_b = f"fav-{uuid.uuid4().hex[:10]}"
    await _insert_detection(event_a, "Clear Favorite A")
    await _insert_detection(event_b, "Clear Favorite B")

    try:
        assert (await client.post(f"/api/events/{event_a}/favorite")).status_code == 200
        assert (await client.post(f"/api/events/{event_b}/favorite")).status_code == 200

        clear_resp = await client.post("/api/maintenance/favorites/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["deleted_count"] == 2

        count_resp = await client.get("/api/events/count", params={"favorites": "true"})
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 0
    finally:
        await _delete_detection(event_a)
        await _delete_detection(event_b)
