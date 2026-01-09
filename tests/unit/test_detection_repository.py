import pytest
import aiosqlite
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Note: This file contains unit tests for the DetectionRepository
# These tests use mocked database connections to test business logic


@pytest.fixture
async def mock_db():
    """Create a mock database connection."""
    db = AsyncMock(spec=aiosqlite.Connection)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    # Mock cursor
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.fetchone = AsyncMock(return_value=None)
    db.execute.return_value = cursor

    return db


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
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)

        detection_data = {
            "detection_time": datetime.now(),
            "detection_index": 0,
            "score": 0.95,
            "display_name": "Turdus merula",
            "category_name": "bird",
            "frigate_event": "test-event-123",
            "camera_name": "BirdCam",
        }

        mock_db.execute.return_value.lastrowid = 1

        detection_id = await repo.create(**detection_data)

        assert detection_id == 1
        assert mock_db.execute.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_by_frigate_event(self, mock_db, sample_detection_row):
        """Test retrieving detection by Frigate event ID."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=sample_detection_row)
        mock_db.execute.return_value = cursor

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

        assert mock_db.execute.called
        assert mock_db.commit.called

        # Verify the UPDATE query was called with correct parameters
        call_args = mock_db.execute.call_args[0]
        assert "UPDATE detections" in call_args[0]
        assert "video_classification" in call_args[0]

    @pytest.mark.asyncio
    async def test_update_video_status(self, mock_db):
        """Test updating video classification status."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)

        await repo.update_video_status("test-event-123", "processing")

        assert mock_db.execute.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_delete_older_than(self, mock_db):
        """Test deleting old detections."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        cursor = AsyncMock()
        cursor.rowcount = 42
        mock_db.execute.return_value = cursor

        cutoff = datetime.now() - timedelta(days=90)
        deleted_count = await repo.delete_older_than(cutoff)

        assert deleted_count == 42
        assert mock_db.execute.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_species_counts(self, mock_db):
        """Test getting species counts."""
        from app.repositories.detection_repository import DetectionRepository

        repo = DetectionRepository(mock_db)
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[
            ("Turdus merula", 10),
            ("Cyanistes caeruleus", 5),
        ])
        mock_db.execute.return_value = cursor

        counts = await repo.get_species_counts()

        assert len(counts) == 2
        assert counts[0] == ("Turdus merula", 10)
        assert counts[1] == ("Cyanistes caeruleus", 5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
