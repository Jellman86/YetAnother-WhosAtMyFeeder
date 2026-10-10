from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services.audio.heard_groups import ConfirmedVisit, HeardCall, attribute_calls, fold_heard_calls

T0 = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


def call(minutes: float, species: str = "House Sparrow", confidence: float = 0.8, birdnet_id: int | None = 1, **extra):
    return HeardCall(
        timestamp=T0 + timedelta(minutes=minutes),
        species=species,
        scientific_name=extra.get(
            "scientific_name", {"House Sparrow": "Passer domesticus", "Dunnock": "Prunella modularis"}.get(species)
        ),
        confidence=confidence,
        birdnet_id=birdnet_id,
        source_name=extra.get("source_name", "patiocam"),
        mapping_keys=frozenset(extra.get("keys", {"patiocam"})),
    )


def visit(visit_id: str, start_minute: float, end_minute: float, camera: str = "birdcam") -> ConfirmedVisit:
    return ConfirmedVisit(
        visit_id=visit_id,
        start=T0 + timedelta(minutes=start_minute),
        end=T0 + timedelta(minutes=end_minute),
        camera_name=camera,
        scientific_key="prunella modularis",
        names=frozenset({"dunnock"}),
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
        [
            call(0, confidence=0.6, birdnet_id=10),
            call(1, confidence=0.97, birdnet_id=None),
            call(2, confidence=0.8, birdnet_id=12),
        ]
    )
    assert groups[0].best_confidence == 0.97
    assert groups[0].best_heard == T0 + timedelta(minutes=1)
    assert groups[0].best_birdnet_id == 12


def test_a_group_with_no_servable_call_has_no_picture():
    assert fold_heard_calls([call(0, birdnet_id=None)])[0].best_birdnet_id is None


def test_calls_arrive_in_any_order():
    assert fold_heard_calls([call(9), call(0), call(4)])[0].call_count == 3


def test_the_default_bout_matches_the_default_correlation_window():
    groups = fold_heard_calls([call(0), call(5), call(10.5)])
    assert [group.call_count for group in groups] == [1, 2]


def test_only_calls_inside_the_widened_visit_count_on_it():
    calls = [call(minute, "Dunnock") for minute in (-6, -4, 0, 1, 4, 8, 20)]
    matched, rest = attribute_calls(calls, [visit("v1", 0, 1)], window_seconds=300, camera_audio_mapping={})
    assert matched == {"v1": 4}, "-4, 0, 1 and 4 minutes are within five minutes of the visit"
    assert [round((c.timestamp - T0).total_seconds() / 60) for c in rest] == [-6, 8, 20]


def test_a_bout_running_past_a_visit_is_split_at_its_edge():
    calls = [call(minute, "Dunnock") for minute in range(0, 31, 2)]
    matched, rest = attribute_calls(calls, [visit("v1", 0, 0.5)], window_seconds=300, camera_audio_mapping={})
    assert matched == {"v1": 3}
    assert [group.call_count for group in fold_heard_calls(rest)] == [13]


def test_another_species_never_counts_on_a_visit():
    matched, rest = attribute_calls(
        [call(0, "House Sparrow")], [visit("v1", 0, 1)], window_seconds=300, camera_audio_mapping={}
    )
    assert matched == {} and len(rest) == 1


def test_a_common_name_matches_when_the_call_has_no_scientific_name():
    matched, _ = attribute_calls(
        [call(0, "Dunnock", scientific_name=None)], [visit("v1", 0, 1)], window_seconds=300, camera_audio_mapping={}
    )
    assert matched == {"v1": 1}


def test_a_call_counts_once_on_the_nearest_visit():
    calls = [call(3, "Dunnock")]
    matched, _ = attribute_calls(
        calls, [visit("early", 0, 1), visit("late", 4, 5)], window_seconds=300, camera_audio_mapping={}
    )
    assert matched == {"late": 1}


def test_a_microphone_not_mapped_to_the_camera_does_not_count():
    calls = [call(0, "Dunnock", keys={"nestcam"}), call(0.5, "Dunnock", keys={"patiocam"})]
    matched, rest = attribute_calls(
        calls, [visit("v1", 0, 1)], window_seconds=300, camera_audio_mapping={"birdcam": "patiocam"}
    )
    assert matched == {"v1": 1}
    assert rest[0].mapping_keys == frozenset({"nestcam"})


def test_a_wildcard_or_missing_mapping_accepts_any_microphone():
    calls = [call(0, "Dunnock", keys={"nestcam"})]
    for mapping in ({}, {"birdcam": "*"}):
        matched, _ = attribute_calls(calls, [visit("v1", 0, 1)], window_seconds=300, camera_audio_mapping=mapping)
        assert matched == {"v1": 1}


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
    assert payload["gap_seconds"] == 300
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


@pytest.mark.asyncio
async def test_heard_groups_count_calls_on_the_confirmed_visit_they_support(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    saved_window = settings.frigate.audio_correlation_window_seconds
    saved_mapping = dict(settings.frigate.camera_audio_mapping)
    settings.frigate.audio_correlation_window_seconds = 300
    settings.frigate.camera_audio_mapping = {}
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        seen = now - timedelta(minutes=40)
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name, scientific_name, common_name, audio_confirmed, is_hidden)
                   VALUES ('evt_dunnock', 'birdcam', ?, 1, 0.9, 'Dunnock', 'Prunella modularis',
                           'Prunella modularis', 'Dunnock', 1, 0)""",
                (seen.replace(tzinfo=None).isoformat(sep=" "),),
            )
            await db.commit()
        await seed(
            [
                (seen + timedelta(minutes=minute), "Dunnock", 0.9, "patiocam", 100 + index, "Prunella modularis", 0)
                for index, minute in enumerate((1, 3, 12, 14))
            ]
        )

        response = await client.get(
            "/api/audio/heard-groups",
            params={"start_date": (now - timedelta(hours=1)).isoformat(), "end_date": now.isoformat()},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["call_count"] == 4
        assert [(item["visit_id"], item["call_count"]) for item in payload["matched_visits"]] == [("evt_dunnock", 2)]
        assert [(group["species"], group["call_count"]) for group in payload["groups"]] == [("Dunnock", 2)]
    finally:
        settings.frigate.audio_correlation_window_seconds = saved_window
        settings.frigate.camera_audio_mapping = saved_mapping
