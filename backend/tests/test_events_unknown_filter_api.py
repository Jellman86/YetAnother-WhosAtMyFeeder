import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.events import _detection_updated_payload, _event_filters_cache


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


async def _insert_detection(
    event_id: str,
    species_name: str,
    camera_name: str,
    *,
    category_name: str | None = None,
    scientific_name: str | None = None,
    common_name: str | None = None,
    taxa_id: int | None = None,
    is_hidden: bool = False,
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.77,
                species_name,
                category_name or species_name,
                event_id,
                camera_name,
                1 if is_hidden else 0,
                scientific_name,
                common_name,
                taxa_id,
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


@pytest.mark.asyncio
async def test_events_filters_exclude_hidden_species_rows(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    hidden_species = f"Zebra Mussel {uuid.uuid4().hex[:6]}"
    visible_species = f"Visible Species {uuid.uuid4().hex[:6]}"
    hidden_event = f"evt-{uuid.uuid4().hex[:8]}"
    visible_event = f"evt-{uuid.uuid4().hex[:8]}"

    await _insert_detection(hidden_event, hidden_species, "cam-hidden", is_hidden=True)
    await _insert_detection(visible_event, visible_species, "cam-hidden")

    try:
        events_resp = await client.get(
            "/api/events",
            params={"species": hidden_species, "limit": 20},
        )
        assert events_resp.status_code == 200
        assert events_resp.json() == []

        count_resp = await client.get(
            "/api/events/count",
            params={"species": hidden_species},
        )
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 0

        filters_resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
        assert filters_resp.status_code == 200
        species_values = {item["value"] for item in filters_resp.json()["species"]}
        assert visible_species in species_values
        assert hidden_species not in species_values
    finally:
        await _delete_detection(hidden_event)
        await _delete_detection(visible_event)


@pytest.mark.asyncio
async def test_events_filters_exclude_hidden_only_cameras(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    hidden_event = f"evt-{uuid.uuid4().hex[:8]}"
    visible_event = f"evt-{uuid.uuid4().hex[:8]}"

    await _insert_detection(hidden_event, f"Hidden Camera Species {uuid.uuid4().hex[:6]}", "cam-hidden-only", is_hidden=True)
    await _insert_detection(visible_event, f"Visible Camera Species {uuid.uuid4().hex[:6]}", "cam-visible")

    try:
        filters_resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
        assert filters_resp.status_code == 200
        cameras = set(filters_resp.json()["cameras"])
        assert "cam-visible" in cameras
        assert "cam-hidden-only" not in cameras
    finally:
        await _delete_detection(hidden_event)
        await _delete_detection(visible_event)


@pytest.mark.asyncio
async def test_events_filters_force_refresh_bypasses_cache(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    species_a = f"Refresh Species A {uuid.uuid4().hex[:6]}"
    species_b = f"Refresh Species B {uuid.uuid4().hex[:6]}"
    event_a = f"evt-{uuid.uuid4().hex[:8]}"
    event_b = f"evt-{uuid.uuid4().hex[:8]}"

    await _insert_detection(event_a, species_a, "cam-refresh")
    try:
        first_resp = await client.get("/api/events/filters")
        assert first_resp.status_code == 200
        first_species_values = {s["value"] for s in first_resp.json()["species"]}
        assert species_a in first_species_values
        assert species_b not in first_species_values

        await _insert_detection(event_b, species_b, "cam-refresh")

        cached_resp = await client.get("/api/events/filters")
        assert cached_resp.status_code == 200
        cached_species_values = {s["value"] for s in cached_resp.json()["species"]}
        assert species_b not in cached_species_values

        refreshed_resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
        assert refreshed_resp.status_code == 200
        refreshed_species_values = {s["value"] for s in refreshed_resp.json()["species"]}
        assert species_a in refreshed_species_values
        assert species_b in refreshed_species_values
    finally:
        await _delete_detection(event_a)
        await _delete_detection(event_b)


@pytest.mark.asyncio
async def test_unknown_bird_filter_matches_hidden_noncanonical_labels_and_masks_payload(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    camera_name = f"cam-{uuid.uuid4().hex[:6]}"
    event_id = f"evt-{uuid.uuid4().hex[:10]}"
    await _insert_detection(
        event_id,
        "Great tit and allies",
        camera_name,
        category_name="Great tit and allies",
        scientific_name="Great tit and allies",
        common_name="Great tit and allies",
    )

    try:
        events_resp = await client.get(
            "/api/events",
            params={"species": "Unknown Bird", "camera": camera_name, "limit": 20},
        )
        assert events_resp.status_code == 200, events_resp.text
        rows = events_resp.json()
        assert len(rows) == 1
        assert rows[0]["frigate_event"] == event_id
        assert rows[0]["detection_time"].endswith("Z")
        assert rows[0]["display_name"] == "Unknown Bird"
        assert rows[0]["category_name"] == "Unknown Bird"
        assert rows[0]["scientific_name"] is None
        assert rows[0]["common_name"] is None
        assert rows[0]["taxa_id"] is None

        count_resp = await client.get(
            "/api/events/count",
            params={"species": "Unknown Bird", "camera": camera_name},
        )
        assert count_resp.status_code == 200
        assert count_resp.json()["count"] == 1

        filters_resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
        assert filters_resp.status_code == 200, filters_resp.text
        species_values = {item["value"] for item in filters_resp.json()["species"]}
        assert "alias:unknown_bird" in species_values
        assert "Great tit and allies" not in species_values
    finally:
        await _delete_detection(event_id)


def test_detection_updated_payload_masks_hidden_noncanonical_labels():
    detection = SimpleNamespace(
        frigate_event="evt-1",
        display_name="Life (life)",
        category_name="Life (life)",
        score=0.77,
        detection_time=datetime.now(timezone.utc),
        camera_name="cam-1",
        is_hidden=False,
        is_favorite=False,
        frigate_score=0.88,
        sub_label=None,
        manual_tagged=False,
        audio_confirmed=False,
        audio_species=None,
        audio_score=None,
        temperature=None,
        weather_condition=None,
        weather_cloud_cover=None,
        weather_wind_speed=None,
        weather_wind_direction=None,
        weather_precipitation=None,
        weather_rain=None,
        weather_snowfall=None,
        scientific_name="Life",
        common_name="Life",
        taxa_id=123,
        video_classification_score=None,
        video_classification_label=None,
        video_classification_status=None,
        video_classification_error=None,
        video_classification_provider=None,
        video_classification_backend=None,
        video_classification_model_id=None,
        video_classification_timestamp=None,
        video_result_blocked=False,
    )

    payload = _detection_updated_payload(detection)

    assert payload["display_name"] == "Unknown Bird"
    assert payload["category_name"] == "Unknown Bird"
    assert payload["scientific_name"] is None
    assert payload["common_name"] is None
    assert payload["taxa_id"] is None
