"""A guest learns no source name or id from outside the shared window, on any audio route (#1111).

Yesterday the stream ``rtsp_private`` was called ``Feeder`` and then ``Private Door``. Today, inside
a today-only shared window, there is one call without an id under ``Feeder`` and one call from
another stream. The owner's view joins today's ``Feeder`` call to the renamed stream; a guest's
must not, or it would show the private name, its id, or answer a filter for it.
"""

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

PRIVATE = ("Private Door", "rtsp_private")


@pytest.fixture
def renamed_before_the_window(monkeypatch, tmp_path):
    path = tmp_path / "guest-window.db"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = now.replace(hour=0, minute=0, second=0)
    shared = max(today + timedelta(seconds=1), now - timedelta(minutes=2))
    rows = [
        # Before the shared window: the stream's old name and the private name it was given.
        (today - timedelta(hours=14), "Feeder", "Node", "rtsp_private", "Feeder"),
        (today - timedelta(hours=13), "Private Door", "Node", "rtsp_private", "Private Door"),
        # Inside it: a call stored without an id, and a call from another stream.
        (shared, "Feeder", None, None, "Feeder"),
        (shared + timedelta(seconds=1), "Garden", "Node", "rtsp_garden", "Garden"),
    ]
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("DELETE FROM detections")
        db.execute("DELETE FROM audio_detections")
        for index, (stamp, sensor, node, source_id, name) in enumerate(rows, start=1):
            db.execute(
                """INSERT INTO audio_detections
                   (timestamp, species, confidence, sensor_id, raw_data, source_node, source_id, source_name)
                   VALUES (?, 'Robin', .9, ?, ?, ?, ?, ?)""",
                (
                    stamp.replace(tzinfo=None).isoformat(sep=" "),
                    sensor,
                    json.dumps({"detectionId": index, "sourceName": name}),
                    node,
                    source_id,
                    name,
                ),
            )
        db.execute(
            """INSERT INTO detections(frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name)
               VALUES ('shared-visit', 'feeder', ?, 1, .9, 'Robin', 'Robin')""",
            (shared.replace(tzinfo=None).isoformat(sep=" "),),
        )
        db.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(audio, "get_db", database)
    for target, values in [
        (settings.auth, {"enabled": True, "initial_setup_complete": True, "username": "owner"}),
        (
            settings.public_access,
            {
                "enabled": True,
                "historical_days_mode": "custom",
                "show_historical_days": 0,
                "show_audio": True,
                "show_camera_names": True,
            },
        ),
        (settings.frigate, {"camera_audio_mapping": {"feeder": "Feeder, Garden"}}),
    ]:
        for key, value in values.items():
            monkeypatch.setattr(target, key, value)
    monkeypatch.setattr(audio, "localize_audio_detections", AsyncMock())
    return today, shared


async def _get(path: str, params: dict | None = None, *, owner: bool = False) -> httpx.Response:
    headers = {"Authorization": f"Bearer {create_access_token('owner')}"} if owner else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response


def _assert_private_source_absent(response: httpx.Response) -> None:
    for secret in PRIVATE:
        assert secret not in response.text


def _window(today: datetime) -> dict:
    return {"start_date": today.isoformat(), "end_date": (today + timedelta(days=1)).isoformat()}


@pytest.mark.asyncio
async def test_the_owner_sees_the_rename_the_guest_must_not(renamed_before_the_window):
    today, _ = renamed_before_the_window
    owner = await _get("/api/audio/summary", {"days": 7}, owner=True)
    assert {item["source_name"] for item in owner.json()["sources"]} == {"Private Door", "Garden"}


@pytest.mark.asyncio
async def test_guest_history_names_calls_by_the_shared_window_only(renamed_before_the_window):
    today, _ = renamed_before_the_window
    response = await _get("/api/audio/history", _window(today))
    _assert_private_source_absent(response)
    assert sorted(item["source_name"] for item in response.json()["items"]) == ["Feeder", "Garden"]
    for probe in ("source", "search"):
        probed = await _get("/api/audio/history", {**_window(today), probe: "Private"})
        assert probed.json()["total"] == 0, probe
        probed = await _get("/api/audio/history", {**_window(today), probe: "rtsp_private"})
        assert probed.json()["total"] == 0, probe


@pytest.mark.asyncio
async def test_guest_summary_lists_sources_by_the_shared_window_only(renamed_before_the_window):
    today, _ = renamed_before_the_window
    response = await _get("/api/audio/summary", _window(today))
    _assert_private_source_absent(response)
    assert sorted((item["source_name"], item["source_id"]) for item in response.json()["sources"]) == [
        ("Feeder", None),
        ("Garden", "rtsp_garden"),
    ]
    for probe in ("source", "search"):
        assert (await _get("/api/audio/summary", {**_window(today), probe: "Private"})).json()["total"] == 0


@pytest.mark.asyncio
async def test_guest_activity_grid_answers_no_filter_for_a_name_outside_the_window(renamed_before_the_window):
    today, _ = renamed_before_the_window
    for probe in ("source", "search"):
        response = await _get("/api/audio/activity-heatmap", {**_window(today), probe: "Private"})
        assert response.json()["total_count"] == 0, probe
    assert (await _get("/api/audio/activity-heatmap", {**_window(today), "source": "Feeder"})).json()[
        "total_count"
    ] == 1


@pytest.mark.asyncio
async def test_guest_heard_bands_name_calls_by_the_shared_window_only(renamed_before_the_window):
    today, _ = renamed_before_the_window
    response = await _get("/api/audio/heard-groups", _window(today))
    _assert_private_source_absent(response)


@pytest.mark.asyncio
async def test_guest_source_discovery_lists_the_shared_window_only(renamed_before_the_window):
    response = await _get("/api/audio/sources")
    _assert_private_source_absent(response)
    assert sorted(item["source_name"] for item in response.json()) == ["Feeder", "Garden"]


@pytest.mark.asyncio
async def test_guest_recent_calls_are_named_by_the_shared_window_only(renamed_before_the_window):
    response = await _get("/api/audio/recent")
    _assert_private_source_absent(response)
    assert sorted(item["source_name"] for item in response.json()) == ["Feeder", "Garden"]


@pytest.mark.asyncio
async def test_guest_context_names_calls_by_the_shared_window_only(renamed_before_the_window):
    _, shared = renamed_before_the_window
    response = await _get(
        "/api/audio/context", {"timestamp": shared.isoformat(), "camera": "feeder", "window_seconds": 60}
    )
    _assert_private_source_absent(response)
    assert sorted(item["sensor_id"] for item in response.json()) == ["Feeder", "Garden"]
    event = await _get("/api/audio/context/event/shared-visit")
    _assert_private_source_absent(event)


@pytest.fixture
def renamed_while_shared(monkeypatch, tmp_path):
    """Two shared calls from one stream, the newer under a name the owner is about to hide."""
    path = tmp_path / "guest-race.db"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = now.replace(hour=0, minute=0, second=0)
    first = max(today + timedelta(seconds=1), now - timedelta(minutes=3))
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("DELETE FROM detections")
        db.execute("DELETE FROM audio_detections")
        for index, (stamp, name) in enumerate([(first, "Feeder"), (first + timedelta(seconds=30), "Private Rename")]):
            db.execute(
                """INSERT INTO audio_detections
                   (timestamp, species, confidence, sensor_id, raw_data, source_node, source_id, source_name)
                   VALUES (?, 'Robin', .9, ?, ?, 'Shed', 'rtsp_a', ?)""",
                (
                    stamp.replace(tzinfo=None).isoformat(sep=" "),
                    name,
                    json.dumps({"detectionId": 500 + index, "sourceName": name, "sourceId": "rtsp_a"}),
                    name,
                ),
            )
        db.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(audio, "get_db", database)
    for target, values in [
        (settings.auth, {"enabled": True, "initial_setup_complete": True, "username": "owner"}),
        (
            settings.public_access,
            {"enabled": True, "historical_days_mode": "custom", "show_historical_days": 0, "show_audio": True},
        ),
    ]:
        for key, value in values.items():
            monkeypatch.setattr(target, key, value)
    monkeypatch.setattr(audio, "localize_audio_detections", AsyncMock())
    return path, today


@pytest.mark.asyncio
@pytest.mark.parametrize("filtered", [False, True])
async def test_a_call_hidden_while_a_guest_reads_never_names_the_calls_they_see(
    renamed_while_shared, monkeypatch, filtered
):
    path, today = renamed_while_shared
    original = audio.AudioHistoryRepository.load_audio_source_directory

    async def hide_after_reading(self, **kwargs):
        directory = await original(self, **kwargs)
        # The owner hides the newer call on another connection before the counts are read.
        with closing(sqlite3.connect(path)) as other:
            other.execute("UPDATE audio_detections SET is_hidden = 1 WHERE source_name = 'Private Rename'")
            other.commit()
        return directory

    monkeypatch.setattr(audio.AudioHistoryRepository, "load_audio_source_directory", hide_after_reading)
    params = {**_window(today), **({"source": "Private Rename"} if filtered else {})}
    summary = (await _get("/api/audio/summary", params)).json()

    # One reading of the history: a name is shown only beside the calls that carried it.
    counted = {(item["source_name"], item["count"]) for item in summary["sources"]}
    assert (summary["total"], counted) in [
        (2, {("Private Rename", 2)}),
        (1, set() if filtered else {("Feeder", 1)}),
    ]
    if summary["total"] == 2:
        # The read began before the hide, so it shows the history as it stood, whole.
        monkeypatch.setattr(audio.AudioHistoryRepository, "load_audio_source_directory", original)
        after = (await _get("/api/audio/summary", _window(today))).json()
        assert {(item["source_name"], item["count"]) for item in after["sources"]} == {("Feeder", 1)}
        assert "Private Rename" not in (await _get("/api/audio/summary", _window(today))).text
