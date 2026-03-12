import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.services.backfill_service import BackfillService
from app.services.classifier_service import BackgroundImageClassificationUnavailableError


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


@pytest.mark.asyncio
async def test_process_historical_event_passes_frigate_score_into_filtering(monkeypatch):
    classifier = MagicMock()
    classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Wood Pigeon", "score": 0.82, "index": 3}]
    )
    service = BackfillService(classifier)

    image = Image.new("RGB", (8, 8), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    async def _fake_snapshot(*_args, **_kwargs):
        return buffer.getvalue()

    monkeypatch.setattr("app.services.backfill_service.frigate_client.get_snapshot", _fake_snapshot)

    observed: dict[str, object] = {}

    def _fake_filter(result, frigate_event, sub_label, frigate_score=None):
        observed["result"] = result
        observed["frigate_event"] = frigate_event
        observed["sub_label"] = sub_label
        observed["frigate_score"] = frigate_score
        return result, "threshold_passed"

    save_mock = AsyncMock(return_value=(True, True))
    service.detection_service.filter_and_label = _fake_filter  # type: ignore[method-assign]
    service.detection_service.save_detection = save_mock

    status, reason = await service.process_historical_event(
        {
            "id": "evt-frigate-score",
            "camera": "front",
            "start_time": 1700000000,
            "sub_label": "Columba palumbus",
            "data": {"top_score": 0.91},
        }
    )

    assert status == "new"
    assert reason is None
    assert observed["frigate_score"] == pytest.approx(0.91)
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_historical_event_returns_classifier_worker_reason(monkeypatch):
    classifier = MagicMock()
    classifier.classify_async_background = AsyncMock(
        side_effect=BackgroundImageClassificationUnavailableError("background_image_worker_unavailable")
    )
    service = BackfillService(classifier)

    image = Image.new("RGB", (8, 8), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    async def _fake_snapshot(*_args, **_kwargs):
        return buffer.getvalue()

    monkeypatch.setattr("app.services.backfill_service.frigate_client.get_snapshot", _fake_snapshot)

    status, reason = await service.process_historical_event(
        {
            "id": "evt-worker-unavailable",
            "camera": "front",
            "start_time": 1700000000,
        }
    )

    assert status == "error"
    assert reason == "background_image_worker_unavailable"


@pytest.mark.asyncio
async def test_process_historical_event_with_timeout_retries_transient_classifier_failure():
    service = BackfillService(MagicMock())
    attempts: list[str] = []

    async def _flaky(_event):
        attempts.append("attempt")
        if len(attempts) == 1:
            return "error", "background_image_worker_unavailable"
        return "new", None

    service.process_historical_event = _flaky  # type: ignore[method-assign]

    status, reason = await service.process_historical_event_with_timeout(
        {"id": "evt-transient-worker-failure"},
        timeout_seconds=20.0,
    )

    assert attempts == ["attempt", "attempt"]
    assert status == "new"
    assert reason is None


@pytest.mark.asyncio
async def test_fetch_frigate_events_paginates_until_exhausted(monkeypatch):
    classifier = MagicMock()
    service = BackfillService(classifier)

    page_one = [{"id": f"evt-{idx}", "start_time": 2000 - idx} for idx in range(100)]
    page_two = [{"id": f"evt-{100 + idx}", "start_time": 1900 - idx} for idx in range(100)]
    page_three = [{"id": f"evt-{200 + idx}", "start_time": 1800 - idx} for idx in range(35)]
    seen_before_values: list[float] = []

    async def _fake_list_events(*, after=None, before=None, **_kwargs):
        seen_before_values.append(float(before))
        if len(seen_before_values) == 1:
            return page_one
        if len(seen_before_values) == 2:
            return page_two
        return page_three

    monkeypatch.setattr("app.services.backfill_service.frigate_client.list_events", _fake_list_events)

    events = await service.fetch_frigate_events(after_ts=1000.0, before_ts=3000.0, cameras=["front"])

    assert len(events) == 235
    assert events[0]["id"] == "evt-0"
    assert events[-1]["id"] == "evt-234"
    assert seen_before_values[0] == pytest.approx(3000.0)
    assert seen_before_values[1] < seen_before_values[0]
