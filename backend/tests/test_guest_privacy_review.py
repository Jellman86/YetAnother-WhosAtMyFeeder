"""Guest privacy through real routes, migrated history, and the live broadcaster."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
import json
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest
from starlette.requests import Request

from app.auth import AuthContext, AuthLevel, StreamAuth, create_access_token
from app.config import settings
from app.main import app, sse_endpoint
from app.routers import ai, audio, events, species, stats
from app.services.broadcaster import broadcaster


@pytest.fixture
def private_history(monkeypatch, tmp_path):
    path = tmp_path / "history.db"
    today = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM detections")
        db.execute("DELETE FROM audio_detections")
        for name, stamp, hidden in (
            ("visible", today + timedelta(seconds=1), 0),
            ("hidden", today + timedelta(seconds=2), 1),
            ("old", today - timedelta(seconds=1), 0),
        ):
            db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time,
                   detection_index, score, display_name, category_name, is_hidden, ai_analysis)
                   VALUES (?, 'secret-camera', ?, 1, .9, 'Robin', 'Robin', ?, ?)""",
                (name, stamp.replace(tzinfo=None).isoformat(sep=" "), hidden, f"analysis-{name}"),
            )
            db.execute(
                "INSERT INTO ai_conversation_turns (frigate_event, role, content, created_at) VALUES (?, 'user', ?, ?)",
                (name, f"conversation-{name}", stamp.replace(tzinfo=None).isoformat(sep=" ")),
            )
        for identifier, stamp, hidden, label, raw in (
            (101, today + timedelta(seconds=1), 0, "Visible", {"detectionId": 101}),
            (102, today + timedelta(seconds=2), 1, "Hidden", {"id": 102}),
            (103, today - timedelta(seconds=1), 0, "Old", {"detection_id": "103"}),
            (104, today + timedelta(seconds=3), 0, "Malformed", "broken-json"),
        ):
            db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, is_hidden)
                   VALUES (?, ?, .9, ?, ?, ?)""",
                (
                    stamp.replace(tzinfo=None).isoformat(sep=" "),
                    label,
                    f"source-{label}",
                    json.dumps(raw) if isinstance(raw, dict) else raw,
                    hidden,
                ),
            )
        db.commit()

    @asynccontextmanager
    async def history_db():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for router in (ai, audio, events, species, stats):
        monkeypatch.setattr(router, "get_db", history_db)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_ai_conversation", True)
    monkeypatch.setattr(settings.public_access, "show_audio", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    monkeypatch.setattr(settings.public_access, "show_camera_names", True)
    monkeypatch.setattr(settings.frigate, "birdnet_url", "http://birdnet.fixture")
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"secret-camera": "*"})
    monkeypatch.setattr(audio, "localize_audio_detections", AsyncMock())
    return today, history_db


@pytest.mark.asyncio
@pytest.mark.parametrize("route,method", [("analyze", "POST"), ("conversation", "GET")])
@pytest.mark.parametrize("event,expected", [("visible", 200), ("hidden", 404), ("old", 404), ("unknown", 404)])
async def test_guest_ai_requires_current_visible_parent(private_history, route, method, event, expected):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.request(method, f"/api/events/{event}/{route}")
        owner = await client.request(
            method, f"/api/events/old/{route}", headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
    assert response.status_code == expected, response.text
    assert owner.status_code == 200, owner.text
    if expected != 200:
        assert f"analysis-{event}" not in response.text
        assert f"conversation-{event}" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("route,method", [("analyze", "POST"), ("conversation", "GET")])
async def test_guest_ai_switch_covers_cached_answers(private_history, monkeypatch, route, method):
    monkeypatch.setattr(settings.public_access, "show_ai_conversation", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.request(method, f"/api/events/visible/{route}")
    assert response.status_code == 403
    assert "analysis-visible" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["history?days=3650", "summary?days=3650", "species?span=all", "sources"])
async def test_guest_audio_windows_filter_before_counts_and_source_discovery(private_history, route):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(f"/api/audio/{route}")
        owner = await client.get(
            f"/api/audio/{route}", headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
    assert response.status_code == 200, response.text
    assert '"Old"' not in response.text and "source-Old" not in response.text
    assert '"Hidden"' not in response.text and "source-Hidden" not in response.text
    assert "Visible" in response.text
    assert "Old" in owner.text
    if route.startswith(("history", "summary")):
        assert response.json()["total"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("event_context", [False, True])
async def test_guest_context_clamps_before_mapping_counts_and_limit(private_history, event_context):
    today, _ = private_history
    url = "/api/audio/context/event/visible" if event_context else "/api/audio/context"
    params = {} if event_context else {"timestamp": today.isoformat(), "limit": 1}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    assert response.json()[0]["species"] == "Visible"
    assert "Old" not in response.text
    assert response.headers["X-YAWAMF-Audio-Suppressed-By-Mapping"] == "0"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["clip", "spectrogram"])
@pytest.mark.parametrize("identifier,expected", [(101, 206), (102, 404), (103, 404), (99999, 404)])
async def test_guest_audio_media_requires_stored_visible_upstream_id(
    private_history, monkeypatch, route, identifier, expected
):
    upstream = AsyncMock(
        return_value=httpx.Response(
            206,
            content=b"audio-fixture",
            headers={"content-type": "audio/mp4", "content-range": "bytes 0-12/13", "accept-ranges": "bytes"},
        )
    )
    original_client = httpx.AsyncClient

    class MediaClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        get = upstream

    monkeypatch.setattr(audio.httpx, "AsyncClient", lambda **kwargs: MediaClient())
    async with original_client(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(f"/api/audio/{route}/{identifier}", headers={"Range": "bytes=0-12"})
    # Spectrograms return the complete image response even if the fixture has a range status.
    assert response.status_code == (200 if route == "spectrogram" and expected == 206 else expected), response.text
    assert upstream.await_count == (1 if identifier == 101 else 0)
    if identifier == 101:
        assert response.content == b"audio-fixture"
        assert "no-store" in response.headers["cache-control"]
        if route == "clip":
            assert upstream.call_args.kwargs["headers"] == {"Range": "bytes=0-12"}


@pytest.mark.asyncio
async def test_guest_recent_uses_persisted_visibility_not_stale_memory(private_history, monkeypatch):
    monkeypatch.setattr(
        audio.audio_service,
        "get_recent_detections",
        AsyncMock(
            return_value=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "species": "Hidden",
                    "confidence": 0.9,
                    "sensor_id": "private-mic",
                    "birdnet_id": 102,
                }
            ]
        ),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/audio/recent?limit=1")
    assert response.status_code == 200, response.text
    assert response.json()[0]["species"] == "Malformed"
    assert "Hidden" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["history", "context/event/visible", "sources", "recent"])
async def test_guest_source_privacy_hides_both_source_fields(private_history, monkeypatch, route):
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(f"/api/audio/{route}")
    assert response.status_code == 200, response.text
    assert "source-" not in response.text


@pytest.mark.asyncio
async def test_guest_sse_never_carries_raw_object_or_owner_payload(private_history):
    request = Request({"type": "http", "method": "GET", "path": "/api/sse", "headers": [], "query_string": b""})
    response = await sse_endpoint(request, StreamAuth(AuthContext(AuthLevel.GUEST), None))
    try:
        await response.body_iterator.__anext__()
        await broadcaster.broadcast({"type": "unknown_future_owner_message", "data": {"secret": "private"}})
        await broadcaster.broadcast(
            {"type": "detection_updated", "data": {"frigate_event": "hidden", "secret": "private"}}
        )
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert json.loads(frame.removeprefix("data: ")) == {"type": "public_history_changed"}
        await broadcaster.broadcast({"type": "settings_updated", "data": {"secret": "private"}})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert json.loads(frame.removeprefix("data: ")) == {"type": "public_access_changed"}
        settings.public_access.enabled = False
        await broadcaster.broadcast({"type": "detection", "data": {"secret": "private"}})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert json.loads(frame.removeprefix("data: ")) == {"type": "public_access_changed"}
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(response.body_iterator.__anext__(), 1)
    finally:
        await response.body_iterator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/audio/clip/101", "GET"),
        ("/api/audio/spectrogram/101", "GET"),
        ("/api/audio/history", "GET"),
        ("/api/audio/recent", "GET"),
        ("/api/audio/summary", "GET"),
        (
            "/api/audio/heard-groups?start_date="
            + datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
            + "&end_date="
            + (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
            "GET",
        ),
        ("/api/audio/species", "GET"),
        ("/api/audio/sources", "GET"),
        ("/api/audio/context/event/visible", "GET"),
        ("/api/events/visible/analyze", "POST"),
        ("/api/events/visible/conversation", "GET"),
    ],
)
async def test_visibility_database_failure_is_closed_and_retryable(private_history, monkeypatch, path, method):
    @asynccontextmanager
    async def unavailable():
        raise sqlite3.OperationalError("private-path.db locked")
        yield

    monkeypatch.setattr(audio, "get_db", unavailable)
    monkeypatch.setattr(ai, "get_db", unavailable)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.request(method, path)
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == "5"
    assert "private-path" not in response.text


@pytest.mark.asyncio
async def test_owner_sse_keeps_detailed_payload(private_history):
    request = Request({"type": "http", "method": "GET", "path": "/api/sse", "headers": [], "query_string": b""})
    response = await sse_endpoint(request, StreamAuth(AuthContext(AuthLevel.OWNER), None))
    message = {"type": "reclassification_progress", "data": {"event_id": "hidden", "diagnostics": {"secret": "owner"}}}
    try:
        await response.body_iterator.__anext__()
        await broadcaster.broadcast(message)
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert json.loads(frame.removeprefix("data: ")) == message
    finally:
        await response.body_iterator.aclose()


@pytest.mark.asyncio
async def test_media_identity_payload_precedence_and_hidden_collision(private_history):
    from app.repositories.detection_repository import DetectionRepository

    today, factory = private_history
    async with factory() as db:
        await db.execute(
            "UPDATE audio_detections SET raw_data = ? WHERE species='Visible'",
            (json.dumps({"detectionId": 666, "id": 101}),),
        )
        await db.commit()
        repo = DetectionRepository(db)
        assert not await repo.public_birdnet_media_visible(101, today)
        await db.execute(
            "UPDATE audio_detections SET raw_data = ? WHERE species='Visible'",
            (json.dumps({"detection_id": " 00101 "}),),
        )
        await db.commit()
        assert await repo.public_birdnet_media_visible(101, today)
        await db.execute("UPDATE audio_detections SET raw_data = ? WHERE species='Hidden'", (json.dumps({"id": 101}),))
        await db.commit()
        assert not await repo.public_birdnet_media_visible(101, today)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/api/events", "/api/stats/daily-summary", "/api/species/Robin/stats"])
async def test_audio_switch_covers_visual_history_representations(private_history, monkeypatch, route):
    _, factory = private_history
    async with factory() as db:
        await db.execute("UPDATE detections SET audio_species = 'Old', audio_score = .99, audio_confirmed = 0")
        await db.commit()
    monkeypatch.setattr(settings.public_access, "show_audio", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
    assert response.status_code == 200, response.text
    assert '"Old"' not in response.text
    if route == "/api/events":
        assert response.json()[0]["audio_context_species"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "/api/species",
        "/api/species/Robin/stats",
        "/api/leaderboard/species?span=week",
        "/api/stats/detections/daily?days=30",
        "/api/stats/detections/timeline?span=all&compare_species=Robin",
        "/api/stats/detections/activity-heatmap?span=all&species=Robin",
    ],
)
async def test_guest_visual_statistics_respect_history_window(private_history, monkeypatch, route):
    monkeypatch.setattr(stats.weather_service, "get_hourly_weather", AsyncMock(return_value={}))
    monkeypatch.setattr(species.nearby_species_service, "get_report", AsyncMock(return_value={}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
        owner = await client.get(route, headers={"Authorization": f"Bearer {create_access_token('owner')}"})
    assert response.status_code == 200, response.text
    assert owner.status_code == 200, owner.text
    data, owner_data = response.json(), owner.json()
    if route == "/api/species":
        assert data[0]["count"] == 1
        assert owner_data[0]["count"] == 2
    elif "/Robin/stats" in route:
        assert data["total_sightings"] == 1
        assert owner_data["total_sightings"] == 2
        assert {x["frigate_event"] for x in data["recent_sightings"]} == {"visible"}
    elif "/leaderboard/" in route:
        assert data["species"][0]["window_count"] == 1
        assert owner_data["species"][0]["window_count"] == 2
    else:
        assert data["total_count"] == 1
        assert owner_data["total_count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/api/events", "/api/stats/daily-summary", "/api/species/Robin/stats"])
@pytest.mark.parametrize("audio_visible", [False, True])
async def test_guest_visual_audio_requires_current_visible_evidence(private_history, route, audio_visible):
    _, db_factory = private_history
    async with db_factory() as db:
        await db.execute(
            "UPDATE detections SET audio_confirmed=1, audio_species='Visible', audio_score=.9 WHERE frigate_event='visible'"
        )
        await db.execute("UPDATE audio_detections SET is_hidden=? WHERE species='Visible'", (not audio_visible,))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
        owner = await client.get(route, headers={"Authorization": f"Bearer {create_access_token('owner')}"})
    assert response.status_code == 200, response.text
    data = response.json()
    detection = (
        data[0]
        if route == "/api/events"
        else data["latest_detection"]
        if route.endswith("daily-summary")
        else data["recent_sightings"][0]
    )
    assert detection["audio_confirmed"] is audio_visible
    assert detection["audio_species"] == ("Visible" if audio_visible else None)
    if route.endswith("daily-summary"):
        assert data["audio_confirmations"] == int(audio_visible)
    assert '"audio_confirmed":true' in owner.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "/api/leaderboard/species?span=week",
        "/api/events/filters?force_refresh=true",
        "/api/events?audio_confirmed_only=true",
        "/api/events/count?audio_confirmed_only=true",
    ],
)
async def test_guest_audio_aggregates_require_current_evidence(private_history, monkeypatch, route):
    _, db_factory = private_history
    monkeypatch.setattr(species.nearby_species_service, "get_report", AsyncMock(return_value=None))
    async with db_factory() as db:
        await db.execute(
            "UPDATE detections SET audio_confirmed=1, audio_species='Hidden', audio_score=.9 WHERE frigate_event='visible'"
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
    assert response.status_code == 200, response.text
    data = response.json()
    if "/leaderboard/" in route:
        assert data["species"][0]["window_audio_confirmed_count"] == 0
    elif "/filters" in route:
        assert data["totals"]["audio_matched"] == 0
    elif "/count" in route:
        assert data["count"] == 0
    else:
        assert data == []


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [None, ["private"], "private", 7])
async def test_guest_settings_invalidation_handles_malformed_producer_data(private_history, data):
    request = Request({"type": "http", "method": "GET", "path": "/api/sse", "headers": [], "query_string": b""})
    response = await sse_endpoint(request, StreamAuth(AuthContext(AuthLevel.GUEST), None))
    try:
        await response.body_iterator.__anext__()
        await broadcaster.broadcast({"type": "settings_updated", "data": data})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert json.loads(frame.removeprefix("data: ")) == {"type": "public_access_changed"}
    finally:
        await response.body_iterator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [1, 30, 100])
async def test_public_auth_status_advertises_refresh_budget(private_history, monkeypatch, limit):
    monkeypatch.setattr(settings.public_access, "rate_limit_per_minute", limit)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/auth/status")
    assert response.status_code == 200, response.text
    assert response.json()["public_access_rate_limit_per_minute"] == limit
    assert "password_hash" not in response.text
