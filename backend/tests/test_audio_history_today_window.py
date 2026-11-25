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

SURFACES = ("history", "summary", "activity-heatmap")
UTC_MIDNIGHT = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _counted(surface: str, payload: dict) -> int:
    return payload["total_count"] if surface == "activity-heatmap" else payload["total"]


@pytest.fixture
def audio_rows(monkeypatch, tmp_path):
    """An isolated copy of the migrated database, holding the rows each test seeds."""
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


def _guests_see_today_only(monkeypatch) -> None:
    for key, value in {"enabled": True, "initial_setup_complete": True, "username": "owner"}.items():
        monkeypatch.setattr(settings.auth, key, value)
    for key, value in {
        "enabled": True,
        "historical_days_mode": "custom",
        "show_historical_days": 0,
        "show_audio": True,
        "show_camera_names": True,
    }.items():
        monkeypatch.setattr(settings.public_access, key, value)


async def _read(surface: str, params: dict, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/audio/{surface}", params=params, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


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
@pytest.mark.parametrize("surface", SURFACES)
async def test_a_guest_today_that_starts_before_the_shared_day_is_narrowed_to_it(audio_rows, monkeypatch, surface):
    _guests_see_today_only(monkeypatch)
    # A viewer ten hours ahead of UTC: their midnight was 14:00 UTC yesterday, before the shared day.
    start = UTC_MIDNIGHT - timedelta(hours=10)
    end = datetime.now(timezone.utc)
    audio_rows([(UTC_MIDNIGHT - timedelta(hours=2), "BeforeShared"), (UTC_MIDNIGHT, "SharedMidnight")])
    params = {"start_date": _iso(start), "end_date": _iso(end)}
    owner_headers = {"Authorization": f"Bearer {create_access_token('owner')}"}

    guest = await _read(surface, params)
    owner = await _read(surface, params, owner_headers)

    assert _counted(surface, guest) == 1
    assert _counted(surface, owner) == 2
    if surface != "history":
        assert guest["window_start"] == _iso(UTC_MIDNIGHT)
        assert owner["window_start"] == _iso(start)


@pytest.mark.asyncio
async def test_a_guest_today_inside_the_shared_day_keeps_its_own_start(audio_rows, monkeypatch):
    _guests_see_today_only(monkeypatch)
    # A viewer behind UTC whose midnight falls inside the shared UTC day; asked at the last minute of it.
    start = UTC_MIDNIGHT + timedelta(hours=5)
    end = UTC_MIDNIGHT + timedelta(hours=23, minutes=59)
    audio_rows([(start - timedelta(minutes=1), "BeforeLocalMidnight"), (start, "LocalMidnight")])

    payload = await _read("summary", {"start_date": _iso(start), "end_date": _iso(end)})

    assert payload["total"] == 1
    assert payload["window_start"] == _iso(start)
    assert payload["window_end"] == _iso(end)
