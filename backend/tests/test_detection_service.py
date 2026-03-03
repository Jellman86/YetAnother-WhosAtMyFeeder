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
         patch("app.services.detection_service.broadcaster") as mock_broadcaster, \
         patch("app.services.audio.audio_service.audio_service") as mock_audio:
        
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        
        mock_repo = MockRepo.return_value
        mock_repo.update_video_classification = AsyncMock()
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "New Sci", "common_name": "New Common", "taxa_id": 123})
        
        mock_broadcaster.broadcast = AsyncMock()
        mock_audio.correlate_species = AsyncMock(return_value=(False, None, None))
        
        yield {
            "db": mock_db,
            "repo": mock_repo,
            "taxonomy": mock_taxonomy,
            "broadcaster": mock_broadcaster,
            "audio": mock_audio
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
    
    # Mock successful audio correlation
    mock_deps["audio"].correlate_species = AsyncMock(return_value=(True, "Blue Jay", 0.9))
    
    await service.apply_video_result("event1", "Blue Jay", 0.8, 10)
    
    # Verify audio correlation was called with the scientific name
    mock_deps["audio"].correlate_species.assert_called_once()
    
    # Verify the update query set audio_confirmed to 1
    update_call = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    args = update_call[0].args
    params = args[1]
    
    # Find the index of audio_confirmed in the query
    assert params[7] == 1 # audio_confirmed should be True (1)


@pytest.mark.asyncio
async def test_apply_video_result_does_not_override_known_species_with_lower_score(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.95
    existing.display_name = "Great Tit"
    existing.category_name = "Great Tit"
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    await service.apply_video_result("event1", "Blue Jay", 0.40, 2)

    mock_deps["repo"].update_video_classification.assert_called_once()
    # No primary UPDATE should run when lower-confidence video result does not beat a known species
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_does_not_override_when_below_threshold(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.55
    existing.display_name = "Great Tit"
    existing.category_name = "Parus major"
    existing.sub_label = None
    existing.frigate_score = 0.8
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    # Current score is lower, but still below the primary threshold (0.7 by default)
    await service.apply_video_result("event1", "Blue Jay", 0.60, 2)

    mock_deps["repo"].update_video_classification.assert_called_once()
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()


@pytest.mark.asyncio
async def test_apply_video_result_respects_frigate_sublabel_disagreement_guard(mock_deps):
    classifier = MagicMock()
    service = DetectionService(classifier)

    existing = MagicMock(spec=Detection)
    existing.score = 0.60
    existing.display_name = "Woodpigeon"
    existing.category_name = "Columba palumbus"
    existing.sub_label = "Columba palumbus"
    existing.frigate_score = 0.82
    existing.detection_time = datetime.now()
    existing.camera_name = "cam1"
    existing.is_hidden = False
    existing.audio_species = None
    existing.audio_score = None
    existing.audio_confirmed = False
    existing.video_classification_label = None
    existing.video_classification_score = None
    existing.video_classification_status = "pending"

    mock_deps["repo"].get_by_frigate_event = AsyncMock(return_value=existing)

    # Video disagrees with Frigate sublabel and is not confident enough to force override.
    await service.apply_video_result("event1", "Aegithalos caudatus", 0.80, 3688)

    mock_deps["repo"].update_video_classification.assert_called_once()
    primary_updates = [call for call in mock_deps["db"].execute.call_args_list if "UPDATE detections" in call.args[0]]
    assert primary_updates == []
    mock_deps["audio"].correlate_species.assert_not_called()
