"""A guest's clips follow the owner's switches on every route that serves one, not only the first.

The record offers the same controls wherever it opens; what a guest may watch or download is decided
here, by access. ``show_clips`` off hides every clip route (the answer is the same 404 as an event the
guest may not see), and ``allow_clip_downloads`` off refuses ``?download=1`` on both clip kinds.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers import proxy
from app.services.i18n_service import i18n_service

EVENT = "1795705745.897573-flpb2i"

CLIP_ROUTES = [
    ("HEAD", f"/api/frigate/{EVENT}/clip.mp4"),
    ("GET", f"/api/frigate/{EVENT}/clip.mp4"),
    ("HEAD", f"/api/frigate/{EVENT}/recording-clip.mp4"),
    ("GET", f"/api/frigate/{EVENT}/recording-clip.mp4"),
    ("POST", f"/api/frigate/{EVENT}/recording-clip/fetch"),
    ("GET", f"/api/frigate/{EVENT}/hls/master.m3u8"),
    ("GET", f"/api/frigate/{EVENT}/recording-hls/master.m3u8"),
    ("GET", f"/api/frigate/{EVENT}/clip-thumbnails.vtt"),
    ("GET", f"/api/frigate/{EVENT}/clip-thumbnails.jpg"),
]


@pytest_asyncio.fixture(autouse=True)
async def public_instance(monkeypatch):
    await init_db()
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_clips", True)
    monkeypatch.setattr(settings.public_access, "allow_clip_downloads", False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True)
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (EVENT,))
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                   VALUES (?, 'cam1', ?, 1, 0.9, 'Ring-necked Pheasant', 'Phasianus colchicus', 0)""",
                (EVENT, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            await db.commit()
        yield
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (EVENT,))
            await db.commit()
        await close_db()


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), CLIP_ROUTES)
async def test_a_guest_gets_no_clip_route_while_clips_are_not_shared(monkeypatch, method, path):
    monkeypatch.setattr(settings.public_access, "show_clips", False)
    real_check = proxy.require_event_access
    refusals: list[tuple[str, int]] = []

    async def recording_check(event_id, auth, lang, media="snapshot"):
        try:
            await real_check(event_id, auth, lang, media=media)
        except HTTPException as exc:
            refusals.append((media, exc.status_code))
            raise

    monkeypatch.setattr(proxy, "require_event_access", recording_check)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.request(method, path)
    assert res.status_code == 404
    # The clip switch refused it, not a clip that happens to be missing.
    assert refusals == [("clip", 404)]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [f"/api/frigate/{EVENT}/clip.mp4", f"/api/frigate/{EVENT}/recording-clip.mp4"])
async def test_a_guest_cannot_download_either_clip_kind_without_the_download_switch(path):
    # Access to the event itself is granted, so only the download switch can refuse it.
    with patch("app.routers.proxy.require_event_access", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(f"{path}?download=1")
    assert res.status_code == 403
    assert res.json()["detail"] == i18n_service.translate("errors.proxy.download_forbidden", "en")
