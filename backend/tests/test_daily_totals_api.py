"""The Leaderboard and species charts reach back past retention through daily totals (#949)."""

import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.utils import public_access

NOW = datetime(2036, 2, 25, 12, 0)
CUTOFF = datetime(2036, 2, 11, 6, 0)

# 10 Feb: three Blackbird captures in two visits and a Great Tit, one Blackbird kept as a favourite.
# 20 Feb is inside retention and read from its rows.
DEFAULT_ROWS = [
    ("old-bb-1", "2036-02-10 08:00:00", "Turdus merula", True),
    ("old-bb-2", "2036-02-10 08:00:30", "Turdus merula", False),
    ("old-bb-3", "2036-02-10 10:00:00", "Turdus merula", False),
    ("old-gt-1", "2036-02-10 09:00:00", "Parus major", False),
    ("new-bb-1", "2036-02-20 08:00:00", "Turdus merula", False),
    ("new-bb-2", "2036-02-20 12:00:00", "Turdus merula", False),
]


class FixedDatetime(datetime):
    @classmethod
    def combine(cls, day, clock, tzinfo=None):
        return datetime.combine(day, clock, tzinfo)

    @classmethod
    def now(cls, tz=None):
        instant = NOW.replace(tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else NOW


async def _capture(db, event, at, species, favourite=False, species_id=None):
    cursor = await db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
            frigate_event, camera_name, scientific_name, common_name, is_hidden, species_id)
        VALUES (?, 0, 0.9, ?, ?, ?, 'birdcam', ?, ?, 0, ?)""",
        (at, species, species, event, species, species, species_id),
    )
    if favourite:
        await db.execute("INSERT INTO detection_favorites (detection_id) VALUES (?)", (cursor.lastrowid,))


@pytest_asyncio.fixture
async def serve(migrated_history_db, monkeypatch):
    """Seed rows, seal and delete before ``cutoff`` in ``zone``, then serve the app on that history."""
    import app.database as database_module
    from app.main import app
    from app.routers import events, species, stats

    @asynccontextmanager
    async def private_history():
        async with aiosqlite.connect(migrated_history_db) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            yield connection

    shared = database_module.get_db
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "get_db", None) is shared:
            monkeypatch.setattr(module, "get_db", private_history)
    for module in (stats, species, public_access):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(events, "batch_check_clips", lambda ids: _no_clips(ids))

    clients = []

    async def start(rows=DEFAULT_ROWS, *, zone="UTC", cutoff=CUTOFF, tracking_started=None):
        monkeypatch.setenv("TZ", zone)
        async with private_history() as db:
            for row in rows:
                await _capture(db, *row)
            if tracking_started:
                await db.execute("UPDATE daily_totals_tracking SET started_at = ?", (tracking_started,))
            await db.commit()
            await DailyTotalsRepository(db).seal_and_delete_older_than(
                cutoff, zone=ZoneInfo(zone), now=NOW, preserve_favorites=True
            )
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client, private_history

    try:
        yield start
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
        for client in clients:
            await client.aclose()


async def _no_clips(ids):
    return {}


def _counts(body):
    return {point["bucket_start"][:10]: point["count"] for point in body["points"] if point["count"]}


def _as_guest(monkeypatch, days):
    from app.main import app

    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", days)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")


@pytest.mark.asyncio
async def test_the_all_time_chart_reaches_back_past_retention_without_counting_a_kept_capture_twice(serve):
    client, _db = await serve()
    response = await client.get("/api/stats/detections/timeline?span=all")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bucket"] == "day"
    # The kept favourite on 10 Feb is inside that day's total, not added to it.
    assert _counts(body) == {"2036-02-10": 4, "2036-02-20": 2}
    assert body["total_count"] == 6
    assert body["daily_totals"] == {"totals_through": "2036-02-10", "complete_from": None, "partial": False}


@pytest.mark.asyncio
async def test_days_from_before_tracking_began_are_reported_as_possibly_low(serve):
    client, _db = await serve(tracking_started="2036-02-15 00:00:00")
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert body["daily_totals"] == {"totals_through": "2036-02-10", "complete_from": None, "partial": True}


@pytest.mark.asyncio
async def test_a_chart_inside_retention_reports_no_daily_totals(serve):
    client, _db = await serve()
    body = (await client.get("/api/stats/detections/timeline?span=week")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"] == {"totals_through": None, "complete_from": None, "partial": False}


@pytest.mark.asyncio
async def test_a_rolling_window_that_opens_mid_way_through_a_sealed_day_does_not_take_its_whole_total(
    serve, monkeypatch
):
    client, _db = await serve()
    # Thirty days back from noon on 11 March opens at noon on 10 February, after that day's captures.
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2036, 3, 11, 12, 0))
    body = (await client.get("/api/stats/detections/timeline?span=month")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"]["totals_through"] is None


@pytest.mark.asyncio
async def test_a_half_hour_zone_counts_each_capture_once(serve):
    # In Kolkata (UTC+05:30) 18:45 UTC on 10 Feb is 00:15 on the 11th. Cleanup seals the 11th, keeps
    # that capture as a favourite, and leaves the 10th live. The capture is in the 11th's total and
    # must not be counted again from its UTC hour, which begins on the 10th.
    client, _db = await serve(
        [
            ("ist-1", "2036-02-10 18:45:00", "Turdus merula", True),
            ("ist-2", "2036-02-10 19:30:00", "Turdus merula", False),
        ],
        zone="Asia/Kolkata",
        cutoff=datetime(2036, 2, 10, 19, 0),
    )
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert body["total_count"] == 2
    stats = (await client.get("/api/species/Turdus%20merula/stats")).json()
    assert stats["total_sightings"] == 2


@pytest.mark.asyncio
async def test_compare_lines_take_the_same_daily_totals(serve):
    client, _db = await serve()
    body = (await client.get("/api/stats/detections/timeline?span=all&compare_species=Turdus%20merula")).json()
    line = {
        point["bucket_start"][:10]: point["count"] for point in body["compare_series"][0]["points"] if point["count"]
    }
    assert line == {"2036-02-10": 3, "2036-02-20": 2}


@pytest.mark.asyncio
async def test_a_renamed_species_keeps_its_sealed_days_by_catalogue_identity(serve):
    client, _db = await serve(
        [
            ("blue-old", "2036-02-10 08:00:00", "Parus caeruleus", False, 4242),
            ("blue-new", "2036-02-20 08:00:00", "Cyanistes caeruleus", False, 4242),
        ]
    )
    body = (await client.get("/api/stats/detections/timeline?span=all&compare_species=Cyanistes%20caeruleus")).json()
    line = {
        point["bucket_start"][:10]: point["count"] for point in body["compare_series"][0]["points"] if point["count"]
    }
    assert line == {"2036-02-10": 1, "2036-02-20": 1}
    stats = (await client.get("/api/species/Cyanistes%20caeruleus/stats")).json()
    assert stats["total_sightings"] == 2


@pytest.mark.asyncio
async def test_a_month_that_mixes_sealed_and_live_days_counts_each_species_once(serve, monkeypatch):
    client, _db = await serve(
        [*DEFAULT_ROWS, ("new-sitta", "2036-02-21 08:00:00", "Sitta europaea", False)],
    )
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2036, 9, 1, 12, 0))
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert body["bucket"] == "month"
    february = next(point for point in body["points"] if point["bucket_start"].startswith("2036-02"))
    # Blackbird and Great Tit from the sealed 10th, Blackbird and Nuthatch live: three species.
    assert february["unique_species"] == 3


@pytest.mark.asyncio
async def test_species_trends_count_sealed_days_and_stored_captures_once_each(serve):
    client, _db = await serve()
    response = await client.get("/api/species/Turdus%20merula/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_sightings"] == 5
    assert body["monthly_distribution"][1] == 5
    assert sum(body["daily_distribution"]) == 5
    # Time of day needs a capture time: it counts every stored capture, the kept favourite included.
    assert sum(body["hourly_distribution"]) == 3
    assert body["history_first_day"] == "2036-02-10"
    assert body["daily_totals"]["totals_through"] == "2036-02-10"


@pytest.mark.asyncio
async def test_a_species_with_no_sealed_days_says_nothing_about_daily_totals(serve):
    client, _db = await serve([*DEFAULT_ROWS, ("new-sitta", "2036-02-21 08:00:00", "Sitta europaea", False)])
    body = (await client.get("/api/species/Sitta%20europaea/stats")).json()
    assert body["daily_totals"] == {"totals_through": None, "complete_from": None, "partial": False}


@pytest.mark.asyncio
async def test_a_species_seen_only_before_retention_still_has_its_history(serve):
    client, _db = await serve()
    response = await client.get("/api/species/Parus%20major/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_sightings"] == 1
    assert body["recent_sightings"] == []
    assert body["first_seen"] is None


@pytest.mark.asyncio
async def test_a_capture_frigate_lost_still_counts_and_its_day_stays_correctable(serve):
    client, db_factory = await serve()
    async with db_factory() as db:
        assert await DailyTotalsRepository(db).delete_lost_capture("new-bb-2", zone=timezone.utc, now=NOW)
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert _counts(body) == {"2036-02-10": 4, "2036-02-20": 2}
    # The day was not sealed, so nothing claims its photos are gone.
    assert body["daily_totals"]["totals_through"] == "2036-02-10"
    stats = (await client.get("/api/species/Turdus%20merula/stats")).json()
    assert stats["total_sightings"] == 5
    # Hiding the capture still stored on the 20th is a correction the chart follows.
    async with db_factory() as db:
        await db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'new-bb-1'")
        await db.commit()
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert _counts(body) == {"2036-02-10": 4, "2036-02-20": 1}


@pytest.mark.asyncio
async def test_a_guest_sees_no_daily_totals_older_than_the_shared_window(serve, monkeypatch):
    client, _db = await serve()
    _as_guest(monkeypatch, 7)
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"]["totals_through"] is None
    assert (await client.get("/api/species/Parus%20major/stats")).status_code == 404


@pytest.mark.asyncio
async def test_a_guest_never_sees_a_sealed_day_that_began_before_the_shared_window(serve, monkeypatch):
    # In Berlin the sealed 10 Feb began at 23:00 UTC on the 9th; a guest's window opens at UTC midnight.
    client, _db = await serve(zone="Europe/Berlin")
    _as_guest(monkeypatch, 15)
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    # Not the sealed day's total of 4, which counts captures from before the window: only the
    # favourite still stored inside it, which a guest can already see.
    assert _counts(body) == {"2036-02-10": 1, "2036-02-20": 2}
    assert body["daily_totals"]["totals_through"] is None
    assert (await client.get("/api/species/Parus%20major/stats")).status_code == 404


@pytest.mark.asyncio
async def test_a_lost_capture_stored_again_counts_once_live_and_once_sealed(serve):
    client, db_factory = await serve()
    async with db_factory() as db:
        assert await DailyTotalsRepository(db).delete_lost_capture("new-bb-2", zone=timezone.utc, now=NOW)
        # Backfill or the end-event recovery stores the same Frigate event again.
        await _capture(db, "new-bb-2", "2036-02-20 12:00:00", "Turdus merula")
        await db.commit()
    assert _counts((await client.get("/api/stats/detections/timeline?span=all")).json())["2036-02-20"] == 2
    async with db_factory() as db:
        await DailyTotalsRepository(db).seal_and_delete_older_than(
            datetime(2036, 2, 21, 6, 0), zone=timezone.utc, now=NOW
        )
    assert _counts((await client.get("/api/stats/detections/timeline?span=all")).json())["2036-02-20"] == 2


@pytest.mark.asyncio
async def test_the_all_time_chart_starts_at_a_lost_capture_older_than_every_stored_one(serve):
    client, db_factory = await serve(
        [
            ("x1", "2036-02-20 08:00:00", "Turdus merula", False),
            ("x2", "2036-02-22 08:00:00", "Turdus merula", False),
        ],
        cutoff=datetime(2036, 1, 1),
    )
    async with db_factory() as db:
        assert await DailyTotalsRepository(db).delete_lost_capture("x1", zone=timezone.utc, now=NOW)
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert body["total_count"] == 2
    assert _counts(body) == {"2036-02-20": 1, "2036-02-22": 1}


@pytest.mark.asyncio
async def test_a_live_day_counts_a_species_seen_only_in_lost_captures(serve):
    client, db_factory = await serve([*DEFAULT_ROWS, ("new-gt", "2036-02-20 09:00:00", "Parus major", False)])
    async with db_factory() as db:
        assert await DailyTotalsRepository(db).delete_lost_capture("new-gt", zone=timezone.utc, now=NOW)
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    day = next(point for point in body["points"] if point["bucket_start"].startswith("2036-02-20"))
    assert (day["count"], day["unique_species"]) == (3, 2)


@pytest.mark.asyncio
async def test_a_species_whose_own_sealed_days_are_whole_is_not_called_possibly_low(serve):
    # The 9th began before tracking and may be low; the Great Tit was only seen on the whole 10th.
    client, _db = await serve(
        [("early-bb", "2036-02-09 08:00:00", "Turdus merula", False), *DEFAULT_ROWS],
        tracking_started="2036-02-09 12:00:00",
    )
    tit = (await client.get("/api/species/Parus%20major/stats")).json()
    assert tit["daily_totals"] == {"totals_through": "2036-02-10", "complete_from": None, "partial": False}
    blackbird = (await client.get("/api/species/Turdus%20merula/stats")).json()
    assert blackbird["daily_totals"]["partial"] is True
