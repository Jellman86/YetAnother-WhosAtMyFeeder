"""The media cache stats walk must never run on the event loop.

`GET /api/cache/stats` stats every cached file. The owner system checks call it
once a minute from every owner page, so on a slow filesystem an inline walk
stalled the whole API for as long as the walk took (#300).
"""

import asyncio
import threading
import time

import httpx
import pytest
import pytest_asyncio
import structlog

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.services import media_cache as media_cache_module


def _service_with_cache(tmp_path, monkeypatch, *, snapshots: int = 0, clips: int = 0):
    cache_base = tmp_path / "media_cache"
    snapshots_dir = cache_base / "snapshots"
    clips_dir = cache_base / "clips"
    previews_dir = cache_base / "previews"
    for directory in (snapshots_dir, clips_dir, previews_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for index in range(snapshots):
        (snapshots_dir / f"evt_{index}.jpg").write_bytes(b"x" * 10)
    for index in range(clips):
        (clips_dir / f"evt_{index}.mp4").write_bytes(b"y" * 100)

    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", cache_base)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", clips_dir)
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", previews_dir)
    return media_cache_module.MediaCacheService()


@pytest.mark.asyncio
async def test_the_walk_runs_on_a_worker_thread_not_the_loop(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=3, clips=1)
    walk_threads: list[int] = []
    original_walk = service.get_cache_stats

    def recording_walk():
        walk_threads.append(threading.get_ident())
        return original_walk()

    monkeypatch.setattr(service, "get_cache_stats", recording_walk)

    stats = await service.get_cache_stats_off_loop()

    assert walk_threads, "the walk never ran"
    assert walk_threads[0] != threading.get_ident(), "the walk ran on the event loop thread"
    assert stats["snapshot_count"] == 3
    assert stats["clip_count"] == 1


@pytest.mark.asyncio
async def test_the_loop_keeps_serving_while_a_slow_filesystem_is_walked(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch)

    def slow_walk():
        time.sleep(0.3)
        return service.__class__.get_cache_stats(service)

    monkeypatch.setattr(service, "get_cache_stats", slow_walk)

    ticks = 0

    async def tick_while_walking():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.02)

    ticker = asyncio.create_task(tick_while_walking())
    try:
        await service.get_cache_stats_off_loop()
    finally:
        ticker.cancel()

    assert ticks >= 5, f"the loop only ran {ticks} times during a 300ms walk; it was blocked"


@pytest.mark.asyncio
async def test_a_slow_walk_is_logged_with_its_size_and_location(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=2, clips=2)
    monkeypatch.setattr(media_cache_module, "SLOW_CACHE_WALK_WARN_MS", 0.0)

    with structlog.testing.capture_logs() as captured:
        await service.get_cache_stats_off_loop()

    slow = [entry for entry in captured if entry["event"] == "Slow media cache walk"]
    assert len(slow) == 1
    assert slow[0]["files"] == 4
    assert slow[0]["cache_dir"] == str(tmp_path / "media_cache")
    assert slow[0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_a_fast_walk_is_not_logged(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=1)
    monkeypatch.setattr(media_cache_module, "SLOW_CACHE_WALK_WARN_MS", 60_000.0)

    with structlog.testing.capture_logs() as captured:
        await service.get_cache_stats_off_loop()

    assert not [entry for entry in captured if entry["event"] == "Slow media cache walk"]


@pytest_asyncio.fixture
async def owner_client():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_the_cache_stats_route_walks_off_the_loop(owner_client, monkeypatch):
    from app.routers import settings as settings_router

    loop_thread = threading.get_ident()
    walk_threads: list[int] = []

    def recording_walk():
        walk_threads.append(threading.get_ident())
        return {
            "snapshot_count": 1,
            "snapshot_size_bytes": 10,
            "snapshot_size_mb": 0.0,
            "clip_count": 0,
            "clip_size_bytes": 0,
            "clip_size_mb": 0.0,
            "preview_count": 0,
            "preview_size_bytes": 0,
            "preview_size_mb": 0.0,
            "total_size_bytes": 10,
            "total_size_mb": 0.0,
            "oldest_file": None,
            "newest_file": None,
        }

    monkeypatch.setattr(settings_router.media_cache, "get_cache_stats", recording_walk)

    response = await owner_client.get("/api/cache/stats")

    assert response.status_code == 200, response.text
    assert response.json()["snapshot_count"] == 1
    assert walk_threads and walk_threads[0] != loop_thread, "the route walked the cache on the event loop"
