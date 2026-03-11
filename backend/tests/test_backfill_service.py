import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

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


@pytest.mark.asyncio
async def test_process_historical_event_returns_invalid_score_for_nan_classifier_output(monkeypatch):
    classifier = MagicMock()
    classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Bad Bird", "score": float("nan"), "index": 9}]
    )
    service = BackfillService(classifier)

    image = Image.new("RGB", (8, 8), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    async def _fake_snapshot(*_args, **_kwargs):
        return buffer.getvalue()

    monkeypatch.setattr("app.services.backfill_service.frigate_client.get_snapshot", _fake_snapshot)

    save_mock = AsyncMock(return_value=(True, True))
    service.detection_service.save_detection = save_mock

    status, reason = await service.process_historical_event(
        {
            "id": "evt-nan-score",
            "camera": "front",
            "start_time": 1700000000,
            "top_score": 0.88,
            "sub_label": None,
        }
    )

    assert status == "skipped"
    assert reason == "invalid_score"
    save_mock.assert_not_awaited()
