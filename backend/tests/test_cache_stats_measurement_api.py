"""Each storage poll is short even when the shared filesystem walk has not returned."""

import asyncio

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.routers import settings as settings_router
from app.services.cache_stats_measurements import CacheStatsMeasurements


@pytest_asyncio.fixture
async def owner_client():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_owner, None)


def stats():
    return {
        **{
            f"{kind}_{field}": 0
            for kind in ("snapshot", "clip", "preview")
            for field in ("count", "size_bytes", "size_mb")
        },
        "total_size_bytes": 1024,
        "total_size_mb": 0.01,
        "storage_available": True,
        "cache_clips": False,
        "retention_days": 0,
        "retention_source": "detection",
    }


@pytest.mark.asyncio
async def test_owner_can_poll_one_walk_through_short_requests(owner_client, monkeypatch):
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        await release.wait()
        return stats()

    measurements = CacheStatsMeasurements(collect)
    monkeypatch.setattr(settings_router, "cache_stats_measurements", measurements)
    try:
        first = await asyncio.wait_for(owner_client.get("/api/cache/measurement"), 1)
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-store"
        payload = first.json()
        assert payload["status"] == "running" and payload["stats"] is None
        for _ in range(3):
            response = await asyncio.wait_for(
                owner_client.get("/api/cache/measurement", params={"measurement_id": payload["id"]}), 1
            )
            assert response.json()["status"] == "running"
        assert calls == 1
        release.set()
        await asyncio.sleep(0)
        completed = await owner_client.get("/api/cache/measurement", params={"measurement_id": payload["id"]})
        assert completed.json()["status"] == "completed"
        assert completed.json()["stats"]["total_size_bytes"] == 1024
        assert calls == 1
    finally:
        release.set()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_missing_poll_id_returns_404_without_starting_a_walk(owner_client, monkeypatch):
    async def collect():
        pytest.fail("A missing poll id must not start storage I/O")

    monkeypatch.setattr(settings_router, "cache_stats_measurements", CacheStatsMeasurements(collect))
    response = await owner_client.get("/api/cache/measurement", params={"measurement_id": "expired"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_measurement_is_owner_only(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/cache/measurement")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_poll_returns_while_the_legacy_stats_request_is_still_waiting(owner_client, monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def collect():
        entered.set()
        await release.wait()
        return stats()

    monkeypatch.setattr(settings_router, "_collect_cache_stats", collect)
    monkeypatch.setattr(settings_router, "cache_stats_measurements", CacheStatsMeasurements(collect))
    legacy = asyncio.create_task(owner_client.get("/api/cache/stats"))
    try:
        await entered.wait()
        assert not legacy.done()
        poll = await asyncio.wait_for(owner_client.get("/api/cache/measurement"), 1)
        assert poll.status_code == 200 and poll.json()["status"] == "running"
        assert not legacy.done()
    finally:
        release.set()
        response = await legacy
        assert response.status_code == 200
        await asyncio.sleep(0)
