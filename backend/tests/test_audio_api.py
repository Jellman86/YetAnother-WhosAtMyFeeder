from datetime import datetime, timedelta, timezone
import json
from app.repositories.audio_history_repository import AudioHistoryRepository

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.database import get_db
from app.config import settings
from app.routers.audio import AUDIO_SUPPRESSED_BY_MAPPING_HEADER
from app.utils.birdnet_payload import extract_audio_mapping_keys, parse_mapping_filter_values
from tests.audio_source_columns import fill_source_columns

pytestmark = pytest.mark.usefixtures("history_pool")


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_show_camera_names = settings.public_access.show_camera_names
    original_camera_audio_mapping = dict(settings.frigate.camera_audio_mapping)
    original_correlation_window = settings.frigate.audio_correlation_window_seconds
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.public_access.show_camera_names = original_show_camera_names
    settings.frigate.camera_audio_mapping = original_camera_audio_mapping
    settings.frigate.audio_correlation_window_seconds = original_correlation_window


async def _store_calls(rows: list[tuple[datetime, str | None, dict, int]]) -> None:
    """Replace the history with calls of (time, stored sensor, payload, hidden), source columns filled."""
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.executemany(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, is_hidden)
               VALUES (?, 'Robin', 0.9, ?, ?, ?)""",
            [
                (stamp.replace(tzinfo=None).isoformat(sep=" "), sensor, json.dumps(payload), hidden)
                for stamp, sensor, payload, hidden in rows
            ],
        )
        await db.commit()
        await fill_source_columns(db)


def _stream_call(stamp: datetime, name: str, source_id: str, hidden: int = 0) -> tuple:
    return (stamp, name, {"sourceName": name, "sourceId": source_id, "SourceNode": "Quark"}, hidden)


@pytest.mark.asyncio
async def test_audio_sources_lists_a_renamed_stream_once_linked_by_its_id(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    await _store_calls(
        [
            _stream_call(now - timedelta(days=1), "ESP32 v3.0", "rtsp_52d54d7d"),
            _stream_call(now - timedelta(hours=2), "ESP32 v3.0 X", "rtsp_52d54d7d"),
            _stream_call(now - timedelta(hours=1), "ESP32 v3.0 X", "rtsp_52d54d7d"),
            # The owner hid every call under the old name: it still says the stream was renamed.
            _stream_call(now - timedelta(days=1), "Reolink", "rtsp_68763a4d", hidden=1),
            _stream_call(now - timedelta(minutes=30), "Reolink TEST", "rtsp_68763a4d"),
        ]
    )

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    reolink, esp32 = response.json()

    assert esp32["source_name"] == "ESP32 v3.0 X"
    assert esp32["mapping_value"] == esp32["source_id"] == "rtsp_52d54d7d"
    assert esp32["source_node"] == "Quark"
    assert esp32["last_seen"] == "2026-11-28T08:00:00Z"
    assert "seen_count" not in esp32
    assert esp32["names"] == [
        {"name": "ESP32 v3.0 X", "last_seen": "2026-11-28T08:00:00Z", "current": True, "offer_link_by_id": False},
        {"name": "ESP32 v3.0", "last_seen": "2026-11-27T09:00:00Z", "current": False, "offer_link_by_id": True},
    ]
    assert reolink["source_name"] == "Reolink TEST"
    assert reolink["names"][1] == {"name": "Reolink", "last_seen": None, "current": False, "offer_link_by_id": True}


@pytest.mark.asyncio
async def test_audio_sources_offers_no_rename_for_a_name_a_stream_outside_the_page_still_carries(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    await _store_calls(
        [
            _stream_call(now - timedelta(days=2), "Garden", "rtsp_busy"),
            _stream_call(now - timedelta(hours=1), "Feeder", "rtsp_busy"),
            # A quiet stream, beyond the one entry asked for, still called Garden.
            _stream_call(now - timedelta(days=30), "Garden", "rtsp_quiet"),
        ]
    )

    response = await client.get("/api/audio/sources?limit=1")
    assert response.status_code == 200, response.text
    [busy] = response.json()
    assert busy["mapping_value"] == "rtsp_busy"
    assert [(name["name"], name["offer_link_by_id"]) for name in busy["names"]] == [
        ("Feeder", False),
        ("Garden", False),
    ]


@pytest.mark.asyncio
async def test_audio_sources_offers_an_earlier_name_in_the_spelling_its_calls_carried(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    await _store_calls(
        [
            _stream_call(now - timedelta(days=1), "Garden  Mic", "rtsp_a"),
            _stream_call(now - timedelta(hours=1), "Current", "rtsp_a"),
        ]
    )

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    [stream] = response.json()
    assert [(name["name"], name["offer_link_by_id"]) for name in stream["names"]] == [
        ("Current", False),
        ("Garden  Mic", True),
    ]


@pytest.mark.asyncio
async def test_audio_sources_offers_no_rename_when_one_stored_name_hides_two_spellings(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    day = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    await _store_calls(
        [
            _stream_call(day, "Garden  Mic", "rtsp_a"),
            _stream_call(day + timedelta(days=9), "Current", "rtsp_a"),
            _stream_call(day + timedelta(days=14), "Garden  Mic", "rtsp_a", hidden=1),
            _stream_call(day + timedelta(days=15), "Garden Mic", "rtsp_a", hidden=1),
        ]
    )

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    [stream] = response.json()
    assert stream["source_name"] == "Current"
    assert not any(name["offer_link_by_id"] for name in stream["names"])


@pytest.mark.asyncio
async def test_audio_sources_never_offers_a_later_hidden_name_as_an_earlier_one(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    await _store_calls(
        [
            _stream_call(datetime(2026, 11, 1, 9, tzinfo=timezone.utc), "Feeder", "rtsp_a"),
            _stream_call(datetime(2026, 11, 15, 9, tzinfo=timezone.utc), "Feeder X", "rtsp_a", hidden=1),
        ]
    )

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    [stream] = response.json()
    assert stream["source_name"] == "Feeder"
    assert not any(name["offer_link_by_id"] for name in stream["names"])


@pytest.mark.asyncio
async def test_audio_sources_names_every_install_sharing_an_id_beyond_the_page(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    card = "audio_card_22a9b331"
    await _store_calls(
        [
            (now, None, {"sourceId": card, "SourceNode": "House"}, 0),
            (now - timedelta(days=3), None, {"sourceId": card, "SourceNode": "Shed"}, 0),
        ]
    )

    response = await client.get("/api/audio/sources?limit=1")
    assert response.status_code == 200, response.text
    [house] = response.json()
    assert (house["source_name"], house["source_node"], house["installs_sharing_id"]) == (
        card,
        "House",
        ["House", "Shed"],
    )


@pytest.mark.asyncio
async def test_audio_sources_keeps_a_quiet_stream_behind_many_newer_calls(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    busy = [_stream_call(now - timedelta(seconds=index), "Feeder", "rtsp_busy") for index in range(250)]
    await _store_calls([_stream_call(now - timedelta(days=40), "Pond", "rtsp_quiet"), *busy])

    response = await client.get("/api/audio/sources?limit=20")
    assert response.status_code == 200, response.text
    assert [(item["source_name"], item["last_seen"]) for item in response.json()] == [
        ("Feeder", "2026-11-28T09:00:00Z"),
        ("Pond", "2026-10-19T09:00:00Z"),
    ]


@pytest.mark.asyncio
async def test_audio_sources_links_a_source_without_an_id_by_the_name_the_matcher_reads(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)
    payload = {"sourceName": "Garden  Mic"}
    await _store_calls([(now, "Garden  Mic", payload, 0)])

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    [garden] = response.json()
    assert (garden["source_name"], garden["mapping_value"], garden["source_id"]) == ("Garden  Mic", "Garden  Mic", None)
    # Saved as offered, the link matches the call it came from.
    _, keys = parse_mapping_filter_values(garden["mapping_value"])
    assert keys & extract_audio_mapping_keys("Garden  Mic", json.dumps(payload))


@pytest.mark.asyncio
async def test_audio_sources_names_a_stream_that_sent_no_name_by_its_id(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    await _store_calls([(datetime(2026, 11, 28, tzinfo=timezone.utc), None, {"sourceId": "rtsp_livepayload"}, 0)])

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    [stream] = response.json()
    assert (stream["source_name"], stream["mapping_value"]) == ("rtsp_livepayload", "rtsp_livepayload")


@pytest.mark.asyncio
async def test_guest_cannot_list_audio_sources_or_their_earlier_names(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    settings.public_access.show_camera_names = True
    response = await client.get("/api/audio/sources")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audio_history_filters_persisted_birdnet_detections(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"detectionId": 101, "nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"detectionId": 102, "nm": "Garden Mic", "src": "rtsp_garden"}),
            "Cyanistes caeruleus",
        ),
        (
            (now - timedelta(days=10)).isoformat(sep=" "),
            "Dunnock",
            0.7,
            "BirdCam",
            json.dumps({"detectionId": 103, "nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(
        "/api/audio/history",
        params={
            "days": 2,
            "species": "dun",
            "source": "BirdCam",
            "min_confidence": 0.8,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["species"] == "Dunnock"
    assert payload["items"][0]["source_name"] == "BirdCam"
    assert payload["items"][0]["birdnet_id"] == 101
    assert "scientific_name" not in payload["items"][0]


@pytest.mark.asyncio
async def test_audio_history_links_only_matching_automatic_video_classifications(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"birdcam": "BirdCam", "nestcam": "NestCam"}
    settings.frigate.audio_correlation_window_seconds = 300

    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM detections")
        await db.executemany(
            """INSERT INTO audio_detections
                   (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    now.isoformat(sep=" "),
                    "Woodpigeon",
                    0.92,
                    "BirdCam",
                    json.dumps({"detectionId": 201, "nm": "BirdCam"}),
                    "Columba palumbus",
                ),
                (
                    (now - timedelta(seconds=10)).isoformat(sep=" "),
                    "Woodpigeon",
                    0.89,
                    "NestCam",
                    json.dumps({"detectionId": 202, "nm": "NestCam"}),
                    "Columba palumbus",
                ),
            ],
        )
        detection_rows = [
            ("auto-match", "birdcam", 40, 0, 0, "completed", "Columba palumbus", 0.82),
            ("manual-closer", "birdcam", 5, 1, 0, "completed", "Columba palumbus", 0.99),
            ("hidden-closer", "birdcam", 8, 0, 1, "completed", "Columba palumbus", 0.99),
            ("wrong-camera", "nestcam", 3, 0, 0, "completed", "Columba palumbus", 0.98),
            ("wrong-species", "birdcam", 2, 0, 0, "completed", "Pica pica", 0.99),
            ("failed-video", "birdcam", 1, 0, 0, "failed", "Columba palumbus", 0.99),
        ]
        for event_id, camera, delta, manual, hidden, status, label, score in detection_rows:
            await db.execute(
                """INSERT INTO detections
                       (detection_time, detection_index, score, display_name, category_name,
                        frigate_event, camera_name, manual_tagged, is_hidden,
                        video_classification_status, video_classification_label,
                        video_classification_score)
                       VALUES (?, 1, 0.8, 'Bird', 'Bird', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    (now + timedelta(seconds=delta)).isoformat(sep=" "),
                    event_id,
                    camera,
                    manual,
                    hidden,
                    status,
                    label,
                    score,
                ),
            )
        await db.commit()

    response = await client.get("/api/audio/history", params={"days": 1, "limit": 10})
    assert response.status_code == 200, response.text
    items = {item["birdnet_id"]: item for item in response.json()["items"]}

    assert items[201]["matched_visual_event_id"] == "auto-match"
    assert items[202]["matched_visual_event_id"] == "wrong-camera"


@pytest.mark.asyncio
async def test_audio_summary_rolls_up_persisted_history(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Dunnock",
            0.82,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=1)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"Source": {"displayName": "Garden Mic"}}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()
        await fill_source_columns(db)

    response = await client.get("/api/audio/summary", params={"days": 7})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total"] == 3
    assert payload["species_count"] == 2
    assert payload["source_count"] == 2
    assert payload["top_species"][0]["species"] == "Dunnock"
    assert payload["top_species"][0]["count"] == 2
    # The grid's species choice asks for it by scientific name: the common name is translated.
    assert payload["top_species"][0]["scientific_name"] == "Prunella modularis"
    assert {item["date"] for item in payload["daily_counts"]} == {
        now.strftime("%Y-%m-%d"),
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    assert any(item["hour"] == 11 and item["count"] == 1 for item in payload["hourly_counts"])
    assert [item["source_name"] for item in payload["sources"]] == ["BirdCam", "Garden Mic"]


@pytest.mark.asyncio
async def test_audio_species_leaderboard_counts_window_and_prev(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        # Dunnock: two in the current 7-day window, one in the prior window.
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Dunnock",
            0.82,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=10)).isoformat(sep=" "),
            "Dunnock",
            0.71,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        # Blue Tit: one in the current window, none prior.
        (
            (now - timedelta(hours=3)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic"}),
            "Cyanistes caeruleus",
        ),
        # Robin: outside both windows — must be excluded.
        (
            (now - timedelta(days=20)).isoformat(sep=" "),
            "Robin",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Erithacus rubecula",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM taxonomy_cache")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/species", params={"span": "week"})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["span"] == "week"
    species = payload["species"]
    names = [item["species"] for item in species]
    assert names == ["Dunnock", "Blue Tit"]  # sorted by heard_count desc, Robin excluded

    dunnock = species[0]
    assert dunnock["heard_count"] == 2
    assert dunnock["heard_prev_count"] == 1
    assert dunnock["heard_delta"] == 1
    assert dunnock["heard_percent"] == 100.0
    assert dunnock["scientific_name"] == "Prunella modularis"
    assert dunnock["last_heard"] is not None

    blue_tit = species[1]
    assert blue_tit["heard_count"] == 1
    assert blue_tit["heard_prev_count"] == 0
    assert blue_tit["heard_percent"] == 0.0
    # The Robin 20 days ago reaches back past the prior week, so a trend can be claimed.
    assert payload["previous_window_complete"] is True
    assert payload["history_start"].endswith("Z")


@pytest.mark.asyncio
async def test_audio_species_leaderboard_has_no_trend_before_birdnet_history_covers_it(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for age in (timedelta(hours=1), timedelta(days=9)):
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, 'Dunnock', 0.9, 'BirdCam', '{}', 'Prunella modularis')""",
                ((now - age).isoformat(sep=" "),),
            )
        await db.commit()

    week = (await client.get("/api/audio/species", params={"span": "week"})).json()
    assert week["previous_window_complete"] is False
    month = (await client.get("/api/audio/species", params={"span": "month"})).json()
    assert month["previous_window_complete"] is False
    day = (await client.get("/api/audio/species", params={"span": "day"})).json()
    assert day["previous_window_complete"] is True
    everything = (await client.get("/api/audio/species", params={"span": "all"})).json()
    assert everything["previous_window_complete"] is False


@pytest.mark.asyncio
async def test_audio_species_leaderboard_all_span_counts_everything(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=40)).isoformat(sep=" "),
            "Dunnock",
            0.7,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Blue Tit",
            0.85,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic"}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM taxonomy_cache")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/species", params={"span": "all"})
    assert response.status_code == 200, response.text
    payload = response.json()

    by_name = {item["species"]: item for item in payload["species"]}
    assert by_name["Dunnock"]["heard_count"] == 2  # includes the 40-day-old row
    assert by_name["Dunnock"]["heard_prev_count"] == 0
    assert by_name["Dunnock"]["heard_delta"] == 2
    assert by_name["Blue Tit"]["heard_count"] == 1


@pytest.mark.asyncio
async def test_audio_context_supports_multi_source_camera_mapping(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"front": "BirdCam, Garden Mic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (target - timedelta(seconds=15)).isoformat(sep=" "),
            "Dunnock",
            0.81,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
        (
            (target + timedelta(seconds=12)).isoformat(sep=" "),
            "Blue Tit",
            0.74,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic", "src": "rtsp_garden"}),
            "Cyanistes caeruleus",
        ),
        (
            (target + timedelta(seconds=8)).isoformat(sep=" "),
            "Woodpigeon",
            0.7,
            "Other Mic",
            json.dumps({"nm": "Other Mic", "src": "rtsp_other"}),
            "Columba palumbus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={
            "timestamp": target.isoformat(),
            "camera": "front",
            "window_seconds": 60,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    species = [item["species"] for item in payload]
    assert "Dunnock" in species
    assert "Blue Tit" in species
    assert "Woodpigeon" not in species


@pytest.mark.asyncio
async def test_audio_context_matches_birdnet_source_name(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"front": "Patio Mic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    row = (
        target.isoformat(sep=" "),
        "Dunnock",
        0.81,
        "rtsp_livepayload",
        json.dumps({"sourceName": "Patio Mic", "sourceId": "rtsp_livepayload"}),
        "Prunella modularis",
    )

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            row,
        )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={
            "timestamp": target.isoformat(),
            "camera": "front",
            "window_seconds": 60,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["species"] for item in payload] == ["Dunnock"]


@pytest.mark.asyncio
async def test_event_audio_context_finds_late_audio_without_stored_audio_hint(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"birdcam": "BirdCam"}
    settings.frigate.audio_correlation_window_seconds = 45

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-late-audio-{int(target.timestamp())}"

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                audio_confirmed, audio_species, audio_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, NULL, NULL)
            """,
            (
                target.isoformat(sep=" "),
                1,
                0.51,
                "Unknown Bird",
                "Unknown Bird",
                event_id,
                "birdcam",
            ),
        )
        rows = [
            (
                (target - timedelta(seconds=30)).isoformat(sep=" "),
                "Common Kingfisher",
                0.86,
                "BirdCam",
                json.dumps({"detectionId": 26588, "nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Alcedo atthis",
            ),
            (
                (target + timedelta(seconds=10)).isoformat(sep=" "),
                "Blue Tit",
                0.91,
                "Other Mic",
                json.dumps({"detectionId": 26589, "nm": "Other Mic", "src": "rtsp_other"}),
                "Cyanistes caeruleus",
            ),
            (
                (target + timedelta(seconds=60)).isoformat(sep=" "),
                "Robin",
                0.93,
                "BirdCam",
                json.dumps({"detectionId": 26590, "nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Erithacus rubecula",
            ),
        ]
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(f"/api/audio/context/event/{event_id}")

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "timestamp": (target - timedelta(seconds=30)).isoformat(),
            "species": "Common Kingfisher",
            "confidence": 0.86,
            "sensor_id": "BirdCam",
            "source_name": None,
            "birdnet_id": 26588,
            "offset_seconds": -30,
            "scientific_name": "Alcedo atthis",
            "matches_visual": False,
        }
    ]
    # The fixture also seeds an "Other Mic" row, which this camera's mapping
    # excludes — the header reports that without breaking the established body.
    assert response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] == "1"


@pytest.mark.asyncio
async def test_event_audio_context_returns_not_found_for_unknown_event(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    response = await client.get("/api/audio/context/event/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_event_audio_context_does_not_expose_hidden_event_to_guest(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-hidden-audio-{int(target.timestamp())}"
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
            """,
            (
                target.isoformat(sep=" "),
                1,
                0.75,
                "Robin",
                "Robin",
                event_id,
                "birdcam",
            ),
        )
        await db.commit()

    response = await client.get(f"/api/audio/context/event/{event_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_audio_recent_replaces_locale_species_with_canonical_english(client: httpx.AsyncClient):
    """Regression for issue #46 — Dashboard 'Recent audio' must show the user's locale,
    not whatever language BirdNET-Go publishes in ``comName``. Mirrors the response-time
    transform already deployed for the species/leaderboard endpoints."""
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Домовый воробей",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name="Passer domesticus",
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
        assert "scientific_name" not in payload[0]
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_falls_back_when_taxa_id_missing(client: httpx.AsyncClient):
    """A detection with no ``scientific_name`` (or no matching taxonomy_cache row)
    must fall back to the stored species string — graceful degradation."""
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Dunnock",
                confidence=0.8,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name=None,
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload[0]["species"] == "Dunnock"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_resolves_via_translation_when_scientific_name_missing(client: httpx.AsyncClient):
    """Issue #46 follow-up — when BirdNET-Go publishes a non-English ``comName`` and
    no ``ScientificName``, the audio service stores ``scientific_name = None`` (or the
    raw locale string with no taxa_id). The localizer must still recover the canonical
    English name by matching the stored species text against ``taxonomy_translations``.
    """
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute("DELETE FROM taxonomy_translations")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        await db.execute(
            """INSERT INTO taxonomy_translations (taxa_id, language_code, common_name)
               VALUES (?, ?, ?)""",
            (12345, "ru", "Домовый воробей"),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Домовый воробей",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name=None,
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_resolves_via_common_name_when_scientific_name_is_locale_text(client: httpx.AsyncClient):
    """Issue #46 follow-up — when ``add_detection`` stored a non-Latin string as
    ``scientific_name`` (because iNaturalist couldn't resolve the BirdNET-Go locale
    comName), the cache row keyed by that string has ``taxa_id = NULL``. The
    localizer must still recover by matching the species text against
    ``taxonomy_cache.common_name`` for any row that *does* have a taxa_id.
    """
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        # Poisoned row: the locale comName got saved as scientific_name with no taxa_id.
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, NULL, NULL, 1, ?)""",
            ("Домовый воробей", datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="House Sparrow",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name="Домовый воробей",  # poisoned by ingest pre-fix
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_owner_can_hide_restore_audio_and_summary_excludes_hidden(client):
    from app.repositories.detection_repository import DetectionRepository

    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        repo = DetectionRepository(db)
        row_id = await AudioHistoryRepository(repo.db).insert_audio_detection(
            now, "Robin", 0.95, "mic", {}, source_event_id="hide-test"
        )
    response = await client.patch(f"/api/audio/history/{row_id}", json={"hidden": True})
    assert response.status_code == 200
    assert (await client.get("/api/audio/history")).json()["total"] == 0
    assert (await client.get("/api/audio/summary")).json()["total"] == 0
    async with get_db() as db:
        repo = DetectionRepository(db)
        assert (await AudioHistoryRepository(repo.db).get_audio_context(now, 30, None, 10))[0] == []
        assert (
            await AudioHistoryRepository(repo.db).get_audio_species_counts(
                window_start=now - timedelta(days=1),
                window_end=now + timedelta(days=1),
                prev_start=now - timedelta(days=2),
                prev_end=now - timedelta(days=1),
            )
            == []
        )
        assert await repo.delete_audio_detections_older_than(now + timedelta(days=1)) == 0
    assert (await client.patch(f"/api/audio/history/{row_id}", json={"hidden": False})).status_code == 200
    assert (await client.get("/api/audio/history")).json()["total"] == 1
    assert (await client.patch("/api/audio/history/999999999", json={"hidden": True})).status_code == 404
    await client.patch(f"/api/audio/history/{row_id}", json={"hidden": True})


@pytest.mark.asyncio
async def test_guest_cannot_hide_audio(client):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    response = await client.patch("/api/audio/history/1", json={"hidden": True})
    assert response.status_code in (401, 403)
    bulk_response = await client.patch("/api/audio/history/visibility", json={"ids": [1], "hidden": True})
    assert bulk_response.status_code in (401, 403)
    hidden_count_response = await client.get("/api/audio/history/hidden-count")
    assert hidden_count_response.status_code in (401, 403)
    hidden_history_response = await client.get("/api/audio/history", params={"only_hidden": "true"})
    assert hidden_history_response.status_code == 403


@pytest.mark.asyncio
async def test_owner_bulk_visibility_view_hidden_and_search(client):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        repo = AudioHistoryRepository(db)
        robin_id = await repo.insert_audio_detection(
            now - timedelta(minutes=3),
            "European Robin",
            0.92,
            "garden-mic",
            {"nm": "Garden Mic"},
            scientific_name="Erithacus rubecula",
            source_event_id="bulk-robin",
        )
        wren_id = await repo.insert_audio_detection(
            now - timedelta(minutes=2),
            "Eurasian Wren",
            0.88,
            "patio-mic",
            {"nm": "Patio Mic"},
            scientific_name="Troglodytes troglodytes",
            source_event_id="bulk-wren",
        )
        tit_id = await repo.insert_audio_detection(
            now - timedelta(minutes=1),
            "Blue Tit",
            0.91,
            "shed-mic",
            {"nm": "Shed Mic"},
            scientific_name="Cyanistes caeruleus",
            source_event_id="bulk-tit",
        )

    # Search matches common name, scientific name, and source name
    assert (await client.get("/api/audio/history", params={"search": "rubecula"})).json()["total"] == 1
    assert (await client.get("/api/audio/history", params={"search": "Patio Mic"})).json()["total"] == 1
    assert (await client.get("/api/audio/summary", params={"search": "Blue Tit"})).json()["total"] == 1

    # Bulk hide two calls
    bulk_hide = await client.patch(
        "/api/audio/history/visibility",
        json={"ids": [robin_id, wren_id, 999999999], "hidden": True},
    )
    assert bulk_hide.status_code == 200, bulk_hide.text
    assert bulk_hide.json() == {"updated_count": 2, "ids": [robin_id, wren_id], "hidden": True}

    assert (await client.get("/api/audio/history/hidden-count")).json() == {"hidden_count": 2}
    assert (await client.get("/api/audio/history")).json()["total"] == 1
    hidden_history = (await client.get("/api/audio/history", params={"only_hidden": "true"})).json()
    assert hidden_history["total"] == 2
    assert {item["id"] for item in hidden_history["items"]} == {robin_id, wren_id}
    assert (await client.get("/api/audio/summary", params={"only_hidden": "true"})).json()["total"] == 2

    # Bulk restore
    bulk_restore = await client.patch(
        "/api/audio/history/visibility",
        json={"ids": [robin_id, wren_id], "hidden": False},
    )
    assert bulk_restore.status_code == 200
    assert bulk_restore.json() == {"updated_count": 2, "ids": [robin_id, wren_id], "hidden": False}
    assert (await client.get("/api/audio/history/hidden-count")).json() == {"hidden_count": 0}
    assert (await client.get("/api/audio/history")).json()["total"] == 3
    assert tit_id > 0


@pytest.mark.asyncio
async def test_guest_search_does_not_leak_hidden_sensor_names(client):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    settings.public_access.show_audio = True
    settings.public_access.show_camera_names = False
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        repo = AudioHistoryRepository(db)
        await repo.insert_audio_detection(
            now - timedelta(minutes=1),
            "European Robin",
            0.95,
            "secret-backyard-mic",
            {"nm": "Secret Backyard"},
            scientific_name="Erithacus rubecula",
            source_event_id="guest-search-robin",
        )

    assert (await client.get("/api/audio/history", params={"search": "rubecula"})).json()["total"] == 1
    assert (await client.get("/api/audio/history", params={"search": "Secret Backyard"})).json()["total"] == 0
