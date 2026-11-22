"""A custom backfill range is read as calendar days in the X-Timezone zone, else TZ, else UTC."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.routers import backfill as backfill_router
from app.services.backfill_service import BackfillResult

pytestmark = pytest.mark.usefixtures("history_pool")

ONE_DAY = {"date_range": "custom", "start_date": "2026-04-10", "end_date": "2026-04-10"}


@pytest_asyncio.fixture
async def ranges(monkeypatch) -> list[tuple[datetime, datetime]]:
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    seen: list[tuple[datetime, datetime]] = []

    async def run_backfill(start, end, cameras):
        seen.append((start, end))
        return BackfillResult()

    monkeypatch.setattr(backfill_router.backfill_service, "run_backfill", run_backfill)
    # Only the range is under test: another suite's maintenance work must not answer 409 here.
    monkeypatch.setattr(backfill_router.maintenance_coordinator, "try_acquire", AsyncMock(return_value=True))
    monkeypatch.setattr(backfill_router.maintenance_coordinator, "release", AsyncMock())
    return seen


async def _post(headers: dict[str, str]) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/backfill", json=ONE_DAY, headers=headers)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_a_backfill_day_without_a_header_is_the_instance_day(ranges, monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")

    await _post({})

    # Midnight to midnight in New York (UTC-4 in April), as curl or Home Assistant would mean it.
    assert ranges == [(datetime(2026, 4, 10, 4, tzinfo=timezone.utc), datetime(2026, 4, 11, 4, tzinfo=timezone.utc))]


@pytest.mark.asyncio
async def test_a_backfill_day_with_a_header_is_the_viewers_day(ranges, monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")

    await _post({"X-Timezone": "Europe/Berlin"})

    assert ranges == [(datetime(2026, 4, 9, 22, tzinfo=timezone.utc), datetime(2026, 4, 10, 22, tzinfo=timezone.utc))]
