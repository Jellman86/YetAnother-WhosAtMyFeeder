from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services import auto_video_classifier_service as auto_video_classifier_module

AutoVideoClassifierService = auto_video_classifier_module.AutoVideoClassifierService
from app.services.classifier_service import VideoClassificationWorkerError
from app.services.error_diagnostics import error_diagnostics_history


@pytest.fixture(autouse=True)
def reset_settings():
    original_hq_enabled = settings.media_cache.high_quality_event_snapshots
    yield
    settings.media_cache.high_quality_event_snapshots = original_hq_enabled


@pytest.mark.asyncio
async def test_process_event_triggers_snapshot_upgrade_when_clip_valid():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.92, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    settings.media_cache.high_quality_event_snapshots = True

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module, "high_quality_snapshot_service") as mock_hq:
        mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")

        await service._process_event("evt-auto-video-upgrade", "cam1", skip_delay=True)

    mock_hq.replace_from_clip_bytes.assert_awaited_once_with("evt-auto-video-upgrade", b"clip-bytes")
    service._save_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_still_classifies_when_snapshot_upgrade_fails():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.92, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    settings.media_cache.high_quality_event_snapshots = True

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module, "high_quality_snapshot_service") as mock_hq:
        mock_hq.replace_from_clip_bytes = AsyncMock(return_value="frame_extract_failed")

        await service._process_event("evt-auto-video-upgrade-failure", "cam1", skip_delay=True)

    mock_hq.replace_from_clip_bytes.assert_awaited_once_with("evt-auto-video-upgrade-failure", b"clip-bytes")
    service._save_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_falls_back_to_snapshot_when_clip_not_retained_for_batch_mode():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.88, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
        patch.object(auto_video_classifier_module.frigate_client, "get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module.Image, "open", return_value=MagicMock()):
        await service._process_event("evt-batch-fallback", "cam1", skip_delay=True, fallback_to_snapshot=True)

    service._classifier.classify_async.assert_awaited_once()
    assert service._classifier.classify_async.await_args.kwargs["input_context"] == {
        "is_cropped": True,
        "event_id": "evt-batch-fallback",
    }
    service._save_results.assert_awaited_once_with("evt-batch-fallback", {"label": "Robin", "score": 0.88, "index": 1})
    service._auto_delete_if_missing.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_passes_event_id_into_video_classification_context():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.92, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]

    with patch.object(
        auto_video_classifier_module.frigate_client,
        "get_event_with_error",
        new=AsyncMock(
            return_value=(
                {
                    "has_clip": True,
                    "data": {
                        "box": [0.2, 0.3, 0.4, 0.5],
                        "region": [0.1, 0.2, 0.8, 0.9],
                    },
                },
                None,
            )
        ),
    ), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
        await service._process_event("evt-batch-video-context", "cam1", skip_delay=True)

    service._classifier.classify_video_async.assert_awaited_once()
    assert service._classifier.classify_video_async.await_args.kwargs["input_context"] == {
        "is_cropped": False,
        "event_id": "evt-batch-video-context",
        "frigate_box": [0.2, 0.3, 0.4, 0.5],
        "frigate_region": [0.1, 0.2, 0.8, 0.9],
    }


@pytest.mark.asyncio
async def test_process_event_marks_failed_when_clip_not_retained_for_auto_mode():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
        await service._process_event("evt-auto-no-recordings", "cam1", skip_delay=True, fallback_to_snapshot=False)

    service._save_results.assert_not_awaited()
    service._auto_delete_if_missing.assert_awaited_once_with("evt-auto-no-recordings", "clip_not_retained")


@pytest.mark.asyncio
async def test_process_event_records_backend_diagnostic_for_worker_failure():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(
        side_effect=VideoClassificationWorkerError("video_worker_deadline_exceeded")
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    error_diagnostics_history.clear()

    try:
        with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
             patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
            await service._process_event("evt-video-worker-deadline", "cam1", skip_delay=True)

        snapshot = error_diagnostics_history.snapshot(limit=20)
        event = next(item for item in snapshot["events"] if item["event_id"] == "evt-video-worker-deadline")
        assert event["component"] == "auto_video_classifier"
        assert event["reason_code"] == "video_worker_deadline_exceeded"
        assert event["worker_pool"] == "video"
    finally:
        error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_process_event_diagnostic_includes_inference_provider_context():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(
        side_effect=VideoClassificationWorkerError("video_worker_deadline_exceeded")
    )
    service._classifier.get_status = MagicMock(
        return_value={
            "inference_backend": "openvino",
            "active_provider": "intel_gpu",
            "selected_provider": "intel_gpu",
            "last_runtime_recovery": {
                "status": "recovered",
                "failed_provider": "GPU",
                "recovered_provider": "intel_cpu",
            },
        }
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    error_diagnostics_history.clear()

    try:
        with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
             patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
            await service._process_event("evt-video-provider-context", "cam1", skip_delay=True)

        snapshot = error_diagnostics_history.snapshot(limit=20)
        event = next(item for item in snapshot["events"] if item["event_id"] == "evt-video-provider-context")
        assert event["context"]["inference_backend"] == "openvino"
        assert event["context"]["active_provider"] == "intel_gpu"
        assert event["context"]["selected_provider"] == "intel_gpu"
        assert event["context"]["last_runtime_recovery"]["recovered_provider"] == "intel_cpu"
    finally:
        error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_record_failure_records_backend_diagnostic_when_video_circuit_opens():
    service = AutoVideoClassifierService()
    original_threshold = settings.classification.video_classification_failure_threshold
    original_cooldown = settings.classification.video_classification_failure_cooldown_minutes
    settings.classification.video_classification_failure_threshold = 2
    settings.classification.video_classification_failure_cooldown_minutes = 15
    error_diagnostics_history.clear()

    try:
        service._record_failure("evt-video-circuit-a", "video_no_results")
        service._record_failure("evt-video-circuit-b", "video_no_results")

        snapshot = error_diagnostics_history.snapshot(limit=20)
        event = next(item for item in snapshot["events"] if item["reason_code"] == "video_circuit_opened")
        assert event["component"] == "auto_video_classifier"
        assert event["worker_pool"] == "video"
        assert event["context"]["failure_count"] == 2
    finally:
        settings.classification.video_classification_failure_threshold = original_threshold
        settings.classification.video_classification_failure_cooldown_minutes = original_cooldown
        error_diagnostics_history.clear()
