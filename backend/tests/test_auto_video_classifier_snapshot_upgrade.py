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
