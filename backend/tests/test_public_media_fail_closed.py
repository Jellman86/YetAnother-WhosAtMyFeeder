"""Media access must be established before fetching private upstream bytes."""

from contextlib import asynccontextmanager, closing
from datetime import datetime
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest
from fastapi import HTTPException

from app.auth import AuthContext, AuthLevel
from app.config import settings
from app.main import app
from app.routers import proxy


@pytest.mark.asyncio
@pytest.mark.parametrize("media", ["snapshot", "clip"])
async def test_guest_media_lookup_failure_is_retryable_and_never_grants_access(monkeypatch, media):
    @asynccontextmanager
    async def unavailable_db():
        raise sqlite3.OperationalError("private database path must not reach the response")
        yield

    monkeypatch.setattr(proxy, "get_db", unavailable_db)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, f"show_{'snapshots' if media == 'snapshot' else 'clips'}", True)
    with pytest.raises(HTTPException) as failure:
        await proxy.require_event_access("event_media", AuthContext(AuthLevel.GUEST), "en", media=media)
    assert failure.value.status_code == 503
    assert failure.value.headers == {"Retry-After": "5"}
    assert "private database path" not in failure.value.detail


@pytest.mark.asyncio
async def test_owner_media_access_does_not_depend_on_guest_visibility_lookup(monkeypatch):
    lookup = AsyncMock(side_effect=AssertionError("Owner must not use the guest lookup"))
    monkeypatch.setattr(proxy, "get_db", lookup)
    await proxy.require_event_access("event_media", AuthContext(AuthLevel.OWNER), "en")
    lookup.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, asset",
    [
        ("GET", "snapshot.jpg"),
        ("GET", "thumbnail.jpg"),
        ("GET", "clip.mp4"),
        ("HEAD", "clip.mp4"),
        ("GET", "recording-clip.mp4"),
        ("HEAD", "recording-clip.mp4"),
        ("GET", "hls/master.m3u8"),
        ("GET", "recording-hls/master.m3u8"),
        ("GET", "clip-thumbnails.vtt"),
        ("GET", "clip-thumbnails.jpg"),
    ],
)
async def test_all_guest_media_routes_refuse_failed_visibility_checks(monkeypatch, method, asset):
    @asynccontextmanager
    async def unavailable_db():
        raise sqlite3.OperationalError("database is locked")
        yield

    monkeypatch.setattr(proxy, "get_db", unavailable_db)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.public_access, "show_clips", True)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True)
    upstream = AsyncMock(side_effect=AssertionError("No upstream request may precede visibility checks"))
    monkeypatch.setattr(proxy.frigate_client, "get_event", upstream)
    monkeypatch.setattr(proxy, "get_http_client", upstream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.request(method, f"/api/frigate/event_media/{asset}", headers={"Range": "bytes=0-99"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    upstream.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "journal_mode, locked, expected", [("DELETE", True, 503), ("WAL", True, 404), ("DELETE", False, 404)]
)
async def test_locked_database_cannot_expose_a_hidden_snapshot(monkeypatch, tmp_path, journal_mode, locked, expected):
    # Clone the migrated fixture database; no journal changes touch other tests.
    database_path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(database_path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.execute(
            """INSERT INTO detections
               (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
               VALUES ('private_event', 'private_cam', ?, 1, 0.9, 'Robin', 'Robin', 1)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )
        target.commit()

    @asynccontextmanager
    async def fixture_db():
        async with aiosqlite.connect(database_path, timeout=0.01) as db:
            db.row_factory = aiosqlite.Row
            yield db

    upstream_requests = []

    def upstream(request):
        upstream_requests.append(request)
        return httpx.Response(200, content=b"PRIVATE-SNAPSHOT", headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(proxy, "get_db", fixture_db)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    from app.services.archive_service import archive_service

    monkeypatch.setattr(archive_service, "snapshot_path", AsyncMock(return_value=None))
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        monkeypatch.setattr(proxy, "get_http_client", lambda: upstream_client)
        with closing(sqlite3.connect(database_path)) as writer:
            writer.execute(f"PRAGMA journal_mode={journal_mode}")
            if locked:
                writer.execute("BEGIN EXCLUSIVE")
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://fixture"
                ) as client:
                    response = await client.get("/api/frigate/private_event/snapshot.jpg")
            finally:
                writer.rollback()
    assert response.status_code == expected
    assert b"PRIVATE-SNAPSHOT" not in response.content
    assert upstream_requests == []
