"""Exact guest audio bounds and unambiguous upstream media identity."""

from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
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
from app.repositories.detection_repository import DetectionRepository
from app.routers import audio


@pytest.fixture
def bounded_audio(monkeypatch, tmp_path):
    path = tmp_path / "bounded.db"
    today = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    end = today + timedelta(days=1)
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("DELETE FROM detections")
        db.execute("DELETE FROM audio_detections")
        for identifier, stamp, name in [
            (101, today + timedelta(seconds=1), "Shared"),
            (102, end, "BoundaryPrivate"),
            (103, end + timedelta(seconds=1), "FuturePrivate"),
        ]:
            db.execute(
                "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data) VALUES(?,?,.9,?,?)",
                (stamp.replace(tzinfo=None).isoformat(sep=" "), name, name, json.dumps({"detectionId": identifier})),
            )
        db.execute(
            "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES('midnight','feeder',?,1,.9,'Robin','Robin')",
            ((end - timedelta(seconds=1)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        db.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    monkeypatch.setattr(audio, "get_db", database)
    for obj, attrs in [
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
        (settings.frigate, {"birdnet_url": "http://birdnet.fixture", "camera_audio_mapping": {"feeder": "*"}}),
    ]:
        for key, value in attrs.items():
            monkeypatch.setattr(obj, key, value)
    monkeypatch.setattr(audio, "localize_audio_detections", AsyncMock())
    return today, end, database


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["history", "summary", "sources", "context", "event_context"])
async def test_today_only_audio_excludes_future_before_paging_counts_and_sources(bounded_audio, surface):
    today, end, _ = bounded_audio
    path, params = f"/api/audio/{surface}", {}
    if surface in {"history", "summary"}:
        params = {"start_date": today.isoformat(), "end_date": (end + timedelta(days=1)).isoformat()}
        if surface == "history":
            params["limit"] = 1
    elif surface == "context":
        params = {"timestamp": (end - timedelta(seconds=1)).isoformat(), "window_seconds": 5}
    elif surface == "event_context":
        path = "/api/audio/context/event/midnight"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        guest = await client.get(path, params=params)
        owner = await client.get(
            path, params=params, headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
    assert guest.status_code == 200, guest.text
    assert "BoundaryPrivate" not in guest.text and "FuturePrivate" not in guest.text
    # Owners keep their requested interval, including the selected first page.
    assert "FuturePrivate" in owner.text
    if surface != "history":
        assert "BoundaryPrivate" in owner.text
    if surface in {"history", "summary"}:
        assert guest.json()["total"] == 1
    if surface in {"context", "event_context"}:
        assert guest.json() == []
        assert guest.headers["X-YAWAMF-Audio-Suppressed-By-Mapping"] == "0"


@pytest.mark.asyncio
async def test_audio_leaderboard_excludes_future_only_history_start(bounded_audio):
    _, _, database = bounded_audio
    async with database() as db:
        await db.execute("DELETE FROM audio_detections WHERE species='Shared'")
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        guest = await client.get("/api/audio/species?span=all")
    assert guest.status_code == 200, guest.text
    assert guest.json()["history_start"] is None and guest.json()["species"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["clip", "spectrogram"])
@pytest.mark.parametrize("identifier", [102, 103])
async def test_future_media_denied_before_fetch_owner_unchanged(bounded_audio, monkeypatch, route, identifier):
    original = httpx.AsyncClient
    calls = []

    def answer(request):
        calls.append(request)
        return httpx.Response(200, content=b"fixture", request=request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(answer), **kwargs)
    )
    async with original(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        guest = await client.get(f"/api/audio/{route}/{identifier}")
        assert guest.status_code == 404, guest.text
        assert not calls
        owner = await client.get(
            f"/api/audio/{route}/{identifier}", headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
    assert owner.status_code == 200, owner.text
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("collision", ["old_hidden", "old_visible", "future", "source", "timestamp", "unknown_source"])
async def test_all_retained_media_identity_conflicts_fail_closed(bounded_audio, collision):
    today, end, database = bounded_audio
    stamp, hidden, sensor = today + timedelta(seconds=1), False, "Shared"
    if collision.startswith("old"):
        stamp, hidden = today - timedelta(days=2), collision == "old_hidden"
    elif collision == "future":
        stamp = end
    elif collision == "source":
        sensor = "other-source"
    elif collision == "timestamp":
        stamp += timedelta(seconds=1)
    elif collision == "unknown_source":
        sensor = None
    async with database() as db:
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Collision',.9,?,?,?)",
            (stamp.replace(tzinfo=None).isoformat(sep=" "), sensor, json.dumps({"id": 101}), hidden),
        )
        await db.commit()
        assert not await DetectionRepository(db).public_birdnet_media_visible(101, today)


@pytest.mark.asyncio
async def test_single_future_incomplete_and_oversized_identity_denied(bounded_audio):
    today, end, database = bounded_audio
    async with database() as db:
        repo = DetectionRepository(db)
        assert not await repo.public_birdnet_media_visible(102, today, maximum_end=end)
        await db.execute("UPDATE audio_detections SET sensor_id=NULL WHERE species='Shared'")
        await db.commit()
        assert not await repo.public_birdnet_media_visible(101, today)
        assert not await repo.public_birdnet_media_visible(2**100, today)


@pytest.mark.asyncio
async def test_duplicate_identity_normalizes_source_case_and_space(bounded_audio):
    today, _, database = bounded_audio
    async with database() as db:
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data) SELECT timestamp,species,confidence,'  SHARED  ',raw_data FROM audio_detections WHERE species='Shared'"
        )
        await db.commit()
        assert await DetectionRepository(db).public_birdnet_media_visible(101, today)


@pytest.mark.asyncio
async def test_context_upper_bound_precedes_mapping_suppression(bounded_audio):
    today, end, database = bounded_audio
    async with database() as db:
        results, suppressed = await DetectionRepository(db).get_audio_context(
            end - timedelta(seconds=1), 5, "unmapped-source", 1, minimum_start=today, maximum_end=end
        )
    assert results == [] and suppressed == 0


@pytest.mark.asyncio
async def test_invalid_timestamp_cannot_grant_media_access(bounded_audio):
    today, _, database = bounded_audio
    async with database() as db:
        await db.execute("UPDATE audio_detections SET timestamp='invalid' WHERE species='Shared'")
        await db.commit()
        assert not await DetectionRepository(db).public_birdnet_media_visible(101, today)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_device", [False, True])
async def test_stable_source_ids_disambiguate_same_names_and_allow_renamed_aliases(bounded_audio, same_device):
    today, _, database = bounded_audio
    first = {"detectionId": 101, "Source": {"id": "device-a", "displayName": "same-name"}}
    second = {
        "id": 101,
        "Source": {
            "id": "device-a" if same_device else "device-b",
            "displayName": "renamed" if same_device else "same-name",
        },
    }
    async with database() as db:
        await db.execute("UPDATE audio_detections SET raw_data=? WHERE species='Shared'", (json.dumps(first),))
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data) SELECT timestamp,species,confidence,sensor_id,? FROM audio_detections WHERE species='Shared'",
            (json.dumps(second),),
        )
        await db.commit()
        assert await DetectionRepository(db).public_birdnet_media_visible(101, today) is same_device


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [True, False])
async def test_owner_audio_hide_broadcasts_only_after_success(bounded_audio, monkeypatch, found):
    from app.services.broadcaster import broadcaster

    sender = AsyncMock()
    monkeypatch.setattr(audio.audio_service, "set_hidden", AsyncMock(return_value=found))
    monkeypatch.setattr(broadcaster, "broadcast", sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.patch(
            "/api/audio/history/101",
            json={"hidden": True},
            headers={"Authorization": f"Bearer {create_access_token('owner')}"},
        )
    assert response.status_code == (200 if found else 404), response.text
    if found:
        sender.assert_awaited_once_with({"type": "audio_history_changed"})
    else:
        sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_conflicting_source_ids_inside_payload_are_not_authority(bounded_audio):
    today, _, database = bounded_audio
    async with database() as db:
        await db.execute(
            "UPDATE audio_detections SET raw_data=? WHERE species='Shared'",
            (json.dumps({"detectionId": 101, "sourceId": "device-a", "Source": {"id": "device-b"}}),),
        )
        await db.commit()
        assert not await DetectionRepository(db).public_birdnet_media_visible(101, today)


@pytest.mark.asyncio
async def test_invalid_numeric_identity_text_does_not_escape_as_an_error(bounded_audio):
    today, _, database = bounded_audio
    async with database() as db:
        await db.execute(
            "UPDATE audio_detections SET raw_data=? WHERE species='Shared'",
            (json.dumps({"detectionId": "²", "id": 101}),),
        )
        await db.commit()
        assert not await DetectionRepository(db).public_birdnet_media_visible(101, today)
