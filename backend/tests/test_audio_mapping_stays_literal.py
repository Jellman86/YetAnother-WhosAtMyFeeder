"""A camera's audio mapping matches each call by the names and ids it was stored with, and nothing
more, wherever it is read, even after sources are tracked across renames (#1111)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.audio_history_repository import (
    AudioHistoryRepository,
    public_audio_conditions_sql,
    rank_audio_context,
)
from app.services.audio.audio_service import AudioService
from app.utils.api_datetime import serialize_storage_datetime
from app.utils.birdnet_payload import extract_audio_mapping_keys, parse_mapping_filter_values

pytestmark = pytest.mark.usefixtures("history_pool")

NOW = datetime.now(timezone.utc).replace(microsecond=0)
NODE = "BirdNET-Go Garden"


def _payload(number: int, name: str | None, source_id: str | None, node: str | None = NODE, **extra) -> dict:
    data: dict = {"CommonName": "Robin", "ScientificName": "Erithacus rubecula", "detectionId": number, **extra}
    if name is not None:
        data["sourceName"] = name
    if source_id is not None:
        data["sourceId"] = source_id
    if node is not None:
        data["SourceNode"] = node
    return data


# A source renamed from "birdcam" to "Feeder", a second stream also called "Feeder", a stream named
# after the first one's id, the same id on another install, a call from before ids, and a call
# carrying "Feeder" as a second name: (BirdNET-Go number, stored sensor, payload).
CALLS = [
    (1, "birdcam", _payload(1, "birdcam", "rtsp_a")),
    (2, "Feeder", _payload(2, "Feeder", "rtsp_a")),
    (3, "Feeder", _payload(3, "Feeder", "rtsp_b")),
    (4, "rtsp_a", _payload(4, "rtsp_a", "rtsp_c")),
    (5, "Porch", _payload(5, "Porch", "rtsp_a", node="House")),
    (6, "birdcam", {"CommonName": "Robin", "nm": "birdcam", "detectionId": 6}),
    (7, "Backyard", _payload(7, "Feeder", "rtsp_d", nm="Backyard")),
]
MAPPING_VALUES = ["birdcam", "Feeder", "rtsp_a", "Porch", "Backyard", "birdcam; nestcam", "*", "unknown mic"]


def literal(value: str) -> set[int]:
    """The calls a mapping matched before sources were tracked."""
    wildcard, keys = parse_mapping_filter_values(value)
    return {
        number
        for number, sensor, data in CALLS
        if wildcard or keys & extract_audio_mapping_keys(sensor, json.dumps(data))
    }


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_without_sign_in():
    saved = (
        settings.auth.enabled,
        settings.public_access.enabled,
        settings.public_access.show_historical_days,
        settings.frigate.audio_correlation_window_seconds,
        dict(settings.frigate.camera_audio_mapping),
    )
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    (
        settings.auth.enabled,
        settings.public_access.enabled,
        settings.public_access.show_historical_days,
        settings.frigate.audio_correlation_window_seconds,
        mapping,
    ) = saved
    settings.frigate.camera_audio_mapping = mapping


async def store_calls() -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()
        repo = AudioHistoryRepository(db)
        for number, sensor, data in CALLS:
            await repo.insert_audio_detection(
                NOW - timedelta(minutes=number), "Robin", 0.9, sensor, data, scientific_name="Erithacus rubecula"
            )


def _number(raw_data: str | None) -> int:
    return json.loads(raw_data or "{}")["detectionId"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", MAPPING_VALUES)
async def test_record_context_hears_exactly_the_calls_the_mapping_always_matched(client, value):
    await store_calls()
    settings.frigate.camera_audio_mapping = {"feeder_cam": value}

    response = await client.get(
        "/api/audio/context",
        params={"timestamp": NOW.isoformat(), "camera": "feeder_cam", "window_seconds": 3600, "limit": 20},
    )
    assert response.status_code == 200, response.text
    assert {item["birdnet_id"] for item in response.json()} == literal(value)

    # The ranking every record's context and the batched owner context share.
    async with get_db() as db:
        async with db.execute(
            "SELECT timestamp, species, confidence, sensor_id, scientific_name, raw_data FROM audio_detections"
        ) as cursor:
            rows = list(await cursor.fetchall())
    ranked, suppressed = rank_audio_context(rows, NOW, value, 20)
    assert {item["birdnet_id"] for item in ranked} == literal(value)
    assert suppressed == len(CALLS) - len(literal(value))


@pytest.mark.asyncio
@pytest.mark.parametrize("value", MAPPING_VALUES)
async def test_a_guests_audio_evidence_hears_exactly_the_calls_the_mapping_always_matched(value):
    await store_calls()
    settings.frigate.camera_audio_mapping = {"feeder_cam": value}
    settings.public_access.show_historical_days = 7
    settings.frigate.audio_correlation_window_seconds = 3600

    async with get_db() as db:
        sql, params = await public_audio_conditions_sql(db, match_species=False)
        query = f"""WITH d(camera_name, detection_time, audio_species) AS (VALUES (?, ?, ?))
            SELECT a.raw_data FROM d JOIN audio_detections a ON {sql}"""
        async with db.execute(query, ["feeder_cam", serialize_storage_datetime(NOW), "Robin", *params]) as cursor:
            heard = {_number(row[0]) for row in await cursor.fetchall()}
    assert heard == literal(value)


@pytest.mark.asyncio
async def test_audio_history_and_the_explorer_match_by_each_calls_own_names_and_the_saved_mapping(client):
    await store_calls()
    mapping = {"feeder_cam": "birdcam", "nest_cam": "Feeder"}
    settings.frigate.camera_audio_mapping = mapping
    seen: dict[str, tuple[dict[int, set[str]], dict]] = {}

    def keys_by_number(items) -> dict[int, set[str]]:
        # Read when the match runs: the response drops the keys afterwards.
        return {
            (item["birdnet_id"] if isinstance(item, dict) else item.birdnet_id): set(
                item["_mapping_keys"] if isinstance(item, dict) else item.mapping_keys
            )
            for item in items
        }

    def spy(name, original):
        def recorded(items, candidates, *, window_seconds, camera_audio_mapping):
            seen[name] = (keys_by_number(items), dict(camera_audio_mapping))
            return original(items, candidates, window_seconds=window_seconds, camera_audio_mapping=camera_audio_mapping)

        return recorded

    from app.routers import audio as audio_router

    with (
        patch.object(
            audio_router,
            "match_audio_history_visual_events",
            spy("history", audio_router.match_audio_history_visual_events),
        ),
        patch.object(audio_router, "attribute_calls", spy("explorer", audio_router.attribute_calls)),
    ):
        history = await client.get("/api/audio/history", params={"days": 1, "limit": 20})
        groups = await client.get(
            "/api/audio/heard-groups",
            params={"start_date": (NOW - timedelta(hours=1)).isoformat(), "end_date": NOW.isoformat()},
        )
    assert history.status_code == 200, history.text
    assert groups.status_code == 200, groups.text

    expected = {
        number: extract_audio_mapping_keys(sensor, json.dumps(data, ensure_ascii=True))
        for number, sensor, data in CALLS
    }
    assert seen["history"] == (expected, mapping)
    assert seen["explorer"] == (expected, mapping)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", MAPPING_VALUES)
async def test_live_correlation_hears_exactly_the_calls_the_mapping_always_matched(value):
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()
    with (
        patch("app.services.audio.audio_service.settings") as mocked,
        patch("app.services.taxonomy.taxonomy_service.taxonomy_service.get_names") as names,
    ):
        mocked.frigate.audio_buffer_hours = 1
        mocked.frigate.audio_correlation_window_seconds = 3600
        mocked.frigate.audio_min_confidence = 0.0
        mocked.frigate.camera_audio_mapping = {"feeder_cam": value}
        names.return_value = {"scientific_name": "Erithacus rubecula", "common_name": "Robin"}
        service = AudioService()
        heard_at = datetime.now(timezone.utc)
        for number, _sensor, data in CALLS:
            stamp = heard_at - timedelta(seconds=number)
            assert await service.add_detection({**data, "Confidence": 0.8, "BeginTime": stamp.isoformat()})

        heard = {
            detection.raw_data["detectionId"]
            for detection in service._buffer
            if service._camera_mapping_matches_detection(value, detection)
        }
        near = await service.get_detections_near(heard_at, camera_name="feeder_cam", window_seconds=60, limit=20)
        match = await service.find_match(heard_at, camera_name="feeder_cam")
        confirmed, _species, _score = await service.correlate_species(heard_at, "Robin", camera_name="feeder_cam")

    assert heard == literal(value)
    assert len(near) == len(literal(value))
    assert (match is not None) == bool(literal(value))
    assert confirmed == bool(literal(value))
