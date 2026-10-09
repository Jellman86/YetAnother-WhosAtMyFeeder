from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services.audio.heard_groups import HeardCall, fold_heard_calls

T0 = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


def call(minutes: float, species: str = "House Sparrow", confidence: float = 0.8, birdnet_id: int | None = 1, **extra):
    return HeardCall(
        timestamp=T0 + timedelta(minutes=minutes),
        species=species,
        scientific_name=extra.get("scientific_name", {"House Sparrow": "Passer domesticus", "Dunnock": "Prunella modularis"}.get(species)),
        confidence=confidence,
        birdnet_id=birdnet_id,
        source_name=extra.get("source_name", "patiocam"),
    )


def test_calls_of_one_species_within_the_gap_are_one_group():
    groups = fold_heard_calls([call(0), call(4), call(13)], gap_seconds=600)
    assert len(groups) == 1
    assert groups[0].call_count == 3
    assert groups[0].first_heard == T0
    assert groups[0].last_heard == T0 + timedelta(minutes=13)


def test_a_silence_longer_than_the_gap_starts_a_new_group():
    groups = fold_heard_calls([call(0), call(11)], gap_seconds=600)
    assert [group.call_count for group in groups] == [1, 1]
    assert groups[0].first_heard == T0 + timedelta(minutes=11), "newest group first"


def test_species_interleaved_in_time_keep_their_own_groups():
    groups = fold_heard_calls([call(0), call(1, "Dunnock"), call(2), call(3, "Dunnock")])
    assert sorted((group.species, group.call_count) for group in groups) == [("Dunnock", 2), ("House Sparrow", 2)]


def test_the_same_scientific_name_under_two_common_names_is_one_group():
    groups = fold_heard_calls([call(0, "House Sparrow"), call(1, "Haussperling", scientific_name="Passer domesticus")])
    assert len(groups) == 1 and groups[0].call_count == 2


def test_the_picture_is_the_strongest_call_birdnet_can_still_serve():
    groups = fold_heard_calls(
        [call(0, confidence=0.6, birdnet_id=10), call(1, confidence=0.97, birdnet_id=None), call(2, confidence=0.8, birdnet_id=12)]
    )
    assert groups[0].best_confidence == 0.97
    assert groups[0].best_heard == T0 + timedelta(minutes=1)
    assert groups[0].best_birdnet_id == 12


def test_a_group_with_no_servable_call_has_no_picture():
    assert fold_heard_calls([call(0, birdnet_id=None)])[0].best_birdnet_id is None


def test_calls_arrive_in_any_order():
    assert fold_heard_calls([call(9), call(0), call(4)])[0].call_count == 3


@pytest_asyncio.fixture
async def client():
    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await close_db()


@pytest.fixture(autouse=True)
def restore_settings():
    saved = (
        settings.auth.enabled,
        settings.public_access.enabled,
        settings.public_access.show_audio,
        settings.public_access.show_camera_names,
    )
    yield
    (
        settings.auth.enabled,
        settings.public_access.enabled,
        settings.public_access.show_audio,
        settings.public_access.show_camera_names,
    ) = saved


async def seed(rows: list[tuple[datetime, str, float, str, int, str, int]]):
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for stamp, species, confidence, source, birdnet_id, scientific, hidden in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name, is_hidden)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    stamp.replace(tzinfo=None).isoformat(sep=" "),
                    species,
                    confidence,
                    source,
                    json.dumps({"detectionId": birdnet_id, "nm": source}),
                    scientific,
                    hidden,
                ),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_heard_groups_fold_the_window_and_skip_hidden_calls(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await seed(
        [
            (now - timedelta(minutes=30), "House Sparrow", 0.7, "patiocam", 1, "Passer domesticus", 0),
            (now - timedelta(minutes=25), "House Sparrow", 0.9, "patiocam", 2, "Passer domesticus", 0),
            (now - timedelta(minutes=20), "Dunnock", 0.95, "patiocam", 3, "Prunella modularis", 1),
            (now - timedelta(days=3), "House Sparrow", 0.9, "patiocam", 4, "Passer domesticus", 0),
        ]
    )

    response = await client.get(
        "/api/audio/heard-groups",
        params={"start_date": (now - timedelta(hours=1)).isoformat(), "end_date": now.isoformat()},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["call_count"] == 2
    assert payload["truncated"] is False
    assert payload["gap_seconds"] == 600
    [group] = payload["groups"]
    assert group["species"] == "House Sparrow"
    assert group["scientific_name"] == "Passer domesticus"
    assert group["call_count"] == 2
    assert group["best_birdnet_id"] == 2
    assert group["source_name"] == "patiocam"


@pytest.mark.asyncio
async def test_heard_groups_hide_source_names_from_guests_when_camera_names_are_private(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    settings.public_access.show_audio = True
    settings.public_access.show_camera_names = False
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await seed([(now - timedelta(minutes=5), "House Sparrow", 0.9, "patiocam", 1, "Passer domesticus", 0)])

    response = await client.get(
        "/api/audio/heard-groups",
        params={"start_date": (now - timedelta(hours=1)).isoformat(), "end_date": now.isoformat()},
    )

    assert response.status_code == 200, response.text
    assert response.json()["groups"][0]["source_name"] is None
    assert "patiocam" not in response.text


@pytest.mark.asyncio
async def test_heard_groups_refuse_guests_when_audio_is_not_shared(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    settings.public_access.show_audio = False
    now = datetime.now(timezone.utc)

    response = await client.get(
        "/api/audio/heard-groups",
        params={"start_date": (now - timedelta(hours=1)).isoformat(), "end_date": now.isoformat()},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_heard_groups_refuse_a_window_longer_than_three_months(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime.now(timezone.utc)

    response = await client.get(
        "/api/audio/heard-groups",
        params={"start_date": (now - timedelta(days=120)).isoformat(), "end_date": now.isoformat()},
    )

    assert response.status_code == 422
