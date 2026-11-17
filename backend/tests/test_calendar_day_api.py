"""``today`` and plain dates mean the instance's calendar day on every history endpoint (#950)."""

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, stats
from app.utils import public_access

pytestmark = pytest.mark.usefixtures("history_pool")

# 23:45 UTC on 10 March is 00:45 on 11 March in Berlin (UTC+1 before daylight saving).
NOW = datetime(2034, 3, 10, 23, 45)
ROWS = {
    "cal-0": ("2034-03-09 23:30:00", "Erithacus rubecula"),  # 00:30 Berlin on the 10th
    "cal-1": ("2034-03-10 12:00:00", "Erithacus rubecula"),  # 13:00 Berlin on the 10th
    "cal-2": ("2034-03-10 22:30:00", "Parus major"),  # 23:30 Berlin on the 10th
    "cal-3": ("2034-03-10 23:30:00", "Turdus merula"),  # 00:30 Berlin on the 11th
    "cal-4": ("2034-03-10 23:40:00", "Prunella modularis"),  # 00:40 Berlin on the 11th
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
    monkeypatch.setattr(stats, "utc_naive_now", lambda: NOW)
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
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'cal-%'")
            await db.commit()


def _event_ids(response: httpx.Response) -> set[str]:
    assert response.status_code == 200, response.text
    return {row["frigate_event"] for row in response.json()}


def _visit_events(response: httpx.Response) -> set[str]:
    assert response.status_code == 200, response.text
    return {visit["representative"]["frigate_event"] for visit in response.json()["visits"]}


def _as_guest(monkeypatch, days: int) -> None:
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", days)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")


@pytest.mark.asyncio
async def test_events_today_is_the_instance_calendar_day(client):
    response = await client.get("/api/events?start_date=today&end_date=today")
    assert _event_ids(response) == {"cal-3", "cal-4"}


@pytest.mark.asyncio
async def test_events_today_without_tz_is_the_utc_day(client, monkeypatch):
    monkeypatch.delenv("TZ")
    response = await client.get("/api/events?start_date=today&end_date=today")
    assert _event_ids(response) == {"cal-1", "cal-2", "cal-3", "cal-4"}


@pytest.mark.asyncio
async def test_a_plain_date_runs_midnight_to_midnight_in_the_instance_zone(client):
    response = await client.get("/api/events?start_date=2034-03-10&end_date=2034-03-10")
    # 23:30 Berlin belongs to the 10th; 00:30 on the 11th does not, though it is still the 10th in UTC.
    assert _event_ids(response) == {"cal-0", "cal-1", "cal-2"}


@pytest.mark.asyncio
async def test_an_unknown_day_keyword_is_rejected(client):
    response = await client.get("/api/events?start_date=yesterday")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_events_count_shares_the_calendar_day(client):
    response = await client.get("/api/events/count?start_date=today&end_date=today")
    assert response.status_code == 200, response.text
    assert response.json() == {"count": 2, "filtered": True}


@pytest.mark.asyncio
async def test_events_page_names_the_next_offset_only_when_more_rows_exist(client):
    first = await client.get("/api/events?start_date=today&end_date=today&limit=1")
    assert len(_event_ids(first)) == 1
    assert first.headers["x-next-offset"] == "1"
    last = await client.get("/api/events?start_date=today&end_date=today&limit=1&offset=1")
    assert len(_event_ids(last)) == 1
    assert "x-next-offset" not in last.headers


@pytest.mark.asyncio
async def test_visits_today_is_the_instance_calendar_day(client):
    response = await client.get("/api/visits?start_date=today&end_date=today")
    assert _visit_events(response) == {"cal-3", "cal-4"}
    assert response.json()["total"] == 2


@pytest.mark.asyncio
async def test_visits_return_a_busy_day_in_one_page_but_stay_bounded(client):
    assert (await client.get("/api/visits?start_date=today&limit=500")).status_code == 200
    assert (await client.get("/api/visits?start_date=today&limit=501")).status_code == 422


@pytest.mark.asyncio
async def test_today_never_widens_what_a_guest_may_see(client, monkeypatch):
    # A guest limited to today sees the UTC day (10 March) only. Berlin's "today" (the 11th)
    # overlaps it from 23:00 UTC, so the guest gets that overlap and nothing more.
    _as_guest(monkeypatch, days=0)
    assert _event_ids(await client.get("/api/events?start_date=today&end_date=today")) == {"cal-3", "cal-4"}
    assert _visit_events(await client.get("/api/visits?start_date=today&end_date=today")) == {"cal-3", "cal-4"}
    # A local date that starts before the guest's cutoff is narrowed to it, not widened.
    assert _event_ids(await client.get("/api/events?start_date=2034-03-10&end_date=2034-03-10")) == {
        "cal-1",
        "cal-2",
    }
    assert _event_ids(await client.get("/api/events?start_date=2034-03-01")) == {"cal-1", "cal-2", "cal-3", "cal-4"}
    count = await client.get("/api/events/count?start_date=2034-03-01")
    assert count.json()["count"] == 4


@pytest.mark.asyncio
async def test_a_guest_history_window_still_starts_at_its_cutoff(client, monkeypatch):
    _as_guest(monkeypatch, days=1)
    assert "cal-0" in _event_ids(await client.get("/api/events?start_date=2034-03-01"))
    assert _event_ids(await client.get("/api/events?start_date=today")) == {"cal-3", "cal-4"}


@pytest.mark.asyncio
async def test_daily_summary_keeps_the_rolling_day_by_default(client):
    response = await client.get("/api/stats/daily-summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window"] == "rolling"
    assert body["window_start"] == "2034-03-09T23:45:00Z"
    assert body["window_end"] == "2034-03-10T23:45:00Z"
    assert body["total_count"] == 4


@pytest.mark.asyncio
async def test_daily_summary_today_counts_from_local_midnight(client):
    response = await client.get("/api/stats/daily-summary?window=today")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window"] == "today"
    assert body["window_start"] == "2034-03-10T23:00:00Z"
    assert body["window_end"] == "2034-03-10T23:45:00Z"
    assert body["total_count"] == 2
    assert body["visit_count"] == 2
    assert {species["species"] for species in body["top_species"]} == {"Turdus merula", "Prunella modularis"}


@pytest.mark.asyncio
async def test_daily_summary_today_for_a_guest_keeps_the_guest_cutoff(client, monkeypatch):
    # At 00:30 UTC Berlin's day began at 23:00 UTC yesterday; a guest's day began at UTC midnight.
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime(2034, 3, 10, 0, 30))
    owner = (await client.get("/api/stats/daily-summary?window=today")).json()
    assert owner["window_start"] == "2034-03-09T23:00:00Z"
    assert owner["total_count"] == 1
    _as_guest(monkeypatch, days=0)
    guest = (await client.get("/api/stats/daily-summary?window=today")).json()
    assert guest["window_start"] == "2034-03-10T00:00:00Z"
    assert guest["total_count"] == 0


@pytest.mark.asyncio
async def test_visit_pages_read_their_captures_in_one_batch(client):
    async with get_db() as db:
        found = await DetectionRepository(db).get_by_frigate_events(["cal-1", "cal-3", "cal-missing", "cal-1"])
    assert set(found) == {"cal-1", "cal-3"}
    assert found["cal-3"].display_name == "Turdus merula"
