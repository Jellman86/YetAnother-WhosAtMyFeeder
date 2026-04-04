import asyncio
import time
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
    event_id, camera, skip_delay, fallback_to_snapshot, source = service._pending_queue.get_nowait()
    service._pending_queue.task_done()

    assert event_id == "evt-queue-2"
    assert camera == "cam1"
    assert skip_delay is False
    assert fallback_to_snapshot is False
    assert source == "maintenance"


@pytest.mark.asyncio
async def test_queue_classification_records_job_source_per_job():
    service = AutoVideoClassifierService()

    await service.queue_classification("evt-queue-live", "cam1", source="live")
    event_id, camera, skip_delay, fallback_to_snapshot, source = service._pending_queue.get_nowait()
    service._pending_queue.task_done()

    assert event_id == "evt-queue-live"
    assert camera == "cam1"
    assert skip_delay is True
    assert fallback_to_snapshot is False
    assert source == "live"


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

    queue.assert_awaited_once_with("evt-trigger-1", "cam1", skip_delay=False, source="live")


@pytest.mark.asyncio
async def test_trigger_classification_ignores_open_maintenance_circuit(monkeypatch: pytest.MonkeyPatch):
    service = AutoVideoClassifierService()
    queue = AsyncMock(return_value="queued")
    service.queue_classification = queue  # type: ignore[method-assign]

    monkeypatch.setattr(settings.classification, "auto_video_classification", True)
    monkeypatch.setattr(settings.classification, "video_classification_failure_threshold", 1)

    service._record_failure("evt-maint-open", "video_timeout", source="maintenance")
    assert service.get_status()["maintenance_circuit_open"] is True
    assert service.get_status()["circuit_open"] is False

    await service.trigger_classification("evt-trigger-live-ok", "cam1")

    queue.assert_awaited_once_with("evt-trigger-live-ok", "cam1", skip_delay=False, source="live")


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


# ---------------------------------------------------------------------------
# Circuit-breaker: Frigate-connectivity errors must not count toward threshold
# ---------------------------------------------------------------------------

FRIGATE_SIDE_ERROR_CODES = [
    # Precheck / event lookup
    "event_not_found",
    "event_timeout",
    "event_request_error",
    "event_unknown_error",
    "event_http_404",
    "event_http_500",
    "event_http_503",
    # Clip fetch
    "clip_not_retained",
    "clip_not_found",
    "clip_timeout",
    "clip_request_error",
    "clip_unknown_error",
    "clip_http_400",
    "clip_http_502",
    "clip_invalid",
    "clip_decode_failed",
    # Task lifecycle
    "video_cancelled",
]

ML_INFERENCE_ERROR_CODES = [
    "video_timeout",
    "video_no_results",
    "video_exception",
]


@pytest.mark.asyncio
async def test_frigate_connectivity_errors_do_not_increment_failure_count():
    """Every Frigate-side error code must be silently ignored by the circuit breaker."""
    service = AutoVideoClassifierService()
    for i, code in enumerate(FRIGATE_SIDE_ERROR_CODES):
        service._record_failure(f"evt-frigate-{i}", code)

    status = service.get_status()
    assert status["failure_count"] == 0, (
        f"Expected 0 failures after Frigate-side errors, got {status['failure_count']}"
    )
    assert status["circuit_open"] is False


@pytest.mark.asyncio
async def test_frigate_connectivity_errors_do_not_open_circuit_at_threshold(monkeypatch):
    """Accumulating Frigate errors past the configured threshold must not open the circuit."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        3,
    )
    service = AutoVideoClassifierService()

    # Drive 5 Frigate-side failures — more than the threshold of 3.
    for i in range(5):
        service._record_failure(f"evt-fc-{i}", "event_not_found")

    status = service.get_status()
    assert status["circuit_open"] is False


@pytest.mark.asyncio
async def test_process_event_precheck_failures_do_not_increment_circuit_count(monkeypatch):
    """Frigate precheck failures must pass their error code through to _record_failure()."""
    service = AutoVideoClassifierService()

    monkeypatch.setattr(
        auto_video_classifier_module.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=(None, "event_http_503")),
    )
    monkeypatch.setattr(auto_video_classifier_module.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(service, "_update_status", AsyncMock())
    monkeypatch.setattr(service, "_auto_delete_if_missing", AsyncMock())
    monkeypatch.setattr(service, "_record_diagnostic", lambda *args, **kwargs: None)

    await service._process_event("evt-precheck-1", "cam1", skip_delay=True)

    status = service.get_status()
    assert status["failure_count"] == 0
    assert status["circuit_open"] is False


@pytest.mark.asyncio
async def test_ml_inference_errors_do_increment_failure_count():
    """ML inference failure codes must count toward the circuit-breaker threshold."""
    service = AutoVideoClassifierService()
    for i, code in enumerate(ML_INFERENCE_ERROR_CODES):
        service._record_failure(f"evt-ml-{i}", code)

    status = service.get_status()
    assert status["failure_count"] == len(ML_INFERENCE_ERROR_CODES)


@pytest.mark.asyncio
async def test_ml_inference_errors_open_circuit_at_threshold(monkeypatch):
    """Enough ML inference failures must open the circuit breaker."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        3,
    )
    service = AutoVideoClassifierService()

    for i in range(3):
        service._record_failure(f"evt-ml-open-{i}", "video_timeout")

    status = service.get_status()
    assert status["circuit_open"] is True


@pytest.mark.asyncio
async def test_maintenance_ml_inference_errors_open_only_maintenance_circuit(monkeypatch):
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        2,
    )
    service = AutoVideoClassifierService()

    service._record_failure("evt-maint-1", "video_timeout", source="maintenance")
    service._record_failure("evt-maint-2", "video_timeout", source="maintenance")

    status = service.get_status()
    assert status["circuit_open"] is False
    assert status["failure_count"] == 0
    assert status["maintenance_circuit_open"] is True
    assert status["maintenance_failure_count"] == 2


@pytest.mark.asyncio
async def test_mixed_errors_only_ml_failures_count_toward_circuit(monkeypatch):
    """Interleaved Frigate and ML errors: only ML errors push the counter forward."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        3,
    )
    service = AutoVideoClassifierService()

    # Two ML failures and many Frigate failures — circuit must stay closed.
    service._record_failure("evt-m1", "video_timeout")
    service._record_failure("evt-f1", "event_not_found")
    service._record_failure("evt-f2", "clip_timeout")
    service._record_failure("evt-f3", "event_http_503")
    service._record_failure("evt-m2", "video_exception")

    status = service.get_status()
    assert status["failure_count"] == 2
    assert status["circuit_open"] is False


# ---------------------------------------------------------------------------
# reset_circuit: lightweight circuit reset without queue drain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_circuit_clears_circuit_state(monkeypatch):
    """reset_circuit() must clear failure state and reclose the circuit."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        2,
    )
    service = AutoVideoClassifierService()

    service._record_failure("evt-rc-1", "video_timeout")
    service._record_failure("evt-rc-2", "video_exception")
    assert service.get_status()["circuit_open"] is True

    service.reset_circuit()

    status = service.get_status()
    assert status["circuit_open"] is False
    assert status["failure_count"] == 0


@pytest.mark.asyncio
async def test_reset_circuit_preserves_pending_queue(monkeypatch):
    """reset_circuit() must leave pending queue entries intact."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        2,
    )
    service = AutoVideoClassifierService()

    await service.queue_classification("evt-q1", "cam1")
    await service.queue_classification("evt-q2", "cam1")

    service._record_failure("evt-rc-1", "video_timeout")
    service._record_failure("evt-rc-2", "video_timeout")
    assert service.get_status()["circuit_open"] is True

    service.reset_circuit()

    # Queue must still have both items.
    assert service.get_status()["pending"] == 2
    assert service.get_status()["circuit_open"] is False


# ---------------------------------------------------------------------------
# get_circuit_status: open_until must be UTC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_status_open_until_is_utc(monkeypatch):
    """open_until in get_circuit_status() must carry a UTC offset."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        1,
    )
    service = AutoVideoClassifierService()
    service._record_failure("evt-utc-1", "video_timeout")

    status = service.get_circuit_status()
    assert status["open"] is True
    open_until = status["open_until"]
    assert open_until is not None
    # A UTC-aware isoformat string ends with "+00:00".
    assert open_until.endswith("+00:00"), (
        f"Expected UTC offset in open_until, got: {open_until!r}"
    )


# ---------------------------------------------------------------------------
# Circuit breaker auto-close after cooldown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_auto_closes_after_cooldown_expires(monkeypatch):
    """The circuit must auto-close and clear failure history once the cooldown elapses."""
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_threshold",
        2,
    )
    monkeypatch.setattr(
        settings.classification,
        "video_classification_failure_cooldown_minutes",
        5,
    )
    service = AutoVideoClassifierService()

    # Open the circuit.
    service._record_failure("evt-ac-1", "video_timeout")
    service._record_failure("evt-ac-2", "video_exception")
    assert service._is_circuit_open() is True
    assert service.get_status()["failure_count"] == 2

    # Advance time past the cooldown window (5 min = 300 s).
    service._circuit_open_until = time.time() - 1

    assert service._is_circuit_open() is False
    # Failure history must be cleared after the cooldown auto-close.
    assert service.get_status()["failure_count"] == 0
    assert len(service._failure_events) == 0
    assert len(service._failure_event_ids) == 0
