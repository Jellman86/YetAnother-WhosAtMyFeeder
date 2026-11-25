"""Exact instants on the capture list and its count match the visit list's window (#1098)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.main import app
from app.routers import events
from app.utils import public_access

pytestmark = pytest.mark.usefixtures("history_pool")

NOW = datetime(2034, 3, 10, 23, 45)
ROWS = {
    "exact-old": ("2034-03-08 12:00:00", "Erithacus rubecula"),
    "exact-0": ("2034-03-09 23:30:00", "Erithacus rubecula"),
    "exact-1": ("2034-03-10 12:00:00", "Erithacus rubecula"),
    "exact-2": ("2034-03-10 22:30:00", "Parus major"),
    "exact-3": ("2034-03-10 23:30:00", "Turdus merula"),
    "exact-4": ("2034-03-10 23:40:00", "Prunella modularis"),
}


class FixedDatetime(datetime):
    @classmethod
    def combine(cls, day, clock, tzinfo=None):
        return datetime.combine(day, clock, tzinfo)

    @classmethod
    def now(cls, tz=None):
        instant = NOW.replace(tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else NOW


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    monkeypatch.setattr(events, "utc_naive_now", lambda: NOW)
    monkeypatch.setattr(public_access, "datetime", FixedDatetime)
    monkeypatch.setenv("TZ", "Europe/Berlin")
    async with get_db() as db:
        for event, (moment, species) in ROWS.items():
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, is_hidden, manual_tagged, scientific_name, common_name)
                VALUES (?, 1, 0.9, ?, ?, ?, 'birdcam', 0, 0, ?, ?)""",
                (moment, species, species, event, species, species),
            )
        await db.commit()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'exact-%'")
            await db.commit()


def _as_guest(monkeypatch, days: int) -> None:
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", days)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")


async def _events(client: httpx.AsyncClient, query: str) -> set[str]:
    response = await client.get(f"/api/events?{query}")
    assert response.status_code == 200, response.text
    return {row["frigate_event"] for row in response.json()}


async def _count(client: httpx.AsyncClient, query: str) -> int:
    response = await client.get(f"/api/events/count?{query}")
    assert response.status_code == 200, response.text
    return response.json()["count"]


async def _visits(client: httpx.AsyncClient, query: str) -> set[str]:
    response = await client.get(f"/api/visits?{query}&limit=500")
    assert response.status_code == 200, response.text
    return {
        capture["frigate_event"]
        for visit in response.json()["visits"]
        for capture in (visit["representative"], visit["latest"])
    }


LAST_24_HOURS = "start_time=2034-03-09T23:45:00Z&end_time=2034-03-10T23:45:00Z"


@pytest.mark.asyncio
async def test_events_and_count_return_exactly_the_last_24_hours(client):
    expected = {"exact-1", "exact-2", "exact-3", "exact-4"}
    assert await _events(client, LAST_24_HOURS) == expected
    assert await _count(client, LAST_24_HOURS) == 4
    assert await _visits(client, LAST_24_HOURS) == expected


@pytest.mark.asyncio
async def test_both_bounds_are_inclusive_like_the_visit_list(client):
    query = "start_time=2034-03-10T12:00:00Z&end_time=2034-03-10T23:30:00Z"
    assert await _events(client, query) == {"exact-1", "exact-2", "exact-3"}
    assert await _count(client, query) == 3
    assert await _visits(client, query) == {"exact-1", "exact-2", "exact-3"}


@pytest.mark.asyncio
async def test_bounds_keep_microsecond_precision(client):
    query = "start_time=2034-03-10T12:00:00.000001Z&end_time=2034-03-10T23:29:59.999999Z"
    assert await _events(client, query) == {"exact-2"}
    assert await _count(client, query) == 1


@pytest.mark.asyncio
async def test_an_offset_names_the_same_instant_as_utc(client):
    # 00:30 Berlin on the 11th is 23:30 UTC on the 10th.
    query = "start_time=2034-03-11T00:30:00%2B01:00"
    assert await _events(client, query) == {"exact-3", "exact-4"}
    assert await _count(client, query) == 2


@pytest.mark.asyncio
async def test_exact_instants_outrank_calendar_days(client):
    query = f"start_date=2034-03-01&end_date=2034-03-20&{LAST_24_HOURS}"
    assert await _events(client, query) == {"exact-1", "exact-2", "exact-3", "exact-4"}
    assert await _count(client, query) == 4


@pytest.mark.asyncio
async def test_a_count_with_only_an_exact_bound_says_it_is_filtered(client):
    response = await client.get("/api/events/count?start_time=2034-03-10T23:00:00Z")
    assert response.json() == {"count": 2, "filtered": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["newest", "oldest"])
async def test_a_species_filter_keeps_the_exact_window(client, sort):
    # A bare species filter takes the indexed fast path; a bound must still narrow it.
    query = f"species=Erithacus%20rubecula&sort={sort}&{LAST_24_HOURS}"
    assert await _events(client, query) == {"exact-1"}
    assert await _count(client, query) == 1
    assert await _events(client, f"species=Erithacus%20rubecula&sort={sort}") == {"exact-old", "exact-0", "exact-1"}


@pytest.mark.asyncio
async def test_a_today_only_guest_cannot_reach_before_the_utc_day(client, monkeypatch):
    _as_guest(monkeypatch, days=0)
    assert await _events(client, LAST_24_HOURS) == {"exact-1", "exact-2", "exact-3", "exact-4"}
    query = "start_time=2034-03-01T00:00:00Z&end_time=2034-03-20T00:00:00Z"
    assert await _events(client, query) == {"exact-1", "exact-2", "exact-3", "exact-4"}
    assert await _count(client, query) == 4
    assert await _visits(client, query) == {"exact-1", "exact-2", "exact-3", "exact-4"}
    assert await _events(client, "end_time=2034-03-09T23:59:59Z") == set()
    assert await _count(client, "end_time=2034-03-09T23:59:59Z") == 0


@pytest.mark.asyncio
async def test_a_guest_window_of_days_still_starts_at_its_cutoff(client, monkeypatch):
    _as_guest(monkeypatch, days=1)
    query = "start_time=2034-03-01T00:00:00Z"
    assert await _events(client, query) == {"exact-0", "exact-1", "exact-2", "exact-3", "exact-4"}
    assert await _count(client, query) == 5
    species_query = f"species=Erithacus%20rubecula&{query}"
    assert await _events(client, species_query) == {"exact-0", "exact-1"}
    assert await _count(client, species_query) == 2


@pytest.mark.asyncio
async def test_an_exact_range_longer_than_a_year_is_refused(client):
    query = "start_time=2032-01-01T00:00:00Z&end_time=2034-03-10T00:00:00Z"
    assert (await client.get(f"/api/events?{query}")).status_code == 400
    assert (await client.get(f"/api/events/count?{query}")).status_code == 400


@pytest.mark.asyncio
async def test_an_instant_that_is_not_a_time_is_rejected(client):
    assert (await client.get("/api/events?start_time=yesterday")).status_code == 422
    assert (await client.get("/api/events/count?end_time=soon")).status_code == 422
