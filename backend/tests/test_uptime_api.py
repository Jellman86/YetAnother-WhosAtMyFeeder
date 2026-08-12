from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.database import get_db, init_db, close_db
from app.main import app
from app.repositories.health_repository import HealthRepository
from app.services.uptime import HEARTBEAT_INTERVAL_MINUTES


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM health_samples")
        await db.commit()
    try:
        yield
    finally:
        await close_db()


async def _seed(minutes_back: int, count: int, step: int = HEARTBEAT_INTERVAL_MINUTES) -> None:
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        repo = HealthRepository(db)
        for index in range(count):
            await repo.record_heartbeat("test-instance", now - timedelta(minutes=minutes_back - index * step))


@pytest.mark.asyncio
async def test_uptime_reports_recent_heartbeats_as_up(client):
    await _seed(minutes_back=120, count=25)

    response = await client.get("/api/stats/uptime?hours=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["heartbeat_interval_minutes"] == HEARTBEAT_INTERVAL_MINUTES
    assert len(payload["buckets"]) == 24
    assert any(bucket["state"] == "up" for bucket in payload["buckets"])


@pytest.mark.asyncio
async def test_window_with_no_history_is_unknown_not_an_outage(client):
    response = await client.get("/api/stats/uptime?hours=24")

    assert response.status_code == 200
    payload = response.json()
    assert all(bucket["state"] == "unknown" for bucket in payload["buckets"])
    assert payload["uptime_ratio"] is None


@pytest.mark.asyncio
async def test_a_gap_between_heartbeats_is_reported(client):
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        repo = HealthRepository(db)
        for offset in (600, 595, 590):
            await repo.record_heartbeat("test-instance", now - timedelta(minutes=offset))
        for offset in (30, 25, 20):
            await repo.record_heartbeat("test-instance", now - timedelta(minutes=offset))

    response = await client.get("/api/stats/uptime?hours=24")

    payload = response.json()
    assert payload["longest_gap_minutes"] >= 500
    assert payload["longest_gap_start"] is not None
    assert any(bucket["state"] == "down" for bucket in payload["buckets"])


@pytest.mark.asyncio
async def test_window_bounds_are_validated(client):
    assert (await client.get("/api/stats/uptime?hours=0")).status_code == 422
    assert (await client.get("/api/stats/uptime?hours=999")).status_code == 422
    assert (await client.get("/api/stats/uptime?bucket_minutes=1")).status_code == 422


@pytest.mark.asyncio
async def test_pruning_drops_only_rows_past_retention(client):
    await _seed(minutes_back=60, count=3)
    async with get_db() as db:
        repo = HealthRepository(db)
        await repo.record_heartbeat("test-instance", datetime.now(timezone.utc) - timedelta(days=30))
        removed = await repo.prune(retention_days=7)
        remaining = await repo.list_samples_since(datetime.now(timezone.utc) - timedelta(days=365))

    assert removed == 1
    assert len(remaining) == 3
