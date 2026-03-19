import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import auto_video_classifier_service as auto_video_classifier_module
from app.config import settings

AutoVideoClassifierService = auto_video_classifier_module.AutoVideoClassifierService


@pytest.mark.asyncio
async def test_queue_classification_dedupes_pending_event_ids():
    service = AutoVideoClassifierService()

    first = await service.queue_classification("evt-queue-1", "cam1")
    second = await service.queue_classification("evt-queue-1", "cam1")

    assert first == "queued"
    assert second == "duplicate"
    assert service.get_status()["pending"] == 1


@pytest.mark.asyncio
async def test_queue_classification_records_skip_delay_flag_per_job():
    service = AutoVideoClassifierService()

    await service.queue_classification("evt-queue-2", "cam1", skip_delay=False)
    event_id, camera, skip_delay, fallback_to_snapshot = service._pending_queue.get_nowait()
    service._pending_queue.task_done()

    assert event_id == "evt-queue-2"
    assert camera == "cam1"
    assert skip_delay is False
    assert fallback_to_snapshot is False


@pytest.mark.asyncio
async def test_queue_classification_respects_bounded_capacity(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auto_video_classifier_module, "MAX_PENDING_QUEUE", 2)
    service = AutoVideoClassifierService()

    first = await service.queue_classification("evt-capacity-1", "cam1")
    second = await service.queue_classification("evt-capacity-2", "cam1")
    third = await service.queue_classification("evt-capacity-3", "cam1")

    assert first == "queued"
    assert second == "queued"
    assert third == "full"
    assert service.get_status()["pending"] == 2
    assert service.get_status()["pending_available"] == 0


@pytest.mark.asyncio
async def test_queue_classification_dedupes_under_concurrent_enqueues():
    service = AutoVideoClassifierService()

    results = await asyncio.gather(*[
        service.queue_classification("evt-race-1", "cam1")
        for _ in range(20)
    ])

    assert results.count("queued") == 1
    assert results.count("duplicate") == 19
    assert service.get_status()["pending"] == 1


@pytest.mark.asyncio
async def test_get_status_prunes_completed_active_tasks():
    service = AutoVideoClassifierService()

    async def _done():
        return None

    task = asyncio.create_task(_done())
    await task
    service._active_tasks["evt-finished-1"] = task

    status = service.get_status()

    assert status["active"] == 0
    assert "evt-finished-1" not in service._active_tasks


@pytest.mark.asyncio
async def test_trigger_classification_uses_bounded_queue_path(monkeypatch: pytest.MonkeyPatch):
    service = AutoVideoClassifierService()
    queue = AsyncMock(return_value="queued")
    service.queue_classification = queue  # type: ignore[method-assign]

    monkeypatch.setattr(settings.classification, "auto_video_classification", True)

    await service.trigger_classification("evt-trigger-1", "cam1")

    queue.assert_awaited_once_with("evt-trigger-1", "cam1", skip_delay=False)


@pytest.mark.asyncio
async def test_wait_for_clip_stops_retrying_on_terminal_clip_not_retained(monkeypatch: pytest.MonkeyPatch):
    service = AutoVideoClassifierService()
    fetch = AsyncMock(return_value=(None, "clip_not_retained"))
    monkeypatch.setattr(auto_video_classifier_module.frigate_client, "get_clip_with_error", fetch)
    monkeypatch.setattr(settings.classification, "video_classification_delay", 0)
    monkeypatch.setattr(settings.classification, "video_classification_max_retries", 4)
    monkeypatch.setattr(settings.classification, "video_classification_retry_interval", 0)

    clip_bytes, error = await service._wait_for_clip("evt-no-recordings", skip_delay=True)

    assert clip_bytes is None
    assert error == "clip_not_retained"
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_terminal_missing_clip_does_not_open_circuit():
    service = AutoVideoClassifierService()

    service._record_failure("evt-a", "clip_not_retained")
    service._record_failure("evt-b", "clip_not_retained")
    service._record_failure("evt-c", "clip_not_retained")

    status = service.get_status()
    assert status["failure_count"] == 0
    assert status["circuit_open"] is False
