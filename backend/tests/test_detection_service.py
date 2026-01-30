import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.services.detection_service import DetectionService
from app.repositories.detection_repository import Detection

@pytest.fixture
def mock_deps():
    with patch("app.services.detection_service.get_db") as mock_get_db, \
         patch("app.services.detection_service.DetectionRepository") as MockRepo, \
         patch("app.services.detection_service.taxonomy_service") as mock_taxonomy, \
         patch("app.services.detection_service.broadcaster") as mock_broadcaster:
        
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        
        mock_repo = MockRepo.return_value
        mock_repo.update_video_classification = AsyncMock()
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "New Sci", "common_name": "New Common", "taxa_id": 123})
        
        yield {
            "db": mock_db,
            "repo": mock_repo,
            "taxonomy": mock_taxonomy,
            "broadcaster": mock_broadcaster
        }

@pytest.mark.asyncio
async def test_apply_video_result_overrides_lower_score(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)
    
    # Mock existing detection with lower score
    existing = MagicMock(spec=Detection)
    existing.score = 0.5
    existing.display_name = "Old Name"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = "New Species"
    existing.video_classification_score = 0.9
    existing.video_classification_status = "completed"
    
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    
    await service.apply_video_result("event1", "New Species", 0.9, 5)
    
    # Verify update_video_classification was called
    mock_deps["repo"].update_video_classification.assert_called_once()
    
    # Verify primary fields were updated (using execute on db)
    assert mock_deps["db"].execute.called
    # One of the calls should be the primary UPDATE
    update_call = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call[0][0]]
    assert len(update_call) > 0

@pytest.mark.asyncio
async def test_apply_video_result_re_evaluates_audio(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)
    
    # Mock existing detection with audio that didn't match old ID
    # But WILL match the new video ID
    existing = MagicMock(spec=Detection)
    existing.score = 0.5
    existing.display_name = "Unknown Bird"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = "Blue Jay"
    existing.audio_score = 0.9
    existing.audio_confirmed = False
    existing.video_classification_label = "Blue Jay"
    existing.video_classification_score = 0.8
    existing.video_classification_status = "completed"
    
    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)
    
    await service.apply_video_result("event1", "Blue Jay", 0.8, 10)
    
    # Verify the update query set audio_confirmed to 1
    update_call = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call[0][0]]
    args = update_call[0][0]
    params = update_call[0][1]
    
    # Find the index of audio_confirmed in the query
    # SET display_name = ?, category_name = ?, score = ?, detection_index = ?, scientific_name = ?, common_name = ?, taxa_id = ?, audio_confirmed = ?
    assert params[7] == 1 # audio_confirmed should be True (1)
