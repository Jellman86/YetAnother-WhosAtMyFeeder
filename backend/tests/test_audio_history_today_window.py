"""Audio history's Today: one explicit pair of instants, read exactly by every surface and narrowed for guests."""

from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.routers import audio
from app.utils import public_access

SURFACES = ("history", "summary", "activity-heatmap")
# Every test reads one instant, so none can straddle a UTC midnight while it runs.
NOW = datetime(2026, 11, 25, 10, 30, tzinfo=timezone.utc)
UTC_MIDNIGHT = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
NEXT_UTC_MIDNIGHT = UTC_MIDNIGHT + timedelta(days=1)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _counted(surface: str, payload: dict) -> int:
    return payload["total_count"] if surface == "activity-heatmap" else payload["total"]


@pytest.fixture
def audio_rows(monkeypatch, tmp_path):
    """An isolated copy of the migrated database, holding the rows each test seeds, read at NOW."""
    monkeypatch.setattr(audio, "datetime", _FrozenDatetime)
    monkeypatch.setattr(public_access, "datetime", _FrozenDatetime)
    path = tmp_path / "today.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("DELETE FROM audio_detections")
        db.commit()

    def seed(rows: list[tuple[datetime, str]]) -> None:
        with closing(sqlite3.connect(path)) as db:
            for stamp, species in rows:
                db.execute(
                    "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data) VALUES(?,?,.9,?,?)",
                    (
                        stamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" "),
                        species,
                        "Garden Mic",
                        json.dumps({"nm": "Garden Mic"}),
                    ),
                )
            db.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    monkeypatch.setattr(audio, "get_db", database)
    monkeypatch.setattr(audio, "localize_audio_detections", AsyncMock())
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {})
    return seed


def _owner_without_sign_in(monkeypatch) -> None:
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)


def _guests_see_history_days(monkeypatch, days: int) -> None:
    for key, value in {"enabled": True, "initial_setup_complete": True, "username": "owner"}.items():
        monkeypatch.setattr(settings.auth, key, value)
    for key, value in {
        "enabled": True,
        "historical_days_mode": "custom",
        "show_historical_days": days,
        "show_audio": True,
        "show_camera_names": True,
    }.items():
        monkeypatch.setattr(settings.public_access, key, value)


async def _read(surface: str, params: dict, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/audio/{surface}", params=params, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


OWNER = {"Authorization": f"Bearer {create_access_token('owner')}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", SURFACES)
async def test_today_counts_calls_at_both_instants_and_none_outside_them(audio_rows, monkeypatch, surface):
    _owner_without_sign_in(monkeypatch)
    # Local midnight for a viewer five hours behind UTC, through a "now" an hour later.
    start = UTC_MIDNIGHT - timedelta(hours=19)
    end = start + timedelta(hours=1)
    audio_rows(
        [
            (start - timedelta(seconds=1), "Yesterday"),
            (start, "AtMidnight"),
            (start + timedelta(minutes=30), "Morning"),
            (end, "AtNow"),
            (end + timedelta(seconds=1), "AfterNow"),
        ]
    )

    payload = await _read(surface, {"start_date": _iso(start), "end_date": _iso(end), "days": 30})

    # The explicit instants win over `days`, and both ends are inclusive.
    assert _counted(surface, payload) == 3
    if surface == "history":
        assert {row["species"] for row in payload["items"]} == {"AtMidnight", "Morning", "AtNow"}


@pytest.mark.asyncio
async def test_the_summary_reports_the_window_it_counted(audio_rows, monkeypatch):
    _owner_without_sign_in(monkeypatch)
    start = UTC_MIDNIGHT - timedelta(hours=5)
    end = UTC_MIDNIGHT + timedelta(hours=3)

    payload = await _read("summary", {"start_date": _iso(start), "end_date": _iso(end)})

    assert payload["window_start"] == _iso(start)
    assert payload["window_end"] == _iso(end)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("zone", "local_midnight", "calls", "expected"),
    [
        # 06:00 on 25 November in Tokyo is 21:00 UTC on the 24th.
        (
            "Asia/Tokyo",
            datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc),
            [datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc), datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)],
            [{"date": "2026-11-25", "count": 2}],
        ),
        # 22:00 on 24 November in New York is 03:00 UTC on the 25th.
        (
            "America/New_York",
            datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc),
            [datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc), datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc)],
            [{"date": "2026-11-24", "count": 2}],
        ),
        # India is UTC+5:30: 00:10 on the 25th there is 18:40 UTC on the 24th, inside a UTC hour that
        # starts on the 24th locally, so an hour bucket would file it under the wrong day.
        (
            "Asia/Kolkata",
            datetime(2026, 11, 24, 18, 30, tzinfo=timezone.utc),
            [datetime(2026, 11, 24, 18, 40, tzinfo=timezone.utc)],
            [{"date": "2026-11-25", "count": 1}],
        ),
    ],
)
async def test_calls_over_time_are_counted_on_the_viewers_calendar_day(
    audio_rows, monkeypatch, zone, local_midnight, calls, expected
):
    _owner_without_sign_in(monkeypatch)
    audio_rows([(stamp, "Robin") for stamp in calls])
    end = local_midnight + timedelta(hours=23)

    payload = await _read("summary", {"start_date": _iso(local_midnight), "end_date": _iso(end)}, {"X-Timezone": zone})

    assert payload["daily_counts"] == expected


@pytest.mark.asyncio
async def test_calls_over_time_use_the_instance_zone_without_a_header(audio_rows, monkeypatch):
    _owner_without_sign_in(monkeypatch)
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    audio_rows([(datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc), "Robin")])

    payload = await _read("summary", {"start_date": _iso(UTC_MIDNIGHT - timedelta(days=1)), "end_date": _iso(NOW)})

    assert payload["daily_counts"] == [{"date": "2026-11-25", "count": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", SURFACES)
async def test_a_guest_today_that_starts_before_the_shared_day_is_narrowed_to_it(audio_rows, monkeypatch, surface):
    _guests_see_history_days(monkeypatch, 0)
    # A viewer ten hours ahead of UTC: their midnight was 14:00 UTC yesterday, before the shared day.
    start = UTC_MIDNIGHT - timedelta(hours=10)
    audio_rows([(UTC_MIDNIGHT - timedelta(hours=2), "BeforeShared"), (UTC_MIDNIGHT, "SharedMidnight")])
    params = {"start_date": _iso(start), "end_date": _iso(NOW)}

    guest = await _read(surface, params)
    owner = await _read(surface, params, OWNER)

    assert _counted(surface, guest) == 1
    assert _counted(surface, owner) == 2
    if surface != "history":
        assert guest["window_start"] == _iso(UTC_MIDNIGHT)
        assert owner["window_start"] == _iso(start)


@pytest.mark.asyncio
async def test_a_guest_today_inside_the_shared_day_keeps_its_own_start(audio_rows, monkeypatch):
    _guests_see_history_days(monkeypatch, 0)
    # A viewer behind UTC whose midnight falls inside the shared UTC day.
    start = UTC_MIDNIGHT + timedelta(hours=5)
    audio_rows([(start - timedelta(minutes=1), "BeforeLocalMidnight"), (start, "LocalMidnight")])

    payload = await _read("summary", {"start_date": _iso(start), "end_date": _iso(NOW)})

    assert payload["total"] == 1
    assert payload["window_start"] == _iso(start)
    assert payload["window_end"] == _iso(NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", SURFACES)
async def test_a_guest_never_sees_a_call_at_the_next_utc_midnight_however_late_the_request_ends(
    audio_rows, monkeypatch, surface
):
    _guests_see_history_days(monkeypatch, 0)
    audio_rows(
        [
            (NEXT_UTC_MIDNIGHT - timedelta(seconds=1), "LastSharedSecond"),
            (NEXT_UTC_MIDNIGHT, "NextDay"),
        ]
    )
    # The requested end is inclusive; the shared day's end is exclusive and wins.
    params = {"start_date": _iso(UTC_MIDNIGHT), "end_date": _iso(NEXT_UTC_MIDNIGHT + timedelta(hours=1))}

    guest = await _read(surface, params)
    owner = await _read(surface, params, OWNER)

    assert _counted(surface, guest) == 1
    assert _counted(surface, owner) == 2
    if surface != "history":
        assert guest["window_end"] == _iso(NEXT_UTC_MIDNIGHT)
    if surface == "history":
        assert [row["species"] for row in guest["items"]] == ["LastSharedSecond"]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", SURFACES)
async def test_a_guest_request_older_than_the_shared_days_starts_where_sharing_does(audio_rows, monkeypatch, surface):
    _guests_see_history_days(monkeypatch, 7)
    shared_start = UTC_MIDNIGHT - timedelta(days=7)
    audio_rows([(shared_start - timedelta(seconds=1), "TooOld"), (shared_start, "FirstShared")])
    params = {"start_date": _iso(UTC_MIDNIGHT - timedelta(days=30)), "end_date": _iso(NOW)}

    guest = await _read(surface, params)
    owner = await _read(surface, params, OWNER)

    assert _counted(surface, guest) == 1
    assert _counted(surface, owner) == 2
    if surface != "history":
        assert guest["window_start"] == _iso(shared_start)
        assert guest["window_end"] == _iso(NOW)
