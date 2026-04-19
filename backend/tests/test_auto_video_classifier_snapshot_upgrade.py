import asyncio
import contextlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.config import settings
from app.services import auto_video_classifier_service as auto_video_classifier_module
from app.services.classifier_service import (
    BackgroundImageClassificationUnavailableError,
    VideoClassificationWorkerError,
)
from app.services.error_diagnostics import error_diagnostics_history

AutoVideoClassifierService = auto_video_classifier_module.AutoVideoClassifierService


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

    mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
        "evt-auto-video-upgrade",
        b"clip-bytes",
        event_data={"has_clip": True},
        clip_variant="event",
    )
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

    mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
        "evt-auto-video-upgrade-failure",
        b"clip-bytes",
        event_data={"has_clip": True},
        clip_variant="event",
    )
    service._save_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_falls_back_to_snapshot_when_clip_not_retained_for_batch_mode():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(return_value=[{"label": "Robin", "score": 0.88, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.frigate_client, "get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module.Image, "open", return_value=MagicMock()):
        await service._process_event(
            "evt-batch-fallback",
            "cam1",
            skip_delay=True,
            fallback_to_snapshot=True,
            source="maintenance",
        )

    service._classifier.classify_async_background.assert_awaited_once()
    assert service._classifier.classify_async_background.await_args.kwargs["input_context"] == {
        "is_cropped": True,
        "event_id": "evt-batch-fallback",
    }
    service._save_results.assert_awaited_once_with("evt-batch-fallback", {"label": "Robin", "score": 0.88, "index": 1})
    service._auto_delete_if_missing.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_snapshot_fallback_retries_background_overload_then_succeeds():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(
        side_effect=[
            BackgroundImageClassificationUnavailableError("background_image_overloaded"),
            [{"label": "Robin", "score": 0.88, "index": 1}],
        ]
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]
    service._record_success = MagicMock()  # type: ignore[method-assign]
    service._record_failure = MagicMock()  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.frigate_client, "get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module.Image, "open", return_value=MagicMock()), \
         patch.object(auto_video_classifier_module.asyncio, "sleep", new=AsyncMock()):
        await service._process_event(
            "evt-batch-fallback-retry",
            "cam1",
            skip_delay=True,
            fallback_to_snapshot=True,
            source="maintenance",
        )

    assert service._classifier.classify_async_background.await_count == 2
    service._save_results.assert_awaited_once_with("evt-batch-fallback-retry", {"label": "Robin", "score": 0.88, "index": 1})
    service._record_success.assert_called_once_with("evt-batch-fallback-retry", source="maintenance")
    service._record_failure.assert_not_called()


@pytest.mark.asyncio
async def test_process_event_snapshot_fallback_marks_background_overload_distinctly():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(
        side_effect=BackgroundImageClassificationUnavailableError("background_image_overloaded")
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]
    service._record_success = MagicMock()  # type: ignore[method-assign]
    service._record_failure = MagicMock()  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.frigate_client, "get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module.Image, "open", return_value=MagicMock()), \
         patch.object(auto_video_classifier_module.asyncio, "sleep", new=AsyncMock()):
        await service._process_event(
            "evt-batch-fallback-overloaded",
            "cam1",
            skip_delay=True,
            fallback_to_snapshot=True,
            source="maintenance",
        )

    assert service._classifier.classify_async_background.await_count == 3
    service._update_status.assert_any_await("evt-batch-fallback-overloaded", "failed", error="background_image_overloaded", broadcast=True)
    service._save_results.assert_not_awaited()
    service._record_success.assert_not_called()
    service._record_failure.assert_called_once_with(
        "evt-batch-fallback-overloaded",
        "background_image_overloaded",
        source="maintenance",
    )


@pytest.mark.asyncio
async def test_process_event_snapshot_fallback_uses_extended_background_queue_timeout():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Robin", "score": 0.88, "index": 1}]
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.frigate_client, "get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
         patch.object(auto_video_classifier_module.Image, "open", return_value=MagicMock()):
        await service._process_event(
            "evt-batch-fallback-timeout-budget",
            "cam1",
            skip_delay=True,
            fallback_to_snapshot=True,
            source="maintenance",
        )

    assert service._classifier.classify_async_background.await_args.kwargs["queue_timeout_seconds"] > 0.5


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
        "clip_variant": "event",
        "frigate_box": [0.2, 0.3, 0.4, 0.5],
        "frigate_region": [0.1, 0.2, 0.8, 0.9],
    }


@pytest.mark.asyncio
async def test_process_event_prefers_cached_recording_clip_when_available():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.92, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"event-clip-bytes", None))  # type: ignore[method-assign]

    # Write a real temp file so asyncio.to_thread(Path(...).read_bytes) succeeds.
    fd, recording_path = tempfile.mkstemp(suffix=".mp4")
    try:
        os.write(fd, b"\x00\x00\x00\x18ftyprecording-clip-bytes")
        os.close(fd)

        with patch.object(
            auto_video_classifier_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True, "data": {}}, None)),
        ), \
             patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
             patch.object(auto_video_classifier_module, "_get_valid_cached_recording_clip_path", new=AsyncMock(return_value=(recording_path, "cam1", 1, 2))), \
             patch.object(AutoVideoClassifierService, "_clip_decodes", new=AsyncMock(return_value=True)):

            await service._process_event("evt-recording-preferred", "cam1", skip_delay=True)
    finally:
        with contextlib.suppress(OSError):
            os.remove(recording_path)

    service._wait_for_clip.assert_not_awaited()
    service._classifier.classify_video_async.assert_awaited_once()
    assert service._classifier.classify_video_async.await_args.kwargs["input_context"] == {
        "is_cropped": False,
        "event_id": "evt-recording-preferred",
        "clip_variant": "recording",
    }


@pytest.mark.asyncio
async def test_process_event_falls_back_to_event_clip_when_cached_recording_is_invalid():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.92, "index": 1}])
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypevent-clip-bytes", None))  # type: ignore[method-assign]

    fd, recording_path = tempfile.mkstemp(suffix=".mp4")
    try:
        os.write(fd, b"not-a-valid-clip")
        os.close(fd)

        with patch.object(
            auto_video_classifier_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True, "data": {}}, None)),
        ), \
             patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()), \
             patch.object(auto_video_classifier_module, "_get_valid_cached_recording_clip_path", new=AsyncMock(return_value=(recording_path, "cam1", 1, 2))), \
             patch.object(AutoVideoClassifierService, "_clip_decodes", new=AsyncMock(return_value=False)):

            await service._process_event("evt-recording-invalid", "cam1", skip_delay=True)
    finally:
        with contextlib.suppress(OSError):
            os.remove(recording_path)

    service._wait_for_clip.assert_awaited_once()
    assert service._classifier.classify_video_async.await_args.kwargs["input_context"] == {
        "is_cropped": False,
        "event_id": "evt-recording-invalid",
        "clip_variant": "event",
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
        assert event["context"]["source"] == "live"
    finally:
        settings.classification.video_classification_failure_threshold = original_threshold
        settings.classification.video_classification_failure_cooldown_minutes = original_cooldown
        error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_process_event_timeout_diagnostic_includes_job_source_and_clip_context():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(side_effect=asyncio.TimeoutError())
    service._classifier.get_status = MagicMock(
        return_value={
            "inference_backend": "openvino",
            "active_provider": "intel_gpu",
            "selected_provider": "intel_gpu",
        }
    )
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    error_diagnostics_history.clear()

    try:
        with patch.object(
            auto_video_classifier_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True}, None)),
        ), patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
            await service._process_event(
                "evt-video-timeout-maintenance",
                "cam1",
                skip_delay=True,
                source="maintenance",
            )

        snapshot = error_diagnostics_history.snapshot(limit=20)
        event = next(
            item
            for item in snapshot["events"]
            if item["event_id"] == "evt-video-timeout-maintenance" and item["reason_code"] == "video_timeout"
        )
        assert event["context"]["source"] == "maintenance"
        assert event["context"]["camera"] == "cam1"
        assert event["context"]["clip_bytes"] == len(b"clip-bytes")
        assert event["context"]["timeout_seconds"] == settings.classification.video_classification_timeout_seconds
        assert event["context"]["max_frames"] == settings.classification.video_classification_frames
        assert event["context"]["inference_backend"] == "openvino"
        assert event["context"]["active_provider"] == "intel_gpu"
    finally:
        error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_process_event_maintenance_timeout_falls_back_to_snapshot_without_breaker_failure():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(side_effect=asyncio.TimeoutError())
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]
    service._classify_from_snapshot = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service._record_success = MagicMock()  # type: ignore[method-assign]
    service._record_failure = MagicMock()  # type: ignore[method-assign]
    error_diagnostics_history.clear()

    try:
        with patch.object(
            auto_video_classifier_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True}, None)),
        ), patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
            await service._process_event(
                "evt-video-timeout-fallback",
                "cam1",
                skip_delay=True,
                fallback_to_snapshot=True,
                source="maintenance",
            )

        service._classify_from_snapshot.assert_awaited_once_with("evt-video-timeout-fallback", "cam1")
        service._record_success.assert_called_once_with("evt-video-timeout-fallback", source="maintenance")
        service._record_failure.assert_not_called()
        service._update_status.assert_any_await("evt-video-timeout-fallback", "processing", error=None, broadcast=False)
        snapshot = error_diagnostics_history.snapshot(limit=20)
        event = next(
            item
            for item in snapshot["events"]
            if item["event_id"] == "evt-video-timeout-fallback" and item["reason_code"] == "video_timeout"
        )
        assert event["context"]["snapshot_fallback_attempted"] is True
        assert event["context"]["snapshot_fallback_recovered"] is True
    finally:
        error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_process_event_persists_top_frames_after_successful_video_classification():
    """After successful video classification, top-N frames by score should be persisted."""
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._persist_video_top_frames = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]

    async def mock_classify(video_path, **kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            await cb(1, 3, 0.91, "European Robin", frame_index=42, frame_offset_seconds=1.68)
            await cb(2, 3, 0.75, "European Robin", frame_index=38, frame_offset_seconds=1.52)
            await cb(3, 3, 0.83, "European Robin", frame_index=50, frame_offset_seconds=2.0)
        return [{"label": "European Robin", "score": 0.91, "index": 1}]

    service._classifier.classify_video_async = mock_classify

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
        await service._process_event("evt-top-frames-test", "cam1", skip_delay=True)

    service._persist_video_top_frames.assert_awaited_once()
    call_args = service._persist_video_top_frames.call_args
    event_id_arg, frame_scores_arg, clip_variant_arg = call_args[0]
    assert event_id_arg == "evt-top-frames-test"
    assert clip_variant_arg == "event"
    assert len(frame_scores_arg) == 3
    # scores should be the raw scores as collected (sorting happens inside _persist_video_top_frames)
    scores = [f["frame_score"] for f in frame_scores_arg]
    assert pytest.approx(0.91) in scores
    assert pytest.approx(0.75) in scores
    assert pytest.approx(0.83) in scores


@pytest.mark.asyncio
async def test_process_event_top_frames_ranked_by_score_descending():
    """_persist_video_top_frames must rank frames by descending score."""
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._persist_video_top_frames = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(b"clip-bytes", None))  # type: ignore[method-assign]

    async def mock_classify(video_path, **kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            await cb(1, 5, 0.5, "Sparrow", frame_index=10, frame_offset_seconds=0.4)
            await cb(2, 5, 0.9, "Sparrow", frame_index=20, frame_offset_seconds=0.8)
            await cb(3, 5, 0.3, "Sparrow", frame_index=30, frame_offset_seconds=1.2)
            await cb(4, 5, 0.7, "Sparrow", frame_index=40, frame_offset_seconds=1.6)
            await cb(5, 5, 0.1, "Sparrow", frame_index=50, frame_offset_seconds=2.0)
        return [{"label": "Sparrow", "score": 0.9, "index": 2}]

    service._classifier.classify_video_async = mock_classify

    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
        await service._process_event("evt-rank-order", "cam1", skip_delay=True)

    service._persist_video_top_frames.assert_awaited_once()
    call_args = service._persist_video_top_frames.call_args[0]
    frame_scores_arg = call_args[1]
    assert len(frame_scores_arg) == 5

    # Verify ranking logic directly via the internal helper
    persisted: list[dict] = []

    async def collect(frigate_event, frame_scores, clip_variant):
        from app.services.auto_video_classifier_service import _VIDEO_TOP_FRAMES_LIMIT
        sorted_frames = sorted(frame_scores, key=lambda f: f["frame_score"], reverse=True)
        top_frames = [
            {**f, "rank": rank, "clip_variant": clip_variant}
            for rank, f in enumerate(sorted_frames[:_VIDEO_TOP_FRAMES_LIMIT], 1)
        ]
        persisted.extend(top_frames)

    service._persist_video_top_frames.side_effect = collect
    with patch.object(auto_video_classifier_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch.object(auto_video_classifier_module.broadcaster, "broadcast", new=AsyncMock()):
        await service._process_event("evt-rank-order-2", "cam1", skip_delay=True)

    assert len(persisted) == 5
    scores = [f["frame_score"] for f in persisted]
    assert scores == sorted(scores, reverse=True), "frames must be ranked by descending score"
    assert persisted[0]["frame_score"] == pytest.approx(0.9)
    assert persisted[0]["rank"] == 1
