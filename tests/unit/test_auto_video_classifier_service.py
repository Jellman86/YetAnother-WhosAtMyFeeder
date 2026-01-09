import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_classifier():
    """Mock classifier service."""
    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[
        {"label": "Turdus merula", "score": 0.95, "index": 0},
        {"label": "Cyanistes caeruleus", "score": 0.03, "index": 1},
    ])
    return classifier


@pytest.fixture
def mock_frigate_client():
    """Mock Frigate client."""
    client = MagicMock()
    # Mock MP4 header bytes
    client.get_clip = AsyncMock(return_value=b'\x00\x00\x00\x18ftyp' + b'\x00' * 1000)
    return client


@pytest.fixture
def mock_db():
    """Mock database."""
    return AsyncMock()


@pytest.fixture
def mock_broadcaster():
    """Mock broadcaster."""
    broadcaster = MagicMock()
    broadcaster.broadcast = AsyncMock()
    return broadcaster


class TestAutoVideoClassifierService:
    """Unit tests for AutoVideoClassifierService."""

    @pytest.mark.asyncio
    async def test_trigger_classification_disabled(self):
        """Test that classification doesn't start when disabled."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings:
            mock_settings.classification.auto_video_classification = False

            service = AutoVideoClassifierService()
            await service.trigger_classification("test-event", "BirdCam")

            # Should not start any tasks
            assert len(service._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_trigger_classification_already_in_progress(self):
        """Test that duplicate classification requests are ignored."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings:
            mock_settings.classification.auto_video_classification = True

            service = AutoVideoClassifierService()

            # Add a fake task
            fake_task = asyncio.create_task(asyncio.sleep(0.1))
            service._active_tasks["test-event"] = fake_task

            # Try to trigger again
            await service.trigger_classification("test-event", "BirdCam")

            # Should still have only one task
            assert len(service._active_tasks) == 1
            assert service._active_tasks["test-event"] == fake_task

            # Cleanup
            fake_task.cancel()
            try:
                await fake_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_successful_classification(self, mock_classifier, mock_frigate_client,
                                            mock_db, mock_broadcaster):
        """Test successful video classification flow."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings, \
             patch('app.services.auto_video_classifier_service.frigate_client', mock_frigate_client), \
             patch('app.services.auto_video_classifier_service.get_db') as mock_get_db, \
             patch('app.services.auto_video_classifier_service.broadcaster', mock_broadcaster), \
             patch('app.services.auto_video_classifier_service.get_classifier', return_value=mock_classifier):

            mock_settings.classification.auto_video_classification = True
            mock_settings.classification.video_classification_delay = 0  # No delay for testing
            mock_settings.classification.video_classification_max_retries = 1
            mock_settings.classification.video_classification_retry_interval = 0

            # Mock get_db context manager
            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()

            # Trigger classification
            await service.trigger_classification("test-event-123", "BirdCam")

            # Wait for task to complete
            if "test-event-123" in service._active_tasks:
                await asyncio.sleep(0.2)  # Give it time to process

            # Verify broadcaster was called
            assert mock_broadcaster.broadcast.called

            # Verify classifier was used
            assert mock_classifier.classify_video_async.called

    @pytest.mark.asyncio
    async def test_clip_not_available(self, mock_classifier, mock_db, mock_broadcaster):
        """Test handling when Frigate clip is not available."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        # Mock frigate client that returns None (clip not available)
        mock_frigate = MagicMock()
        mock_frigate.get_clip = AsyncMock(return_value=None)

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings, \
             patch('app.services.auto_video_classifier_service.frigate_client', mock_frigate), \
             patch('app.services.auto_video_classifier_service.get_db') as mock_get_db, \
             patch('app.services.auto_video_classifier_service.broadcaster', mock_broadcaster), \
             patch('app.services.auto_video_classifier_service.get_classifier', return_value=mock_classifier):

            mock_settings.classification.auto_video_classification = True
            mock_settings.classification.video_classification_delay = 0
            mock_settings.classification.video_classification_max_retries = 1
            mock_settings.classification.video_classification_retry_interval = 0

            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()
            await service.trigger_classification("test-event-456", "BirdCam")

            # Wait for task to complete
            await asyncio.sleep(0.2)

            # Verify status was updated to 'failed'
            # (The actual call is to repo.update_video_status which is mocked)
            assert mock_broadcaster.broadcast.called

    @pytest.mark.asyncio
    async def test_task_cleanup_on_completion(self, mock_classifier, mock_frigate_client,
                                              mock_db, mock_broadcaster):
        """Test that completed tasks are removed from _active_tasks."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings, \
             patch('app.services.auto_video_classifier_service.frigate_client', mock_frigate_client), \
             patch('app.services.auto_video_classifier_service.get_db') as mock_get_db, \
             patch('app.services.auto_video_classifier_service.broadcaster', mock_broadcaster), \
             patch('app.services.auto_video_classifier_service.get_classifier', return_value=mock_classifier):

            mock_settings.classification.auto_video_classification = True
            mock_settings.classification.video_classification_delay = 0
            mock_settings.classification.video_classification_max_retries = 1
            mock_settings.classification.video_classification_retry_interval = 0

            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()

            # Trigger classification
            await service.trigger_classification("test-cleanup", "BirdCam")

            # Task should be in active_tasks
            assert "test-cleanup" in service._active_tasks

            # Wait for completion
            await asyncio.sleep(0.3)

            # Task should be removed from active_tasks
            assert "test-cleanup" not in service._active_tasks


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
