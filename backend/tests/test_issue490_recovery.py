"""Keep a stalled native call from consuming the rest of a backfill (#490)."""

import asyncio
import threading
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.config import settings
from app.services import classifier_service as classifier_module
from app.services.auto_video_classifier_service import AutoVideoClassifierService
from app.services.backfill_service import BackfillService
from app.services.classification_admission import ClassificationLeaseExpiredError
from app.services.classifier_service import (
    BackgroundImageClassificationUnavailableError,
    ClassifierService,
    LiveImageClassificationOverloadedError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", ["live", "background"])
async def test_native_timeout_moves_next_work_to_workers_without_waiting_for_stuck_thread(monkeypatch, priority):
    monkeypatch.setattr(settings.classification, "image_execution_mode", "in_process")
    monkeypatch.setattr(settings.classification, "personalized_rerank_enabled", False)
    monkeypatch.setattr(settings.classification, "live_worker_count", 1)
    monkeypatch.setattr(settings.classification, "background_worker_count", 1)
    for name in ("CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS", "CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS"):
        monkeypatch.setattr(classifier_module, name, 0.05)
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    result = [{"label": "Parus major", "score": 0.9}]

    def stuck_native(*args):
        started.set()
        try:
            release.wait(5)
            return result
        finally:
            finished.set()

    supervisor = MagicMock()
    supervisor.classify = AsyncMock(return_value=result)
    supervisor.shutdown = AsyncMock()
    supervisor.get_metrics.return_value = {
        "live": {"workers": 1, "runtime": {"inference_backend": "openvino", "active_provider": "intel_gpu"}},
        "background": {"workers": 1},
    }
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService(supervisor=supervisor)
    service.classify = MagicMock(side_effect=stuck_native)
    service._inference_backend = "openvino"
    service._active_inference_provider = "intel_gpu"
    service._resolve_active_model_id = lambda: "test-model"
    image = Image.new("RGB", (16, 16))
    classify = service.classify_async_live if priority == "live" else service.classify_async_background
    expected_error = (
        ClassificationLeaseExpiredError if priority == "live" else BackgroundImageClassificationUnavailableError
    )
    try:
        with pytest.raises(expected_error):
            await classify(image)
        assert started.is_set() and not finished.is_set()
        assert service._image_execution_mode == "subprocess"
        recovery = service.latest_runtime_recovery()
        assert recovery["status"] == "recovering"
        assert recovery["reason"] == "in_process_lease_expired"
        assert service.check_health()["status"] != "ok"
        assert await service.classify_async_live(image) == result
        assert await service.classify_async_background(image) == result
        assert service.classify.call_count == 1
        assert supervisor.classify.await_count == 2
        assert service.get_admission_status()["live"]["capacity"] == 1
        assert service.latest_runtime_recovery()["status"] == "recovered"
        assert service.get_status()["inference_health"]["last_recovery"]["status"] == "recovered"
        assert service.check_health()["runtime_recovery"]["last_recovery"]["status"] == "recovered"
        assert service._subprocess_runtime_identity(supervisor.get_metrics())[2] == "worker"
        with pytest.raises(LiveImageClassificationOverloadedError):
            await service._classify_in_process_as_last_resort(
                priority="live", image=image, camera_name=None, model_id=None, input_context=None
            )
        assert service.classify.call_count == 1
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)
        await service.shutdown()


@pytest.mark.asyncio
async def test_recovered_quarantine_does_not_hide_new_worker_failure():
    from app.services.inference_health import RuntimeKey

    supervisor = MagicMock()
    supervisor.shutdown = AsyncMock()
    supervisor.classify = AsyncMock(return_value=[])
    metrics = {"live": {"workers": 1}, "background": {"workers": 1}}
    supervisor.get_metrics.return_value = metrics
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService(supervisor=supervisor)
    try:
        service._isolate_expired_native_runtime("live", RuntimeKey("openvino", "intel_gpu", "test"))
        await service.classify_async_live(Image.new("RGB", (16, 16)))
        failure = {"status": "failed", "reason": "worker_failed", "at": service.latest_runtime_recovery()["at"] + 1}
        metrics["live"]["last_runtime_recovery"] = failure
        assert service.check_health()["runtime_recovery"]["last_recovery"]["reason"] == "worker_failed"
        assert service.check_health()["status"] == "error"
        assert service.get_status()["inference_health"]["last_recovery"]["reason"] == "worker_failed"
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_late_invalid_native_result_cannot_start_another_model_recovery():
    from app.services.inference_health import RuntimeKey
    from app.services.classifier_service import InvalidInferenceOutputError

    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService()
    model = MagicMock()
    service._models["bird"] = model
    service._attempt_gpu_retry_after_invalid_output = MagicMock(return_value=True)
    try:
        service._isolate_expired_native_runtime("live", RuntimeKey("openvino", "intel_gpu", "test"))
        error = InvalidInferenceOutputError(backend="openvino", provider="intel_gpu", detail="late invalid output")
        assert service._recover_from_invalid_bird_output(model, error) is False
        service._attempt_gpu_retry_after_invalid_output.assert_not_called()
        model.cleanup.assert_not_called()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_model_reload_retains_quarantined_native_model():
    from app.services.inference_health import RuntimeKey

    supervisor = MagicMock()
    supervisor.restart_pool = AsyncMock()
    supervisor.shutdown = AsyncMock()
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService(supervisor=supervisor)
    model = MagicMock()
    service._models["bird"] = model
    try:
        service._isolate_expired_native_runtime("live", RuntimeKey("openvino", "intel_gpu", "test"))
        await service.reload_bird_model()
        model.cleanup.assert_not_called()
        assert service._models["bird"] is model
        supervisor.restart_pool.assert_awaited_once()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_wildlife_uses_workers_after_native_quarantine():
    from app.services.inference_health import RuntimeKey

    supervisor = MagicMock()
    supervisor.shutdown = AsyncMock()
    supervisor.classify = AsyncMock(return_value=[{"label": "Fox", "score": 0.9}])
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService(supervisor=supervisor)
    service.classify_wildlife = MagicMock(side_effect=AssertionError("native runtime must not be reused"))
    try:
        service._isolate_expired_native_runtime("live", RuntimeKey("openvino", "intel_gpu", "test"))
        result = await service.classify_wildlife_async(Image.new("RGB", (16, 16)), input_context={"is_cropped": True})
        assert result[0]["label"] == "Fox"
        assert supervisor.classify.await_args.kwargs["model_kind"] == "wildlife"
        assert supervisor.classify.await_args.kwargs["input_context"]["is_cropped"] is True
        service.classify_wildlife.assert_not_called()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_wildlife_reload_restarts_background_workers_without_loading_in_parent(monkeypatch):
    monkeypatch.setattr(settings.classification, "image_execution_mode", "subprocess")
    supervisor = MagicMock()
    supervisor.restart_pool = AsyncMock()
    supervisor.shutdown = AsyncMock()
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService(supervisor=supervisor)
    service._get_wildlife_model = MagicMock()
    try:
        await service.reload_wildlife_model()
        supervisor.restart_pool.assert_awaited_once_with("background")
        service._get_wildlife_model.assert_not_called()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_waiting_native_fallback_does_not_reload_after_quarantine():
    from app.services.inference_health import RuntimeKey

    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        service = ClassifierService()
    service._init_bird_model = MagicMock()
    native_start = MagicMock()
    try:
        await service._worker_fallback_lock.acquire()
        task = asyncio.create_task(
            service._classify_in_process_as_last_resort(
                priority="background",
                image=Image.new("RGB", (16, 16)),
                camera_name=None,
                model_id=None,
                input_context=None,
                on_native_start=native_start,
            )
        )
        await asyncio.sleep(0)
        service._isolate_expired_native_runtime("live", RuntimeKey("openvino", "intel_gpu", "test"))
        service._worker_fallback_lock.release()
        with pytest.raises(BackgroundImageClassificationUnavailableError):
            await task
        service._init_bird_model.assert_not_called()
        native_start.assert_not_called()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_backfill_stops_after_three_classifier_failures_preserving_counts():
    service = BackfillService(classifier=MagicMock())
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(20)])
    service.process_historical_event_with_timeout = AsyncMock(return_value=("error", "background_image_lease_expired"))
    now = datetime.now(timezone.utc)
    result = await service.run_backfill(now, now)
    assert result.processed == result.errors == 3
    assert result.stopped_reason
    assert service.process_historical_event_with_timeout.await_count == 3


@pytest.mark.asyncio
async def test_successful_or_filtered_events_reset_backfill_failure_streak():
    service = BackfillService(classifier=MagicMock())
    outcomes = [("error", "background_image_worker_timed_out")] * 2 + [("skipped", "low_confidence")]
    outcomes += [("error", "background_image_lease_expired")] * 2 + [("new", None)]
    outcomes += [("error", "fetch_snapshot_failed")] * 5
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(len(outcomes))])
    service.process_historical_event_with_timeout = AsyncMock(side_effect=outcomes)
    now = datetime.now(timezone.utc)
    result = await service.run_backfill(now, now)
    assert result.processed == len(outcomes)
    assert result.stopped_reason is None
    assert result.new_detections == 1


@pytest.mark.asyncio
async def test_async_backfill_failure_keeps_counts_and_releases_maintenance(monkeypatch):
    from starlette.requests import Request
    from app.routers import backfill as router

    service = BackfillService(classifier=MagicMock())
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(20)])
    service.process_historical_event_with_timeout = AsyncMock(return_value=("error", "background_image_lease_expired"))
    coordinator = MagicMock()
    coordinator.try_acquire = AsyncMock(return_value=True)
    coordinator.release = AsyncMock()
    monkeypatch.setattr(router, "backfill_service", service)
    monkeypatch.setattr(router, "maintenance_coordinator", coordinator)
    monkeypatch.setattr(router, "_maintenance_guardrail_status", lambda: {})
    monkeypatch.setattr(router.canonical_identity_repair_service, "get_status", lambda: {})
    monkeypatch.setattr(router.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(router, "_schedule_weather_followup", MagicMock())
    monkeypatch.setattr(router, "_JOB_STORE", {})
    monkeypatch.setattr(router, "_JOB_TASKS", {})
    monkeypatch.setattr(router, "_LATEST_JOB_BY_KIND", {})
    monkeypatch.setattr(router, "_JOB_LOCK", asyncio.Lock())
    job = await router.backfill_detections_async(
        router.BackfillRequest(date_range="day"), Request({"type": "http", "headers": []})
    )
    await router._JOB_TASKS[job.id]
    assert job.status == "failed"
    assert job.processed == job.errors == 3
    assert job.total == 20
    assert job.error_reasons == {"background_image_lease_expired": 3}
    coordinator.release.assert_awaited_once()
    router._schedule_weather_followup.assert_not_called()
    assert router.broadcaster.broadcast.await_args.args[0]["type"] == "backfill_failed"


@pytest.mark.parametrize("source", ["live", "manual", "maintenance"])
@pytest.mark.parametrize(
    "reason", ["low_confidence", "below_threshold", "blocked_label", "blocked_species", "snapshot_no_usable_result"]
)
def test_snapshot_policy_rejection_does_not_open_video_circuit(monkeypatch, source, reason):
    monkeypatch.setattr(settings.classification, "video_classification_failure_threshold", 2)
    service = AutoVideoClassifierService()
    for i in range(5):
        service._record_failure(str(i), reason, source=source)
    assert service.get_circuit_status(source)["failure_count"] == 0
    assert service.get_circuit_status(source)["open"] is False


@pytest.mark.asyncio
async def test_busy_background_capacity_does_not_stop_a_healthy_backfill_early():
    """Overload is admission pressure, not evidence of a stalled runtime.

    Video snapshot fallbacks share background capacity with backfill, so a short
    burst of them made three consecutive events report overloaded and stopped
    the job on a healthy classifier.
    """
    service = BackfillService(classifier=MagicMock())
    outcomes = [("error", "background_image_overloaded")] * 5 + [("new", None)] * 3
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(len(outcomes))])
    service.process_historical_event_with_timeout = AsyncMock(side_effect=outcomes)
    now = datetime.now(timezone.utc)
    result = await service.run_backfill(now, now)
    assert result.stopped_reason is None
    assert result.processed == len(outcomes)


@pytest.mark.asyncio
async def test_overload_between_stall_failures_does_not_hide_the_stall():
    service = BackfillService(classifier=MagicMock())
    lease = ("error", "background_image_lease_expired")
    busy = ("error", "background_image_overloaded")
    outcomes = [lease, busy, busy, lease, busy, lease] + [("new", None)] * 5
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(len(outcomes))])
    service.process_historical_event_with_timeout = AsyncMock(side_effect=outcomes)
    now = datetime.now(timezone.utc)
    result = await service.run_backfill(now, now)
    assert result.stopped_reason
    assert result.processed == 6


@pytest.mark.asyncio
async def test_sustained_overload_still_stops_the_backfill():
    service = BackfillService(classifier=MagicMock())
    service.fetch_frigate_events = AsyncMock(return_value=[{"id": str(i)} for i in range(40)])
    service.process_historical_event_with_timeout = AsyncMock(return_value=("error", "background_image_overloaded"))
    now = datetime.now(timezone.utc)
    result = await service.run_backfill(now, now)
    assert result.stopped_reason and "busy" in result.stopped_reason
    assert result.processed == 10
