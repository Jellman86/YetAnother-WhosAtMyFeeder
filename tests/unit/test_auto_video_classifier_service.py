import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class MockCursor:
    def __init__(self, *, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.rowcount = 0

    async def fetchone(self):
        return self._fetchone_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class MockExecuteCall:
    def __init__(self, cursor):
        self._cursor = cursor

    def __await__(self):
        async def _inner():
            return self._cursor

        return _inner().__await__()

    async def __aenter__(self):
        return self._cursor

    async def __aexit__(self, exc_type, exc, tb):
        return False


class MockDB:
    def __init__(self):
        self.commit = AsyncMock()
        self.execute_calls = []

    def execute(self, *args, **kwargs):
        self.execute_calls.append((args, kwargs))
        return MockExecuteCall(MockCursor(fetchone_result=None))


@pytest.fixture
def mock_classifier():
    """Mock classifier service."""
    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[
        {"label": "Turdus merula", "score": 0.95, "index": 0},
        {"label": "Cyanistes caeruleus", "score": 0.03, "index": 1},
    ])
    classifier.get_admission_status.return_value = {"live": {"running": 0, "queued": 0}}
    return classifier


@pytest.fixture
def mock_frigate_client():
    """Mock Frigate client."""
    client = MagicMock()
    client.get_event_with_error = AsyncMock(return_value=({"data": {}}, None))
    client.get_clip_with_error = AsyncMock(return_value=(b'\x00\x00\x00\x18ftyp' + b'\x00' * 1000, None))
    return client


@pytest.fixture
def mock_db():
    """Mock database."""
    return MockDB()


@pytest.fixture
def mock_broadcaster():
    """Mock broadcaster."""
    broadcaster = MagicMock()
    broadcaster.broadcast = AsyncMock()
    return broadcaster


async def _wait_until(predicate, timeout=1.5):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Timed out waiting for expected condition")


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
             patch('app.services.auto_video_classifier_service.get_classifier', return_value=mock_classifier), \
             patch.object(AutoVideoClassifierService, '_clip_decodes', new=AsyncMock(return_value=True)):

            mock_settings.classification.auto_video_classification = True
            mock_settings.classification.video_classification_delay = 0  # No delay for testing
            mock_settings.classification.video_classification_max_retries = 1
            mock_settings.classification.video_classification_retry_interval = 0
            mock_settings.classification.video_classification_timeout_seconds = 5
            mock_settings.classification.video_classification_frames = 15
            mock_settings.classification.video_classification_stale_minutes = 15

            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()
            await service.start()
            try:
                await service.trigger_classification("test-event-123", "BirdCam")
                await _wait_until(lambda: mock_classifier.classify_video_async.called)

                assert mock_broadcaster.broadcast.called
                assert mock_frigate_client.get_event_with_error.called
                assert mock_frigate_client.get_clip_with_error.called
                assert mock_db.commit.await_count >= 1
            finally:
                await service.stop()

    @pytest.mark.asyncio
    async def test_clip_not_available(self, mock_classifier, mock_db, mock_broadcaster):
        """Test handling when Frigate clip is not available."""
        from app.services.auto_video_classifier_service import AutoVideoClassifierService

        # Mock Frigate client that returns no clip bytes.
        mock_frigate = MagicMock()
        mock_frigate.get_event_with_error = AsyncMock(return_value=({"data": {}}, None))
        mock_frigate.get_clip_with_error = AsyncMock(return_value=(None, "clip_not_found"))

        with patch('app.services.auto_video_classifier_service.settings') as mock_settings, \
             patch('app.services.auto_video_classifier_service.frigate_client', mock_frigate), \
             patch('app.services.auto_video_classifier_service.get_db') as mock_get_db, \
             patch('app.services.auto_video_classifier_service.broadcaster', mock_broadcaster), \
             patch('app.services.auto_video_classifier_service.get_classifier', return_value=mock_classifier):

            mock_settings.classification.auto_video_classification = True
            mock_settings.classification.video_classification_delay = 0
            mock_settings.classification.video_classification_max_retries = 1
            mock_settings.classification.video_classification_retry_interval = 0
            mock_settings.classification.video_classification_timeout_seconds = 5
            mock_settings.classification.video_classification_frames = 15
            mock_settings.classification.video_classification_stale_minutes = 15

            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()
            await service.start()
            try:
                await service.trigger_classification("test-event-456", "BirdCam")
                await _wait_until(lambda: mock_frigate.get_clip_with_error.called)
                await _wait_until(
                    lambda: "test-event-456" not in service._active_tasks and "test-event-456" not in service._pending_ids
                )

                assert mock_broadcaster.broadcast.called
            finally:
                await service.stop()

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
            mock_settings.classification.video_classification_timeout_seconds = 5
            mock_settings.classification.video_classification_frames = 15
            mock_settings.classification.video_classification_stale_minutes = 15

            mock_get_db.return_value.__aenter__.return_value = mock_db

            service = AutoVideoClassifierService()
            await service.start()
            try:
                await service.trigger_classification("test-cleanup", "BirdCam")
                await _wait_until(
                    lambda: "test-cleanup" in service._pending_ids or "test-cleanup" in service._active_tasks
                )
                await _wait_until(
                    lambda: "test-cleanup" not in service._active_tasks and "test-cleanup" not in service._pending_ids
                )
            finally:
                await service.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
