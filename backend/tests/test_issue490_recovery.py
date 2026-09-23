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
