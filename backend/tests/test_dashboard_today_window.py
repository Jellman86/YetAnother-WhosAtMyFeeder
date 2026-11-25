"""The Dashboard's Today reads one window everywhere it counts (#1097).

The day summary, Needs your call and the species checks beside it all answer for the same
stretch: from local midnight in the zone ``X-Timezone`` names, else ``TZ``, else UTC, to now.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.main import app
from app.routers import audio, events, species, stats
from app.services.nearby_species_service import NearbyLookup
from app.utils import public_access

pytestmark = pytest.mark.usefixtures("history_pool")

# 20:00 UTC on 10 March: 01:30 on the 11th in India, 21:00 on the 10th in Berlin.
NOW = datetime(2034, 3, 10, 20, 0)
THRESHOLD = 0.6
INDIA = {"X-Timezone": "Asia/Kolkata"}


class FixedDatetime(datetime):
    @classmethod
    def combine(cls, day, clock, tzinfo=None):
        return datetime.combine(day, clock, tzinfo)

    @classmethod
    def now(cls, tz=None):
        instant = NOW.replace(tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else NOW


def _clock(monkeypatch, now: datetime) -> None:
    monkeypatch.setattr(sys.modules[__name__], "NOW", now)


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.classification, "threshold", THRESHOLD)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    monkeypatch.setattr(events, "utc_naive_now", lambda: NOW)
    monkeypatch.setattr(stats, "utc_naive_now", lambda: NOW)
    for module in (public_access, species, audio):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    monkeypatch.setattr(
        species.nearby_species_service,
        "lookup",
        AsyncMock(return_value=NearbyLookup(report=None, current=False, configured=False)),
    )
    monkeypatch.setenv("TZ", "UTC")
    await _clear()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
        await _clear()


async def _clear() -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM lost_captures WHERE frigate_event LIKE 'dtw-%'")
        await db.execute("DELETE FROM species_daily_totals WHERE day = '2034-03-10'")
        await db.execute("DELETE FROM daily_totals_days WHERE day = '2034-03-10'")
        await db.commit()


async def _seed(event: str, at: datetime, *, name: str = "European Robin", score: float = 0.9, scientific=None):
    scientific = scientific if scientific is not None else ("Erithacus rubecula" if name == "European Robin" else None)
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged, scientific_name, common_name)
            VALUES (?, 1, ?, ?, ?, ?, 'birdcam', 0, 0, ?, ?)""",
            (at.isoformat(sep=" "), score, name, name, event, scientific, name),
        )
        await db.commit()


async def _seed_call(identifier: str, at: datetime, name: str = "European Robin") -> None:
    async with get_db() as db:
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, scientific_name, confidence, sensor_id, raw_data)
            VALUES (?, ?, ?, 0.9, 'mic', ?)""",
            (at.isoformat(sep=" "), name, "Erithacus rubecula", json.dumps({"detectionId": identifier})),
        )
        await db.commit()


async def _established_robin() -> None:
    """Enough history that the robin is a regular, not a new species waiting on the owner."""
    for index in range(5):
        await _seed(f"history-{index}", NOW - timedelta(days=20, hours=index))


def _local_midnight(zone: str) -> datetime:
    local = NOW.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _ok(response: httpx.Response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


# The hourly chart ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("zone", ["Asia/Kolkata", "Asia/Kathmandu", "Australia/Adelaide", "America/St_Johns"])
async def test_a_capture_just_after_local_midnight_is_in_todays_first_hour(client, zone):
    # In India 18:40 UTC is 00:10, but its UTC hour starts at 23:30 the day before.
    midnight = _local_midnight(zone)
    assert midnight + timedelta(minutes=10) < NOW
    await _seed("after-midnight", midnight + timedelta(minutes=10))
    await _seed("before-midnight", midnight - timedelta(minutes=10))

    today = _ok(await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": zone}))
    assert today["window_start"] == midnight.isoformat() + "Z"
    assert today["total_count"] == 1
    assert today["hourly_distribution"][0] == 1
    assert sum(today["hourly_distribution"]) == 1

    rolling = _ok(await client.get("/api/stats/daily-summary", headers={"X-Timezone": zone}))
    assert rolling["hourly_distribution"][0] == 1
    assert rolling["hourly_distribution"][23] == 1


@pytest.mark.asyncio
async def test_hours_skipped_by_a_spring_clock_change_stay_empty(client, monkeypatch):
    # London moves to BST at 01:00 UTC on 26 March 2034: 00:30 UTC is 00:30, 01:10 UTC is 02:10.
    _clock(monkeypatch, datetime(2034, 3, 26, 12, 0))
    await _seed("gmt", datetime(2034, 3, 26, 0, 30))
    await _seed("bst", datetime(2034, 3, 26, 1, 10), name="Wren", scientific="Troglodytes troglodytes")
    today = _ok(await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": "Europe/London"}))
    assert today["window_start"] == "2034-03-26T00:00:00Z"
    hours = today["hourly_distribution"]
    assert (hours[0], hours[1], hours[2]) == (1, 0, 1)
    assert today["hourly_visits"][0] == 1
    assert today["hourly_visits"][2] == 1


@pytest.mark.asyncio
async def test_a_guest_today_starts_no_earlier_than_the_shared_utc_day(client, monkeypatch):
    # Before UTC midnight, Tokyo's Today began after the shared UTC day did, so it is not narrowed.
    _clock(monkeypatch, datetime(2034, 3, 10, 16, 0))  # 01:00 on the 11th in Tokyo
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")
    await _seed("tokyo-today", datetime(2034, 3, 10, 15, 30))
    summary = _ok(await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": "Asia/Tokyo"}))
    assert summary["window_start"] == "2034-03-10T15:00:00Z"
    assert summary["total_count"] == 1

    # Past UTC midnight, the shared day starts after the viewer's: the summary says from when it counted.
    _clock(monkeypatch, datetime(2034, 3, 11, 0, 30))  # 09:30 on the 11th in Tokyo
    await _seed("tokyo-before-utc-midnight", datetime(2034, 3, 10, 23, 0))
    await _seed("tokyo-after-utc-midnight", datetime(2034, 3, 11, 0, 10))
    narrowed = _ok(await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": "Asia/Tokyo"}))
    assert narrowed["window_start"] == "2034-03-11T00:00:00Z"
    assert narrowed["total_count"] == 1


# Needs your call ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_review_queue_today_holds_only_todays_waiting_captures(client):
    await _established_robin()
    # India's Today began at 18:30 UTC.
    await _seed("unknown-yesterday", datetime(2034, 3, 10, 18, 0), name="Unknown Bird")
    await _seed("low-yesterday", datetime(2034, 3, 10, 12, 0), score=THRESHOLD - 0.1)
    await _seed("unknown-today", datetime(2034, 3, 10, 18, 40), name="Unknown Bird")
    await _seed("low-today", datetime(2034, 3, 10, 19, 50), score=THRESHOLD - 0.1)

    today = _ok(await client.get("/api/events/review-queue?window=today", headers=INDIA))
    assert today["window_start"] == "2034-03-10T18:30:00Z"
    assert today["window_end"] == "2034-03-10T20:00:00Z"
    assert today["total"] == 2
    assert [item["event"]["frigate_event"] for item in today["items"]] == ["unknown-today", "low-today"]

    rolling = _ok(await client.get("/api/events/review-queue", headers=INDIA))
    assert rolling["window_start"] == "2034-03-09T20:00:00Z"
    assert rolling["total"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("window", ["rolling", "today"])
async def test_needs_your_call_and_the_unresolved_figure_count_the_same_captures(client, window):
    await _established_robin()
    await _seed("unknown-yesterday", datetime(2034, 3, 10, 18, 0), name="Unknown Bird")
    await _seed("unknown-today", datetime(2034, 3, 10, 18, 40), name="Unknown Bird")
    await _seed("on-threshold", datetime(2034, 3, 10, 19, 0), score=THRESHOLD)
    await _seed("low-today", datetime(2034, 3, 10, 19, 50), score=THRESHOLD - 0.1)

    summary = _ok(await client.get(f"/api/stats/daily-summary?window={window}", headers=INDIA))
    queue = _ok(await client.get(f"/api/events/review-queue?window={window}", headers=INDIA))
    assert queue["window_start"] == summary["window_start"]
    assert queue["window_end"] == summary["window_end"]
    assert queue["total"] == summary["unresolved_count"]


@pytest.mark.asyncio
async def test_a_new_species_waits_beside_todays_captures_and_counts_once(client):
    # A new species is waiting whenever it was first seen in the last fortnight, in either window,
    # so the queue holds it beside Unresolved rather than inside it. One seen today below the
    # threshold is both, and counts once.
    await _established_robin()
    await _seed("unknown-today", datetime(2034, 3, 10, 18, 40), name="Unknown Bird")
    await _seed("hoopoe-3-days-ago", NOW - timedelta(days=3), name="Eurasian Hoopoe", scientific="Upupa epops")
    await _seed("wren-today-shaky", datetime(2034, 3, 10, 19, 0), name="Wren", scientific="Troglodytes", score=0.3)

    summary = _ok(await client.get("/api/stats/daily-summary?window=today", headers=INDIA))
    queue = _ok(await client.get("/api/events/review-queue?window=today", headers=INDIA))
    assert summary["unresolved_count"] == 2
    assert queue["total"] == 3
    reasons = {item["event"]["frigate_event"]: item["reason"] for item in queue["items"]}
    assert reasons == {
        "unknown-today": "unknown_species",
        "hoopoe-3-days-ago": "new_species",
        "wren-today-shaky": "new_species",
    }


@pytest.mark.asyncio
async def test_the_review_queue_refuses_a_window_it_does_not_know(client):
    response = await client.get("/api/events/review-queue?window=week")
    assert response.status_code == 422


# The species checks -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_seen_leaderboard_today_counts_from_local_midnight(client):
    await _seed("robin-yesterday", datetime(2034, 3, 10, 18, 0))
    await _seed("robin-today", datetime(2034, 3, 10, 18, 40))
    await _seed("robin-yesterday-same-time", datetime(2034, 3, 9, 19, 0))

    today = _ok(await client.get("/api/leaderboard/species?span=today", headers=INDIA))
    assert today["span"] == "today"
    assert today["window_start"].startswith("2034-03-10T18:30:00")
    assert [(row["species"], row["window_count"]) for row in today["species"]] == [("European Robin", 1)]
    # Yesterday until the same clock time: 18:30 UTC on the 9th to 20:00 UTC on the 9th.
    assert today["species"][0]["window_prev_count"] == 1

    day = _ok(await client.get("/api/leaderboard/species?span=day", headers=INDIA))
    assert day["species"][0]["window_count"] == 2


@pytest.mark.asyncio
async def test_the_heard_leaderboard_today_counts_from_local_midnight(client):
    await _seed_call("call-yesterday", datetime(2034, 3, 10, 18, 0))
    await _seed_call("call-today", datetime(2034, 3, 10, 18, 40))

    today = _ok(await client.get("/api/audio/species?span=today", headers=INDIA))
    assert today["span"] == "today"
    assert today["window_start"].startswith("2034-03-10T18:30:00")
    assert [(row["species"], row["heard_count"]) for row in today["species"]] == [("European Robin", 1)]

    day = _ok(await client.get("/api/audio/species?span=day", headers=INDIA))
    assert day["species"][0]["heard_count"] == 2


@pytest.mark.asyncio
async def test_a_guest_leaderboard_today_never_reaches_before_the_shared_day(client, monkeypatch):
    _clock(monkeypatch, datetime(2034, 3, 11, 0, 30))  # 09:30 on the 11th in Tokyo
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")
    await _seed("robin-before-utc-midnight", datetime(2034, 3, 10, 23, 0))
    await _seed("robin-after-utc-midnight", datetime(2034, 3, 11, 0, 10))

    seen = _ok(await client.get("/api/leaderboard/species?span=today", headers={"X-Timezone": "Asia/Tokyo"}))
    assert seen["window_start"].startswith("2034-03-11T00:00:00")
    assert seen["species"][0]["window_count"] == 1


# One half-open window ------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("window", "start"),
    [("today", datetime(2034, 3, 10, 18, 30)), ("rolling", datetime(2034, 3, 9, 20, 0))],
)
async def test_every_count_takes_the_window_start_and_leaves_its_end_to_the_next_read(client, window, start):
    # [window_start, window_end): a capture at the very start counts, one at the very end does not,
    # in the figures, the hours, the species, Unresolved, the latest capture and Needs your call.
    await _established_robin()
    await _seed("at-start", start, name="Unknown Bird")
    await _seed("inside", datetime(2034, 3, 10, 19, 0), score=THRESHOLD - 0.1)
    await _seed("at-end", NOW, name="Unknown Bird")

    summary = _ok(await client.get(f"/api/stats/daily-summary?window={window}", headers=INDIA))
    assert summary["window_start"] == start.isoformat() + "Z"
    assert summary["window_end"] == NOW.isoformat() + "Z"
    assert summary["total_count"] == 2
    assert sum(summary["hourly_distribution"]) == 2
    assert sum(species["count"] for species in summary["top_species"]) == 2
    assert summary["visit_count"] == 2
    assert sum(summary["hourly_visits"]) == 2
    assert summary["unresolved_count"] == 2
    assert summary["latest_detection"]["frigate_event"] == "inside"

    queue = _ok(await client.get(f"/api/events/review-queue?window={window}", headers=INDIA))
    assert queue["total"] == 2
    assert [item["event"]["frigate_event"] for item in queue["items"]] == ["at-start", "inside"]


@pytest.mark.asyncio
async def test_a_guest_window_ends_where_the_shared_day_does(client, monkeypatch):
    # With no earlier days shared, a guest's history is the UTC day, start inclusive.
    _clock(monkeypatch, datetime(2034, 3, 11, 0, 30))  # 09:30 on the 11th in Tokyo
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")
    await _seed("at-utc-midnight", datetime(2034, 3, 11, 0, 0))
    await _seed("just-before", datetime(2034, 3, 10, 23, 59, 59))
    summary = _ok(await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": "Asia/Tokyo"}))
    assert summary["window_start"] == "2034-03-11T00:00:00Z"
    assert summary["window_end"] == "2034-03-11T00:30:00Z"
    assert summary["total_count"] == 1
    assert summary["latest_detection"]["frigate_event"] == "at-utc-midnight"


@pytest.mark.asyncio
async def test_at_midnight_todays_queue_drops_yesterdays_captures_and_keeps_a_new_species(client, monkeypatch):
    # 23:59 in India is 18:29 UTC; a minute after midnight is 18:31 UTC.
    await _established_robin()
    await _seed("unknown-before-midnight", datetime(2034, 3, 10, 18, 0), name="Unknown Bird")
    await _seed("hoopoe-4-days-ago", datetime(2034, 3, 6, 12, 0), name="Eurasian Hoopoe", scientific="Upupa epops")

    _clock(monkeypatch, datetime(2034, 3, 10, 18, 29))
    before = _ok(await client.get("/api/events/review-queue?window=today", headers=INDIA))
    assert before["window_start"] == "2034-03-09T18:30:00Z"
    assert {item["event"]["frigate_event"] for item in before["items"]} == {
        "unknown-before-midnight",
        "hoopoe-4-days-ago",
    }

    _clock(monkeypatch, datetime(2034, 3, 10, 18, 31))
    after = _ok(await client.get("/api/events/review-queue?window=today", headers=INDIA))
    assert after["window_start"] == "2034-03-10T18:30:00Z"
    assert [item["event"]["frigate_event"] for item in after["items"]] == ["hoopoe-4-days-ago"]
    assert after["total"] == 1


# The species checks beside the day ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_todays_species_checks_count_what_the_leaderboard_does_and_the_day_what_is_stored(client):
    # Needs your call's species checks read the Leaderboard's Today (span=today), and link to it:
    # stored captures and captures Frigate lost, never a sealed day's total. The day's figures count
    # the stored captures a person can open. Both start at the same local midnight.
    await _seed("robin-today", datetime(2034, 3, 10, 18, 40))
    async with get_db() as db:
        for event, at in (("dtw-lost-today", "2034-03-10 19:10:00"), ("dtw-lost-yesterday", "2034-03-10 18:10:00")):
            await db.execute(
                """INSERT INTO lost_captures (frigate_event, detection_time, species_key, scientific_name,
                    display_name, lost_at) VALUES (?, ?, 'name:european robin', 'Erithacus rubecula', 'European Robin', ?)""",
                (event, at, at),
            )
        # The instance's whole UTC day of the 10th is sealed with captures no longer stored.
        await db.execute(
            "INSERT INTO daily_totals_days (day, sealed_at, complete) VALUES ('2034-03-10', '2034-03-10 19:30:00', 1)"
        )
        await db.execute(
            """INSERT INTO species_daily_totals (day, species_key, scientific_name, common_name, display_name,
                capture_count, visit_count) VALUES ('2034-03-10', 'name:dunnock', 'Prunella modularis', 'Dunnock', 'Dunnock', 4, 2)"""
        )
        await db.commit()

    board = _ok(await client.get("/api/leaderboard/species?span=today", headers=INDIA))
    summary = _ok(await client.get("/api/stats/daily-summary?window=today", headers=INDIA))

    assert datetime.fromisoformat(board["window_start"].replace("Z", "+00:00")) == datetime(
        2034, 3, 10, 18, 30, tzinfo=timezone.utc
    )
    assert summary["window_start"] == "2034-03-10T18:30:00Z"
    # The Leaderboard counts the stored capture and the one Frigate lost today, not yesterday's.
    assert [(row["species"], row["window_count"]) for row in board["species"]] == [("European Robin", 2)]
    # The day counts the capture that is stored.
    assert [(row["species"], row["count"]) for row in summary["top_species"]] == [("European Robin", 1)]
    # A sealed total counts in neither.
    assert all(row["species"] != "Dunnock" for row in board["species"] + summary["top_species"])


@pytest.mark.asyncio
@pytest.mark.parametrize("window", ["rolling", "today"])
async def test_a_new_species_at_or_after_the_window_end_waits_for_the_next_read(client, window):
    # Needs your call is as of window_end, exclusive: a species first stamped then, or later, is not
    # yet new to this read, while a newcomer from four days ago still waits.
    await _established_robin()
    await _seed("hoopoe-4-days-ago", datetime(2034, 3, 6, 12, 0), name="Eurasian Hoopoe", scientific="Upupa epops")
    await _seed("wren-at-end", NOW, name="Wren", scientific="Troglodytes troglodytes")
    await _seed("nuthatch-after-end", NOW + timedelta(minutes=1), name="Nuthatch", scientific="Sitta europaea")
    # A newcomer seen before the window ends and again at its end waits by its earlier sighting.
    await _seed("siskin-before-end", datetime(2034, 3, 10, 19, 0), name="Siskin", scientific="Spinus spinus")
    await _seed("siskin-at-end", NOW, name="Siskin", scientific="Spinus spinus")

    queue = _ok(await client.get(f"/api/events/review-queue?window={window}", headers=INDIA))
    newcomers = {
        item["event"]["frigate_event"]: item["species_sightings"]
        for item in queue["items"]
        if item["reason"] == "new_species"
    }
    assert newcomers == {"hoopoe-4-days-ago": 1, "siskin-before-end": 1}
    assert queue["total"] == 2
