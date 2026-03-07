from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services.auto_video_classifier_service import AutoVideoClassifierService


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

    with patch("app.services.auto_video_classifier_service.frigate_client.get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch("app.services.auto_video_classifier_service.broadcaster.broadcast", new=AsyncMock()), \
         patch("app.services.auto_video_classifier_service.high_quality_snapshot_service", create=True) as mock_hq:
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

    with patch("app.services.auto_video_classifier_service.frigate_client.get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch("app.services.auto_video_classifier_service.broadcaster.broadcast", new=AsyncMock()), \
         patch("app.services.auto_video_classifier_service.high_quality_snapshot_service", create=True) as mock_hq:
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

    with patch("app.services.auto_video_classifier_service.frigate_client.get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch("app.services.auto_video_classifier_service.frigate_client.get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")), \
         patch("app.services.auto_video_classifier_service.broadcaster.broadcast", new=AsyncMock()), \
         patch("app.services.auto_video_classifier_service.Image.open", return_value=MagicMock()):
        await service._process_event("evt-batch-fallback", "cam1", skip_delay=True, fallback_to_snapshot=True)

    service._save_results.assert_awaited_once_with("evt-batch-fallback", {"label": "Robin", "score": 0.88, "index": 1})
    service._auto_delete_if_missing.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_marks_failed_when_clip_not_retained_for_auto_mode():
    service = AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._update_status = AsyncMock()  # type: ignore[method-assign]
    service._save_results = AsyncMock()  # type: ignore[method-assign]
    service._auto_delete_if_missing = AsyncMock()  # type: ignore[method-assign]
    service._wait_for_clip = AsyncMock(return_value=(None, "clip_not_retained"))  # type: ignore[method-assign]

    with patch("app.services.auto_video_classifier_service.frigate_client.get_event_with_error", new=AsyncMock(return_value=({"has_clip": True}, None))), \
         patch("app.services.auto_video_classifier_service.broadcaster.broadcast", new=AsyncMock()):
        await service._process_event("evt-auto-no-recordings", "cam1", skip_delay=True, fallback_to_snapshot=False)

    service._save_results.assert_not_awaited()
    service._auto_delete_if_missing.assert_awaited_once_with("evt-auto-no-recordings", "clip_not_retained")
