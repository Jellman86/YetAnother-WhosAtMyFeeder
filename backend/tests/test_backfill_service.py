import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.backfill_service import BackfillService


@pytest.mark.asyncio
async def test_process_historical_event_with_timeout_returns_timeout_error():
    service = BackfillService(MagicMock())

    async def _slow(_event):
        await asyncio.sleep(0.05)
        return ("new", None)

    service.process_historical_event = _slow  # type: ignore[method-assign]

    status, reason = await service.process_historical_event_with_timeout(
        {"id": "evt-timeout-1"},
        timeout_seconds=0.01,
    )

    assert status == "error"
    assert reason == "timeout"


@pytest.mark.asyncio
async def test_process_historical_event_with_timeout_passes_success_through():
    service = BackfillService(MagicMock())

    async def _fast(_event):
        return ("skipped", "already_exists")

    service.process_historical_event = _fast  # type: ignore[method-assign]

    status, reason = await service.process_historical_event_with_timeout(
        {"id": "evt-fast-1"},
        timeout_seconds=0.5,
    )

    assert status == "skipped"
    assert reason == "already_exists"
