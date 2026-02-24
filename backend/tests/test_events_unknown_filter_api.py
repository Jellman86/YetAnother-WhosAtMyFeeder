import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.events import _event_filters_cache


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
def reset_auth_and_unknown_labels():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_unknown_labels = list(settings.classification.unknown_bird_labels)
    _event_filters_cache.clear()
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.classification.unknown_bird_labels = original_unknown_labels
    _event_filters_cache.clear()


async def _insert_detection(event_id: str, species_name: str, camera_name: str) -> None:
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
                0.77,
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
async def test_events_unknown_bird_filter_matches_configured_unknown_labels(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    raw_unknown_label = f"Unknown Alias {uuid.uuid4().hex[:8]}"
    camera_name = f"cam-{uuid.uuid4().hex[:6]}"
    event_id = f"evt-{uuid.uuid4().hex[:10]}"
    settings.classification.unknown_bird_labels = [raw_unknown_label]
    await _insert_detection(event_id, raw_unknown_label, camera_name)

    try:
        events_resp = await client.get(
            "/api/events",
            params={"species": "Unknown Bird", "camera": camera_name, "limit": 20},
        )
        assert events_resp.status_code == 200
        rows = events_resp.json()
        assert len(rows) == 1
        assert rows[0]["frigate_event"] == event_id
        assert rows[0]["display_name"] == "Unknown Bird"

        count_resp = await client.get(
            "/api/events/count",
            params={"species": "Unknown Bird", "camera": camera_name},
        )
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 1
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_events_unknown_alias_filter_token_matches_configured_unknown_labels(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    raw_unknown_label = f"Unknown Alias {uuid.uuid4().hex[:8]}"
    camera_name = f"cam-{uuid.uuid4().hex[:6]}"
    event_id = f"evt-{uuid.uuid4().hex[:10]}"
    settings.classification.unknown_bird_labels = [raw_unknown_label]
    await _insert_detection(event_id, raw_unknown_label, camera_name)

    try:
        events_resp = await client.get(
            "/api/events",
            params={"species": "alias:unknown_bird", "camera": camera_name, "limit": 20},
        )
        assert events_resp.status_code == 200
        rows = events_resp.json()
        assert len(rows) == 1
        assert rows[0]["frigate_event"] == event_id
        assert rows[0]["display_name"] == "Unknown Bird"

        count_resp = await client.get(
            "/api/events/count",
            params={"species": "alias:unknown_bird", "camera": camera_name},
        )
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 1
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_events_filters_canonicalize_unknown_aliases_to_single_option(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    unknown_a = f"Unknown Alias A {uuid.uuid4().hex[:6]}"
    unknown_b = f"Unknown Alias B {uuid.uuid4().hex[:6]}"
    known = f"Known Species {uuid.uuid4().hex[:6]}"
    settings.classification.unknown_bird_labels = [unknown_a, unknown_b]

    event_ids = [f"evt-{uuid.uuid4().hex[:8]}" for _ in range(3)]
    await _insert_detection(event_ids[0], unknown_a, "cam-a")
    await _insert_detection(event_ids[1], unknown_b, "cam-a")
    await _insert_detection(event_ids[2], known, "cam-a")

    try:
        resp = await client.get("/api/events/filters")
        assert resp.status_code == 200
        payload = resp.json()
        species = payload["species"]
        unknown_options = [s for s in species if s["value"] == "alias:unknown_bird"]
        assert len(unknown_options) == 1
        assert unknown_options[0]["display_name"] == "Unknown Bird"
        raw_unknown_values = {unknown_a, unknown_b}
        assert not any(s["value"] in raw_unknown_values for s in species)
    finally:
        for event_id in event_ids:
            await _delete_detection(event_id)
