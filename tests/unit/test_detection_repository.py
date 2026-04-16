import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

# Note: This file contains unit tests for the DetectionRepository
# These tests use mocked database connections to test business logic


class MockCursor:
    def __init__(self, *, fetchone_result=None, fetchall_result=None, rowcount=0, lastrowid=None):
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result if fetchall_result is not None else []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._fetchone_result

    async def fetchall(self):
        return self._fetchall_result

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
        self.execute_calls = []
        self.commit = AsyncMock()
        self._cursors = []

    def queue_cursor(self, cursor):
        self._cursors.append(cursor)

    def execute(self, *args, **kwargs):
        self.execute_calls.append((args, kwargs))
        if self._cursors:
            cursor = self._cursors.pop(0)
        else:
            cursor = MockCursor()
        return MockExecuteCall(cursor)


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    return MockDB()


@pytest.fixture
def sample_detection_row():
    """Sample detection row from database."""
    return (
        1,  # id
        datetime.now(),  # detection_time
        0,  # detection_index
        0.95,  # score
        "Turdus merula",  # display_name
        "bird",  # category_name
        "test-event-123",  # frigate_event
        "BirdCam",  # camera_name
        False,  # is_hidden
        0.85,  # frigate_score
        None,  # sub_label
        False,  # audio_confirmed
        None,  # audio_species
        None,  # audio_score
        15.5,  # temperature
        "sunny",  # weather_condition
        "Turdus merula",  # scientific_name
        "Eurasian Blackbird",  # common_name
        12345,  # taxa_id
        0.92,  # video_classification_score
        "Turdus merula",  # video_classification_label
        0,  # video_classification_index
        datetime.now(),  # video_classification_timestamp
        "completed",  # video_classification_status
    )


class TestDetectionRepository:
    """Unit tests for DetectionRepository."""

    @pytest.mark.asyncio
    async def test_create_detection(self, mock_db):
        """Test creating a new detection."""
        from app.repositories.detection_repository import DetectionRepository, Detection

        repo = DetectionRepository(mock_db)
        detection = Detection(
            detection_time=datetime.now(),
            detection_index=0,
            score=0.95,
            display_name="Turdus merula",
            category_name="bird",
            frigate_event="test-event-123",
            camera_name="BirdCam",
        )

        await repo.create(detection)

        assert len(mock_db.execute_calls) == 1
        assert mock_db.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_get_by_frigate_event(self, mock_db, sample_detection_row):
        """Test retrieving detection by Frigate event ID."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        mock_db.queue_cursor(MockCursor(fetchone_result=sample_detection_row))

        detection = await repo.get_by_frigate_event("test-event-123")

        assert detection is not None
        assert detection.frigate_event == "test-event-123"
        assert detection.display_name == "Turdus merula"
        assert detection.camera_name == "BirdCam"

    @pytest.mark.asyncio
    async def test_update_video_classification(self, mock_db):
        """Test updating video classification results."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)

        await repo.update_video_classification(
            frigate_event="test-event-123",
            label="Cyanistes caeruleus",
            score=0.92,
            index=42,
            status="completed"
        )

        assert len(mock_db.execute_calls) == 1
        assert mock_db.commit.await_count == 1

        call_args = mock_db.execute_calls[0][0]
        assert "UPDATE detections" in call_args[0]
        assert "video_classification" in call_args[0]

    @pytest.mark.asyncio
    async def test_update_video_status(self, mock_db):
        """Test updating video classification status."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)

        await repo.update_video_status("test-event-123", "processing")

        assert len(mock_db.execute_calls) == 1
        assert mock_db.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_delete_older_than(self, mock_db):
        """Test deleting old detections."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        mock_db.queue_cursor(MockCursor(rowcount=42))
        mock_db.queue_cursor(MockCursor(rowcount=0))

        cutoff = datetime.now() - timedelta(days=90)
        deleted_count = await repo.delete_older_than(cutoff)

        assert deleted_count == 42
        assert len(mock_db.execute_calls) == 2
        assert mock_db.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_get_species_counts(self, mock_db):
        """Test getting species counts."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        mock_db.queue_cursor(MockCursor(fetchall_result=[
            ("turdus merula", 10, "Turdus merula", "Eurasian Blackbird", "Turdus merula", 12345),
            ("cyanistes caeruleus", 5, "Cyanistes caeruleus", "Blue Tit", "Cyanistes caeruleus", 67890),
        ]))

        counts = await repo.get_species_counts()

        assert len(counts) == 2
        assert counts[0]["species"] == "Turdus merula"
        assert counts[0]["count"] == 10
        assert counts[1]["common_name"] == "Blue Tit"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
