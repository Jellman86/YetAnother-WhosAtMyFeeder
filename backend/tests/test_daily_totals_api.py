"""The Leaderboard and species charts reach back past retention through daily totals (#949)."""

import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

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


class FixedDatetime(datetime):
    @classmethod
    def combine(cls, day, clock, tzinfo=None):
        return datetime.combine(day, clock, tzinfo)

    @classmethod
    def now(cls, tz=None):
        instant = NOW.replace(tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else NOW


async def _capture(db, event, at, species, *, favourite=False):
    cursor = await db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
            frigate_event, camera_name, scientific_name, common_name, is_hidden)
        VALUES (?, 0, 0.9, ?, ?, ?, 'birdcam', ?, ?, 0)""",
        (at, species, species, event, species, species),
    )
    if favourite:
        await db.execute("INSERT INTO detection_favorites (detection_id) VALUES (?)", (cursor.lastrowid,))


@pytest_asyncio.fixture
async def client(migrated_history_db, monkeypatch):
    import app.database as database_module
    from app.main import app
    from app.routers import events, species, stats

    async with aiosqlite.connect(migrated_history_db) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        # 10 Feb: three Blackbird captures in two visits and a Great Tit, one Blackbird kept as a favourite.
        await _capture(db, "old-bb-1", "2036-02-10 08:00:00", "Turdus merula", favourite=True)
        await _capture(db, "old-bb-2", "2036-02-10 08:00:30", "Turdus merula")
        await _capture(db, "old-bb-3", "2036-02-10 10:00:00", "Turdus merula")
        await _capture(db, "old-gt-1", "2036-02-10 09:00:00", "Parus major")
        # 20 Feb is inside retention and read from its rows.
        await _capture(db, "new-bb-1", "2036-02-20 08:00:00", "Turdus merula")
        await _capture(db, "new-bb-2", "2036-02-20 12:00:00", "Turdus merula")
        await db.commit()
        repo = DailyTotalsRepository(db)
        await repo.seal_before(CUTOFF, zone=timezone.utc, now=NOW)
        await repo.delete_older_than(CUTOFF, preserve_favorites=True)

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
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(events, "batch_check_clips", lambda ids: _no_clips(ids))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)


async def _no_clips(ids):
    return {}


def _counts(body):
    return {point["bucket_start"][:10]: point["count"] for point in body["points"] if point["count"]}


@pytest.mark.asyncio
async def test_the_all_time_chart_reaches_back_past_retention_without_counting_a_kept_capture_twice(client):
    response = await client.get("/api/stats/detections/timeline?span=all")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bucket"] == "day"
    # The kept favourite on 10 Feb is inside that day's total, not added to it.
    assert _counts(body) == {"2036-02-10": 4, "2036-02-20": 2}
    assert body["total_count"] == 6
    assert body["daily_totals"] == {"totals_through": "2036-02-10", "complete_from": None, "partial": True}


@pytest.mark.asyncio
async def test_a_chart_inside_retention_reports_no_daily_totals(client):
    body = (await client.get("/api/stats/detections/timeline?span=week")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"] == {"totals_through": None, "complete_from": None, "partial": False}


@pytest.mark.asyncio
async def test_a_rolling_window_that_opens_mid_way_through_a_sealed_day_does_not_take_its_whole_total(
    client, monkeypatch
):
    # Thirty days back from noon on 11 March opens at noon on 10 February, after that day's captures.
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2036, 3, 11, 12, 0))
    body = (await client.get("/api/stats/detections/timeline?span=month")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"]["totals_through"] is None


@pytest.mark.asyncio
async def test_compare_lines_take_the_same_daily_totals(client):
    body = (await client.get("/api/stats/detections/timeline?span=all&compare_species=Turdus%20merula")).json()
    line = {
        point["bucket_start"][:10]: point["count"] for point in body["compare_series"][0]["points"] if point["count"]
    }
    assert line == {"2036-02-10": 3, "2036-02-20": 2}


@pytest.mark.asyncio
async def test_species_trends_count_sealed_days_and_stored_captures_once_each(client):
    response = await client.get("/api/species/Turdus%20merula/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_sightings"] == 5
    assert body["monthly_distribution"][1] == 5
    assert sum(body["daily_distribution"]) == 5
    # Time of day needs a capture time, which a daily total does not have.
    assert sum(body["hourly_distribution"]) == 2
    assert body["history_first_day"] == "2036-02-10"
    assert body["daily_totals"]["totals_through"] == "2036-02-10"


@pytest.mark.asyncio
async def test_a_species_seen_only_before_retention_still_has_its_history(client):
    response = await client.get("/api/species/Parus%20major/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_sightings"] == 1
    assert body["recent_sightings"] == []
    assert body["first_seen"] is None


@pytest.mark.asyncio
async def test_a_guest_sees_no_daily_totals_older_than_the_shared_window(client, monkeypatch):
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    from app.main import app

    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")
    body = (await client.get("/api/stats/detections/timeline?span=all")).json()
    assert _counts(body) == {"2036-02-20": 2}
    assert body["daily_totals"]["totals_through"] is None
    assert (await client.get("/api/species/Parus%20major/stats")).status_code == 404
