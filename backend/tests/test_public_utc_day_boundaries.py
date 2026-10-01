"""UTC public-day admission is stable across server calendar and DST boundaries."""

from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiosqlite
import httpx
import pytest
from fastapi import HTTPException

from app.auth import AuthContext, AuthLevel, create_access_token
from app.config import settings
from app.main import app
from app.routers import about, ai, audio, events, proxy, species, stats
from app.utils import public_access

CLOCKS = [
    ("2026-09-30T23:30:00+00:00", "Europe/London"),
    ("2026-10-01T00:30:00+00:00", "America/Los_Angeles"),
    ("2026-09-30T10:30:00+00:00", "Pacific/Kiritimati"),
    ("2026-03-29T23:30:00+00:00", "Europe/London"),
    ("2026-10-25T00:30:00+00:00", "Europe/London"),
    ("2026-11-01T08:30:00+00:00", "America/Los_Angeles"),
    ("2026-09-30T23:59:59.999999+00:00", "Pacific/Kiritimati"),
    ("2026-10-01T00:00:00+00:00", "America/Los_Angeles"),
]


@pytest.fixture(params=CLOCKS, ids=lambda value: "/".join(value))
def clock(request, monkeypatch):
    instant = datetime.fromisoformat(request.param[0])
    local_zone = ZoneInfo(request.param[1])

    class FixedDate(date):
        @classmethod
        def today(cls):
            return instant.astimezone(local_zone).date()

    class FixedDatetime(datetime):
        @classmethod
        def combine(cls, day, clock, tzinfo=None):
            return datetime.combine(day, clock, tzinfo)

        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone(local_zone).replace(tzinfo=None)

    for module in (public_access, events, proxy, about):
        monkeypatch.setattr(module, "date", FixedDate, raising=False)
    for module in (public_access, audio, events, proxy, about, species, stats):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    for name, value in {
        "enabled": True,
        "historical_days_mode": "custom",
        "media_days_mode": "custom",
        "show_historical_days": 0,
        "media_historical_days": 0,
    }.items():
        monkeypatch.setattr(settings.public_access, name, value)
    return instant


@pytest.mark.parametrize("days", [0, 1, 7])
def test_public_current_event_and_audio_window_use_utc_calendar(clock, monkeypatch, days):
    monkeypatch.setattr(settings.public_access, "show_historical_days", days)
    expected = clock.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    assert public_access.public_events_cutoff() == expected
    assert public_access.public_events_end() == (expected + timedelta(days=1) if days == 0 else None)
    assert public_access.public_event_visible(SimpleNamespace(is_hidden=False, detection_time=clock))
    window = audio._history_window(30, None, None, AuthContext(auth_level=AuthLevel.GUEST))
    assert window.start_date <= window.end_date
    assert window.start_date == expected
    assert events._event_filter_start_date(AuthContext(auth_level=AuthLevel.GUEST)) == expected.replace(tzinfo=None)
    assert events._event_filter_start_date(AuthContext(auth_level=AuthLevel.OWNER)) is None


@pytest.fixture
def history(clock, monkeypatch, tmp_path):
    path = tmp_path / "utc-history.db"
    start = clock.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = [
        ("lower", start, False),
        ("current", clock, False),
        ("last", end - timedelta(microseconds=1), False),
        ("old", start - timedelta(microseconds=1), False),
        ("future", end, False),
        ("hidden", clock, True),
    ]
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM detections")
        db.execute("DELETE FROM audio_detections")
        for name, stamp, hidden in rows:
            db.execute(
                "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,is_hidden,ai_analysis) VALUES (?,'utc-camera',?,1,.9,?,?,?,'cached analysis')",
                (name, stamp.replace(tzinfo=None).isoformat(sep=" "), name, name, hidden),
            )
        db.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for module in (events, proxy, about, species, ai, stats):
        monkeypatch.setattr(module, "get_db", database)
    for name, value in {"enabled": True, "initial_setup_complete": True, "username": "owner"}.items():
        monkeypatch.setattr(settings.auth, name, value)
    for name, value in {
        "show_snapshots": True,
        "show_clips": True,
        "show_ai_conversation": True,
        "show_audio": False,
    }.items():
        monkeypatch.setattr(settings.public_access, name, value)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    monkeypatch.setattr(events.taxonomy_service, "get_names", AsyncMock(return_value={}))
    monkeypatch.setattr(about, "_snapshot_source", AsyncMock(return_value="hq_candidate_model_crop"))
    return database


@pytest.mark.asyncio
async def test_event_projection_facets_ai_and_media_share_exact_day_bounds(history):
    guest = AuthContext(auth_level=AuthLevel.GUEST)
    owner = AuthContext(auth_level=AuthLevel.OWNER)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        listed = await client.get("/api/events")
        count = await client.get("/api/events/count")
        facets = await client.get("/api/events/filters")
        showcase = await client.get("/api/about/showcase")
        for response in (listed, count, facets, showcase):
            assert response.status_code == 200, response.text
        expected = {"lower", "current", "last"}
        assert {row["frigate_event"] for row in listed.json()} == expected
        assert count.json()["count"] == 3
        assert {row["value"] for row in facets.json()["species"]} == expected
        assert {row["frigate_event"] for row in showcase.json()["items"]} == expected
        for name in ("lower", "current", "last", "old", "future", "hidden"):
            result = await client.post(f"/api/events/{name}/analyze")
            assert result.status_code == (200 if name in expected else 404)
            if name in expected:
                await proxy.require_event_access(name, guest, "en")
            else:
                with pytest.raises(HTTPException) as denial:
                    await proxy.require_event_access(name, guest, "en")
                assert denial.value.status_code == 404
            await proxy.require_event_access(name, owner, "en")
        owned = await client.get("/api/events", headers={"Authorization": f"Bearer {create_access_token('owner')}"})
        assert {row["frigate_event"] for row in owned.json()} == expected | {"old", "future"}


@pytest.mark.asyncio
async def test_portrait_media_days_use_calendar_midnight_not_rolling_hours(history, clock, monkeypatch):
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "media_historical_days", 1)
    stamp = clock.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1) + timedelta(seconds=1)
    async with history() as db:
        await db.execute("DELETE FROM detections")
        await db.execute(
            "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES ('portrait','camera',?,1,.9,'Robin','Robin')",
            (stamp.replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.commit()
    monkeypatch.setattr(
        about.media_cache, "get_snapshot_metadata", AsyncMock(return_value={"source": "hq_candidate_model_crop"})
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/leaderboard/portraits?span=week")
    assert response.status_code == 200, response.text
    assert [row["frigate_event"] for row in response.json()["portraits"]] == ["portrait"]


def test_utc_day_helper_accepts_aware_offsets_and_rejects_naive_instants():
    assert public_access.public_utc_day(datetime(2026, 10, 1, 0, 30, tzinfo=ZoneInfo("Europe/London"))) == date(
        2026, 9, 30
    )
    with pytest.raises(ValueError, match="aware"):
        public_access.public_utc_day(datetime(2026, 10, 1))


def test_public_bounds_read_the_policy_clock_once_across_midnight(monkeypatch):
    instants = iter(
        [datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc)]
    )

    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(instants)

        @classmethod
        def combine(cls, day, clock, tzinfo=None):
            return datetime.combine(day, clock, tzinfo)

    monkeypatch.setattr(public_access, "datetime", AdvancingDatetime)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    bounds = public_access.public_event_query_bounds()
    assert bounds == {
        "start_date": datetime(2026, 9, 30, tzinfo=timezone.utc),
        "end_date": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }
    assert next(instants) == datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/api/events", "/api/events/count"])
async def test_event_request_reads_one_day_when_the_clock_crosses_midnight(history, clock, monkeypatch, route):
    reads = []

    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            reads.append(None)
            return clock if len(reads) == 1 else clock + timedelta(days=1)

        @classmethod
        def combine(cls, day, clock, tzinfo=None):
            return datetime.combine(day, clock, tzinfo)

    monkeypatch.setattr(public_access, "datetime", AdvancingDatetime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
    assert response.status_code == 200, response.text
    assert len(reads) == 1
    if route.endswith("count"):
        assert response.json()["count"] == 3
    else:
        assert {row["frigate_event"] for row in response.json()} == {"lower", "current", "last"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "/api/stats/detections/timeline?span=day",
        "/api/stats/detections/activity-heatmap?span=day",
        "/api/leaderboard/species?span=week",
        "/api/leaderboard/portraits?span=week",
    ],
)
async def test_window_routes_reuse_their_own_instant_instead_of_reading_a_later_policy_day(
    history, clock, monkeypatch, route
):
    class LaterDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock + timedelta(days=1)

        @classmethod
        def combine(cls, day, clock, tzinfo=None):
            return datetime.combine(day, clock, tzinfo)

    monkeypatch.setattr(public_access, "datetime", LaterDatetime)
    original_bounds = public_access.public_event_query_bounds
    original_events = public_access.public_events_window
    original_media = public_access.public_media_window
    policy_instants = []

    def bounds(now=None):
        policy_instants.append(now)
        return original_bounds(now)

    def event_window(now=None):
        policy_instants.append(now)
        return original_events(now)

    def media_window(now=None):
        policy_instants.append(now)
        return original_media(now)

    monkeypatch.setattr(stats, "public_event_query_bounds", bounds)
    monkeypatch.setattr(species, "public_event_query_bounds", bounds)
    monkeypatch.setattr(species, "public_events_window", event_window)
    monkeypatch.setattr(public_access, "public_media_window", media_window)
    monkeypatch.setattr(species.nearby_species_service, "get_report", AsyncMock(return_value=None))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
    assert response.status_code == 200, response.text
    assert policy_instants and all(instant == clock for instant in policy_instants)
