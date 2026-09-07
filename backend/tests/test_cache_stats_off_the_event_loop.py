"""The media cache stats walk must never run on the event loop.

`GET /api/cache/stats` stats every cached file. The owner system checks call it
once a minute from every owner page, so on a slow filesystem an inline walk
stalled the whole API for as long as the walk took (#300). Off the loop, the
walks must not multiply either: every open owner page and every client retry
would otherwise start its own walk against the same slow disk.
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


def _slow_walk_counting_calls(service, seconds: float):
    """Replace the sync walk with one that sleeps first and counts how often it ran."""
    calls: list[int] = []
    real_walk = service._get_cache_stats_sync

    def slow_walk():
        calls.append(threading.get_ident())
        time.sleep(seconds)
        return real_walk()

    service._get_cache_stats_sync = slow_walk
    return calls


@pytest.mark.asyncio
async def test_the_walk_runs_on_a_worker_thread_not_the_loop(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=3, clips=1)
    walk_threads = _slow_walk_counting_calls(service, 0.0)

    stats = await service.get_cache_stats()

    assert walk_threads, "the walk never ran"
    assert walk_threads[0] != threading.get_ident(), "the walk ran on the event loop thread"
    assert stats["snapshot_count"] == 3
    assert stats["clip_count"] == 1


@pytest.mark.asyncio
async def test_the_loop_keeps_serving_while_a_slow_filesystem_is_walked(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch)
    _slow_walk_counting_calls(service, 0.3)

    ticks = 0

    async def tick_while_walking():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.02)

    ticker = asyncio.create_task(tick_while_walking())
    try:
        await service.get_cache_stats()
    finally:
        ticker.cancel()

    assert ticks >= 5, f"the loop only ran {ticks} times during a 300ms walk; it was blocked"


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_walk(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=2)
    calls = _slow_walk_counting_calls(service, 0.2)

    results = await asyncio.gather(*(service.get_cache_stats() for _ in range(6)))

    assert len(calls) == 1, f"six concurrent requests started {len(calls)} walks"
    assert all(r["snapshot_count"] == 2 for r in results)


@pytest.mark.asyncio
async def test_a_later_caller_gets_a_fresh_walk_once_the_first_has_finished(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=1)
    calls = _slow_walk_counting_calls(service, 0.0)

    await service.get_cache_stats()
    (media_cache_module.SNAPSHOTS_DIR / "evt_new.jpg").write_bytes(b"z")
    later = await service.get_cache_stats()

    assert len(calls) == 2, "a finished walk must not be served as if it were still current"
    assert later["snapshot_count"] == 2


@pytest.mark.asyncio
async def test_a_caller_that_gives_up_does_not_cancel_the_walk_for_others(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=1)
    calls = _slow_walk_counting_calls(service, 0.3)

    impatient = asyncio.create_task(service.get_cache_stats())
    patient = asyncio.create_task(service.get_cache_stats())
    await asyncio.sleep(0.05)
    impatient.cancel()
    with pytest.raises(asyncio.CancelledError):
        await impatient

    stats = await patient

    assert stats["snapshot_count"] == 1
    assert len(calls) == 1, "the patient caller should have finished on the shared walk, not started another"


@pytest.mark.asyncio
async def test_a_slow_walk_is_logged_with_its_size_and_location(tmp_path, monkeypatch):
    service = _service_with_cache(tmp_path, monkeypatch, snapshots=2, clips=2)
    monkeypatch.setattr(media_cache_module, "SLOW_CACHE_WALK_WARN_MS", 0.0)

    with structlog.testing.capture_logs() as captured:
        await service.get_cache_stats()

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
        await service.get_cache_stats()

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

    monkeypatch.setattr(settings_router.media_cache, "_get_cache_stats_sync", recording_walk)

    response = await owner_client.get("/api/cache/stats")

    assert response.status_code == 200, response.text
    assert response.json()["snapshot_count"] == 1
    assert walk_threads and walk_threads[0] != loop_thread, "the route walked the cache on the event loop"
