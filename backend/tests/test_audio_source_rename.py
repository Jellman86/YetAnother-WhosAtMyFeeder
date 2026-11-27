"""Renaming a source in BirdNET-Go keeps one entry with all of its calls (#1111)."""

from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.audio_history_repository import AudioHistoryRepository
from app.services.audio.source_backfill import resolve_pending_audio_sources, start_background_audio_source_backfill

pytestmark = pytest.mark.usefixtures("history_pool")

NODE = "BirdNET-Go Garden"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


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
        dict(settings.frigate.camera_audio_mapping),
    )
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled, settings.public_access.enabled, mapping = saved
    settings.frigate.camera_audio_mapping = mapping


def payload(name: str | None, source_id: str | None = None, *, node: str | None = NODE, **extra) -> dict:
    data: dict = {"CommonName": "Robin", "ScientificName": "Erithacus rubecula", **extra}
    if name is not None:
        data["sourceName"] = name
    if source_id is not None:
        data["sourceId"] = source_id
    if node is not None:
        data["SourceNode"] = node
    return data


async def store(calls: list[tuple[timedelta, str | None, dict]]) -> None:
    """Store calls through the ingest repository, as MQTT would, each ``age`` before now."""
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()
        repo = AudioHistoryRepository(db)
        for age, sensor, data in calls:
            await repo.insert_audio_detection(
                timestamp=NOW - age,
                species="Robin",
                confidence=0.9,
                sensor_id=sensor,
                raw_data=data,
                scientific_name="Erithacus rubecula",
            )


async def store_legacy(calls: list[tuple[timedelta, str]]) -> None:
    """Rows from before BirdNET-Go reported ids: a name and nothing else."""
    async with get_db() as db:
        repo = AudioHistoryRepository(db)
        for age, name in calls:
            await repo.insert_audio_detection(
                timestamp=NOW - age,
                species="Robin",
                confidence=0.9,
                sensor_id=name,
                raw_data={"nm": name},
                scientific_name="Erithacus rubecula",
            )


async def summary_sources(client: httpx.AsyncClient, **params) -> list[dict]:
    response = await client.get("/api/audio/summary", params={"days": 30, **params})
    assert response.status_code == 200, response.text
    return response.json()["sources"]


@pytest.mark.asyncio
async def test_a_renamed_source_is_one_entry_named_by_its_latest_name_with_its_whole_history(client):
    await store(
        [
            (timedelta(days=3), "birdcam", payload("birdcam", "rtsp_3af0d74c")),
            (timedelta(days=2), "birdcam", payload("birdcam", "rtsp_3af0d74c")),
            (timedelta(hours=2), "Feeder", payload("Feeder", "rtsp_3af0d74c")),
        ]
    )

    sources = await summary_sources(client)
    assert [(s["source_name"], s["source_id"], s["count"]) for s in sources] == [("Feeder", "rtsp_3af0d74c", 3)]

    history = (await client.get("/api/audio/history", params={"days": 30})).json()
    # Each call keeps the name it was heard under; only the Sources list follows the rename.
    assert sorted(item["source_name"] for item in history["items"]) == ["Feeder", "birdcam", "birdcam"]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["birdcam", "Feeder", "rtsp_3af0d74c"])
async def test_filtering_by_any_name_or_the_id_finds_the_whole_source(client, text):
    await store(
        [
            (timedelta(days=2), "birdcam", payload("birdcam", "rtsp_3af0d74c")),
            (timedelta(hours=2), "Feeder", payload("Feeder", "rtsp_3af0d74c")),
            (timedelta(hours=1), "nestcam", payload("nestcam", "rtsp_0d6c2ad3")),
        ]
    )

    for route in ("/api/audio/history", "/api/audio/summary"):
        filtered = (await client.get(route, params={"days": 30, "source": text})).json()
        assert filtered["total"] == 2, route
    searched = (await client.get("/api/audio/history", params={"days": 30, "search": text})).json()
    assert searched["total"] == 2


@pytest.mark.asyncio
async def test_two_ids_that_share_a_name_stay_two_sources_told_apart_by_id(client):
    # The stream's URL changed and BirdNET-Go hashed it to a new id; the name stayed.
    await store(
        [
            (timedelta(days=5), "birdcam", payload("birdcam", "rtsp_old00000")),
            (timedelta(days=4), "birdcam", payload("birdcam", "rtsp_old00000")),
            (timedelta(hours=1), "birdcam", payload("birdcam", "rtsp_new11111")),
        ]
    )

    sources = await summary_sources(client)
    assert [(s["source_name"], s["source_id"], s["count"]) for s in sources] == [
        ("birdcam", "rtsp_old00000", 2),
        ("birdcam", "rtsp_new11111", 1),
    ]
    summary = (await client.get("/api/audio/summary", params={"days": 30})).json()
    assert summary["source_count"] == 2


@pytest.mark.asyncio
async def test_rows_from_before_ids_join_the_source_their_name_belonged_to(client):
    await store(
        [
            (timedelta(days=2), "birdcam", payload("birdcam", "rtsp_3af0d74c")),
            (timedelta(hours=1), "Feeder", payload("Feeder", "rtsp_3af0d74c")),
        ]
    )
    await store_legacy([(timedelta(days=20), "birdcam"), (timedelta(days=21), "birdcam")])

    sources = await summary_sources(client)
    assert [(s["source_name"], s["count"]) for s in sources] == [("Feeder", 4)]


@pytest.mark.asyncio
async def test_rows_from_before_ids_stay_apart_when_two_sources_carried_their_name(client):
    await store(
        [
            (timedelta(days=5), "birdcam", payload("birdcam", "rtsp_old00000")),
            (timedelta(hours=1), "birdcam", payload("birdcam", "rtsp_new11111")),
        ]
    )
    await store_legacy([(timedelta(days=20), "birdcam")])

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["source_id"] or "", s["count"]) for s in sources) == [
        ("birdcam", "", 1),
        ("birdcam", "rtsp_new11111", 1),
        ("birdcam", "rtsp_old00000", 1),
    ]


@pytest.mark.asyncio
async def test_a_renamed_sound_card_and_nested_older_payloads_keep_their_source(client):
    await store(
        [
            (timedelta(days=3), "Default Audio Device", payload("Default Audio Device", "audio_card_22a9b331")),
            (timedelta(hours=1), "Shed mic", payload("Shed mic", "audio_card_22a9b331")),
            (
                timedelta(days=4),
                "Garden",
                {"SourceNode": NODE, "Source": {"id": "rtsp_nested", "displayName": "Garden"}, "CommonName": "Robin"},
            ),
            (
                timedelta(hours=2),
                "Garden fence",
                {
                    "SourceNode": NODE,
                    "Source": {"id": "rtsp_nested", "displayName": "Garden fence"},
                    "CommonName": "Robin",
                },
            ),
        ]
    )

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["count"]) for s in sources) == [("Garden fence", 2), ("Shed mic", 2)]


@pytest.mark.asyncio
async def test_the_same_id_from_two_birdnet_go_installs_is_two_sources(client):
    await store(
        [
            (timedelta(hours=2), "Default Audio Device", payload("Default Audio Device", "audio_card_22a9b331")),
            (
                timedelta(hours=1),
                "Default Audio Device",
                payload("Default Audio Device", "audio_card_22a9b331", node="BirdNET-Go Shed"),
            ),
        ]
    )

    assert len(await summary_sources(client)) == 2


async def hide(*sensors: str) -> None:
    async with get_db() as db:
        await db.execute(
            f"UPDATE audio_detections SET is_hidden = 1 WHERE sensor_id IN ({','.join('?' for _ in sensors)})",
            sensors,
        )
        await db.commit()


@pytest.mark.asyncio
async def test_the_hidden_view_names_and_finds_a_renamed_source_by_its_hidden_calls(client):
    await store(
        [
            (timedelta(days=2), "Before", payload("Before", "rtsp_hidden")),
            (timedelta(hours=2), "After", payload("After", "rtsp_hidden")),
            (timedelta(hours=1), "nestcam", payload("nestcam", "rtsp_0d6c2ad3")),
        ]
    )
    await hide("Before", "After")

    sources = await summary_sources(client, only_hidden="true")
    assert [(s["source_name"], s["count"]) for s in sources] == [("After", 2)]
    for text in ("Before", "After"):
        hidden = (
            await client.get("/api/audio/history", params={"days": 30, "only_hidden": "true", "source": text})
        ).json()
        assert hidden["total"] == 2, text
        assert {item["source_name"] for item in hidden["items"]} == {"Before", "After"}


@pytest.mark.asyncio
async def test_two_installs_whose_sound_cards_share_a_name_and_an_id_are_told_apart(client):
    card = "audio_card_22a9b331"
    await store(
        [
            (timedelta(hours=2), "Default Audio Device", payload("Default Audio Device", card, node="Shed")),
            (timedelta(hours=1), "Default Audio Device", payload("Default Audio Device", card, node="House")),
        ]
    )

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["source_id"], s["source_node"]) for s in sources) == [
        ("Default Audio Device", card, "House"),
        ("Default Audio Device", card, "Shed"),
    ]


@pytest.mark.asyncio
async def test_hiding_a_call_never_credits_an_older_call_to_another_stream(client):
    await store(
        [
            (timedelta(hours=3), "Reused", payload("Reused", "rtsp_aaaa1111")),
            (timedelta(hours=2), "Reused-b", payload("Reused", "rtsp_bbbb2222")),
        ]
    )
    await store_legacy([(timedelta(days=3), "Reused")])

    async def legacy_entries() -> list[tuple]:
        return sorted((s["source_id"] or "", s["count"]) for s in await summary_sources(client))

    before = await legacy_entries()
    await hide("Reused-b")
    # Stream B's call is hidden, but it still says B carried the name: the older call stays apart.
    assert await legacy_entries() == [("", 1), ("rtsp_aaaa1111", 1)]
    assert before == [("", 1), ("rtsp_aaaa1111", 1), ("rtsp_bbbb2222", 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first,second",
    [
        (payload("Feeder", "rtsp_a", node="Shed"), payload("Perch", "rtsp_a", node="shed")),
        (payload("Feeder", "rtsp_A", node="Shed"), payload("Perch", "rtsp_a", node="Shed")),
    ],
)
async def test_installs_and_ids_that_differ_only_in_case_are_different_sources(client, first, second):
    await store([(timedelta(hours=2), "Feeder", first), (timedelta(hours=1), "Perch", second)])

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["source_id"], s["source_node"], s["count"]) for s in sources) == sorted(
        [
            ("Feeder", first["sourceId"], first["SourceNode"], 1),
            ("Perch", second["sourceId"], second["SourceNode"], 1),
        ]
    )


@pytest.mark.asyncio
async def test_a_source_renamed_to_its_own_id_is_listed_under_that_name(client):
    await store(
        [
            (timedelta(hours=2), "Feeder", payload("Feeder", "rtsp_a")),
            (timedelta(hours=1), "rtsp_a", payload("rtsp_a", "rtsp_a")),
        ]
    )
    assert [(s["source_name"], s["count"]) for s in await summary_sources(client)] == [("rtsp_a", 2)]


@pytest.mark.asyncio
async def test_an_older_call_named_like_a_source_that_was_named_by_its_id_stays_apart(client):
    # Shed's rtsp_a was named "rtsp_a" and rtsp_b took that name too: the older call is neither's.
    await store(
        [
            (timedelta(hours=3), "rtsp_a", payload("rtsp_a", "rtsp_a", node="Shed")),
            (timedelta(hours=2), "rtsp_a", payload("rtsp_a", "rtsp_b", node="Shed")),
        ]
    )
    await store_legacy([(timedelta(days=3), "rtsp_a")])
    sources = sorted((s["source_id"] or "", s["count"]) for s in await summary_sources(client))
    assert sources == [("", 1), ("rtsp_a", 1), ("rtsp_b", 1)]


@pytest.mark.asyncio
async def test_a_call_whose_id_was_refused_never_joins_another_installs_source(client):
    # Shed's stream once carried the name "rtsp shed". A House call sends that text as its id, which
    # is refused for its space; with no name of its own, it must not be counted as Shed's.
    await store(
        [
            (timedelta(hours=3), "rtsp shed", payload("rtsp shed", "rtsp_a", node="Shed")),
            (timedelta(hours=2), "Feeder", payload("Feeder", "rtsp_a", node="Shed")),
            (timedelta(hours=1), "rtsp shed", payload(None, "rtsp shed", node="House")),
            (timedelta(minutes=30), "Feeder", payload("Feeder", None, node="House")),
        ]
    )

    sources = await summary_sources(client)
    assert ("Feeder", "rtsp_a", "Shed", 2) in {
        (s["source_name"], s["source_id"], s["source_node"], s["count"]) for s in sources
    }
    assert sum(s["count"] for s in sources) == 4
    async with get_db() as db:
        async with db.execute(
            "SELECT source_node, source_id, source_name FROM audio_detections WHERE source_node = 'House'"
        ) as cursor:
            assert sorted(await cursor.fetchall(), key=str) == [("House", None, "Feeder"), ("House", None, None)]
    # Filtering by Shed's id finds Shed's calls only.
    filtered = (await client.get("/api/audio/history", params={"days": 30, "source": "rtsp_a"})).json()
    assert filtered["total"] == 2


@pytest.mark.asyncio
async def test_unnamed_calls_with_refused_ids_stay_on_their_own_installs(client):
    await store(
        [
            (timedelta(hours=2), "rtsp bad", payload(None, "rtsp bad", node="Shed")),
            (timedelta(hours=1), "rtsp bad", payload(None, "rtsp bad", node="House")),
        ]
    )

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["source_id"], s["source_node"], s["count"]) for s in sources) == [
        ("Unknown source", None, "House", 1),
        ("Unknown source", None, "Shed", 1),
    ]


@pytest.mark.asyncio
async def test_a_named_call_with_a_refused_id_never_joins_a_source_by_its_name(client):
    # Not a call from before ids: it sent an id, which was refused, so its name proves nothing.
    await store(
        [
            (timedelta(hours=3), "Old", payload("Old", "rtsp_a", node="Shed")),
            (timedelta(hours=2), "Current", payload("Current", "rtsp_a", node="Shed")),
            (timedelta(hours=1), "Old", payload("Old", "rtsp bad", node=None)),
        ]
    )

    sources = await summary_sources(client)
    assert sorted((s["source_name"], s["source_id"], s["source_node"], s["count"]) for s in sources) == [
        ("Current", "rtsp_a", "Shed", 2),
        ("Unknown source", None, None, 1),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_view", [False, True])
async def test_filtering_by_a_listed_source_finds_exactly_the_calls_it_counts(client, hidden_view):
    await store(
        [
            (timedelta(hours=4), "Feeder", payload("Feeder", "rtsp_a", node="Shed")),
            (timedelta(hours=3), "Perch", payload("Perch", "rtsp_a", node="Shed")),
            (timedelta(hours=2), "nestcam", payload("nestcam", "rtsp_b", node="Shed")),
            # A call whose payload names no source.
            (timedelta(hours=5), None, payload(None, None, node=None)),
        ]
    )
    await store_legacy([(timedelta(days=2), "Perch")])
    view = {"only_hidden": "true"} if hidden_view else {}
    if hidden_view:
        async with get_db() as db:
            await db.execute("UPDATE audio_detections SET is_hidden = 1")
            await db.commit()

    sources = await summary_sources(client, **view)
    assert [(s["source_name"], s["source_id"], s["count"]) for s in sources] == [
        ("Perch", "rtsp_a", 3),
        ("nestcam", "rtsp_b", 1),
        ("Unknown source", None, 1),
    ]
    # "Unknown source" stands for no name at all, so there is nothing to filter it by.
    for entry in sources[:2]:
        for text in (entry["source_name"], entry["source_id"]):
            params = {"days": 30, **view}
            history = (await client.get("/api/audio/history", params={**params, "source": text, "limit": 50})).json()
            searched = (await client.get("/api/audio/history", params={**params, "search": text, "limit": 50})).json()
            summary = (await client.get("/api/audio/summary", params={**params, "source": text})).json()
            grid = (await client.get("/api/audio/activity-heatmap", params={**params, "source": text})).json()
            assert history["total"] == searched["total"] == summary["total"] == entry["count"], text
            assert grid["total_count"] == entry["count"], text
            assert len(history["items"]) == entry["count"], text


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/api/audio/history", "/api/audio/activity-heatmap"])
async def test_a_view_that_names_no_source_never_reads_the_sources(client, route, monkeypatch):
    await store([(timedelta(hours=1), "Feeder", payload("Feeder", "rtsp_a"))])
    reads: list[dict] = []
    original = AudioHistoryRepository.load_audio_source_directory

    async def counted(self, **kwargs):
        reads.append(kwargs)
        return await original(self, **kwargs)

    monkeypatch.setattr(AudioHistoryRepository, "load_audio_source_directory", counted)
    assert (await client.get(route, params={"days": 1})).status_code == 200
    assert (await client.get(route, params={"days": 1, "species": "Robin"})).status_code == 200
    assert reads == []
    assert (await client.get(route, params={"days": 1, "source": "Feeder"})).status_code == 200
    assert len(reads) == 1


async def store_as_an_older_release(age: timedelta, sensor: str, data: dict, number: int) -> None:
    """A call written by a release from before source tracking, against the upgraded database."""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO audio_detections (
                   timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id,
                   species_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_event_id) DO NOTHING""",
            (
                (NOW - age).strftime("%Y-%m-%d %H:%M:%S"),
                "Robin",
                0.9,
                sensor,
                json.dumps(data),
                "Erithacus rubecula",
                f"{sensor.casefold()}:{number}",
                None,
            ),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_calls_an_older_release_stored_are_read_once_after_upgrading_again(client):
    await store([(timedelta(hours=2), "Current", payload("Current", "rtsp_x", node="Quark"))])
    # Rolled back to an older image, which stores a call and leaves the source columns empty.
    await store_as_an_older_release(timedelta(hours=1), "Rollback", payload("Rollback", "rtsp_x", node="Quark"), 7)

    assert await resolve_pending_audio_sources() == 1

    sources = await summary_sources(client)
    assert [(s["source_name"], s["source_id"], s["count"]) for s in sources] == [("Rollback", "rtsp_x", 2)]
    for text in ("Current", "Rollback", "rtsp_x"):
        assert (await client.get("/api/audio/history", params={"days": 30, "source": text})).json()["total"] == 2
    # Read once: nothing is left to read, and running again reads nothing.
    assert await resolve_pending_audio_sources() == 0


@pytest.mark.asyncio
async def test_a_filter_naming_more_than_a_thousand_stored_identities_still_answers(client):
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()
        repo = AudioHistoryRepository(db)
        for index in range(1_100):
            await repo.insert_audio_detection(
                timestamp=NOW - timedelta(minutes=index),
                species="Robin",
                confidence=0.9,
                sensor_id=f"Feeder {index}",
                raw_data=payload(f"Feeder {index}", "rtsp_0", node="Quark"),
                scientific_name="Erithacus rubecula",
            )

    assert [(s["source_id"], s["count"]) for s in await summary_sources(client)] == [("rtsp_0", 1_100)]
    for probe in ({"source": "rtsp_0"}, {"search": "Feeder"}):
        params = {"days": 30, **probe}
        history = await client.get("/api/audio/history", params=params)
        summary = await client.get("/api/audio/summary", params=params)
        grid = await client.get("/api/audio/activity-heatmap", params=params)
        assert (history.status_code, summary.status_code, grid.status_code) == (200, 200, 200), probe
        assert history.json()["total"] == summary.json()["total"] == grid.json()["total_count"] == 1_100, probe


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_view", [False, True])
async def test_a_source_filter_also_matches_a_calls_own_stored_text_as_it_always_has(client, hidden_view):
    """The Sources list keeps the two apart; the filter, as before, also reads each call's own text."""
    await store(
        [
            (timedelta(hours=2), "Current", payload("Current", "rtsp_x", node="Quark")),
            # Its id is refused, so it is an unknown source on Shed, though it was sent as "Current".
            (timedelta(hours=1), "Current", payload("Current", "rtsp bad", node="Shed")),
        ]
    )
    view = {"only_hidden": "true"} if hidden_view else {}
    if hidden_view:
        async with get_db() as db:
            await db.execute("UPDATE audio_detections SET is_hidden = 1")
            await db.commit()

    sources = await summary_sources(client, **view)
    assert sorted((s["source_name"], s["source_node"], s["count"]) for s in sources) == [
        ("Current", "Quark", 1),
        ("Unknown source", "Shed", 1),
    ]
    # The id names only the listed source; the name is also in the Shed call's own payload.
    params = {"days": 30, **view}
    assert (await client.get("/api/audio/history", params={**params, "source": "rtsp_x"})).json()["total"] == 1
    assert (await client.get("/api/audio/history", params={**params, "source": "Current"})).json()["total"] == 2


@pytest.mark.asyncio
async def test_calls_left_by_an_older_release_are_read_in_small_batches(client):
    await store([])
    for number in range(5):
        await store_as_an_older_release(
            timedelta(minutes=number + 1), f"Mic {number}", payload(f"Mic {number}", "rtsp_m", node="Quark"), number
        )

    assert await resolve_pending_audio_sources(batch_size=2) == 5
    sources = await summary_sources(client)
    assert [(s["source_name"], s["source_id"], s["count"]) for s in sources] == [("Mic 0", "rtsp_m", 5)]


@pytest.mark.asyncio
async def test_a_failed_read_at_startup_is_reported_and_never_stops_the_app(monkeypatch):
    async def broken(self, limit):
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(AudioHistoryRepository, "resolve_pending_sources", broken)
    await start_background_audio_source_backfill()
