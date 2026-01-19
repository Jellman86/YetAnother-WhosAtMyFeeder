import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.services.event_processor import EventProcessor

@pytest.fixture
def mock_dependencies():
    with patch("app.services.event_processor.frigate_client") as mock_frigate, \
         patch("app.services.event_processor.DetectionService") as MockDetectionService, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.audio_service") as mock_audio, \
         patch("app.services.event_processor.weather_service") as mock_weather, \
         patch("app.services.event_processor.notification_service") as mock_notif, \
         patch("app.services.taxonomy.taxonomy_service.taxonomy_service") as mock_taxonomy, \
         patch("app.services.event_processor.Image.open") as mock_image_open:

        mock_frigate.get_snapshot = AsyncMock(return_value=b"fakeimage")
        mock_frigate.set_sublabel = AsyncMock()
        mock_cache.cache_snapshot = AsyncMock()
        mock_weather.get_current_weather = AsyncMock(return_value={"temperature": 20, "condition_text": "Sunny"})
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "Scientific Name", "common_name": "Common Name"})

        # CRITICAL: notification_service.notify_detection must be AsyncMock
        mock_notif.notify_detection = AsyncMock()

        mock_det_service = MockDetectionService.return_value
        mock_det_service.save_detection = AsyncMock(return_value=(True, True))

        yield {
            "frigate": mock_frigate,
            "det_service": mock_det_service,
            "audio": mock_audio,
            "weather": mock_weather,
            "notif": mock_notif,
            "taxonomy": mock_taxonomy
        }

@pytest.mark.asyncio
async def test_audio_confirmation(mock_dependencies):
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.9, "index": 1}])
    
    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Cardinal", "score": 0.9}, {})
    
    # Mock audio match with same species
    audio_match = MagicMock()
    audio_match.species = "Cardinal"
    audio_match.confidence = 0.8
    mock_dependencies["audio"].find_match = AsyncMock(return_value=audio_match)
    
    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event1", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'
    
    await processor.process_mqtt_message(payload)
    
    # Verify audio_confirmed was True
    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["audio_confirmed"] is True
    assert kwargs["audio_species"] == "Cardinal"

@pytest.mark.asyncio
async def test_audio_enhancement_unknown_bird(mock_dependencies):
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Background", "score": 0.5, "index": 0}])
    
    # filter_and_label normally converts Background to Unknown Bird
    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Unknown Bird", "score": 0.5}, {})
    
    # Mock audio match with high confidence
    audio_match = MagicMock()
    audio_match.species = "Blue Jay"
    audio_match.confidence = 0.9
    mock_dependencies["audio"].find_match = AsyncMock(return_value=audio_match)
    
    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event2", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'
    
    await processor.process_mqtt_message(payload)
    
    # Verify label was upgraded to Blue Jay and audio_confirmed is True
    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["classification"]["label"] == "Blue Jay"
    assert kwargs["audio_confirmed"] is True

@pytest.mark.asyncio
async def test_weather_context(mock_dependencies):
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.9, "index": 1}])
    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Cardinal", "score": 0.9}, {})
    mock_dependencies["audio"].find_match = AsyncMock(return_value=None)
    
    # Weather is mocked in mock_dependencies fixture to return 20, "Sunny"
    
    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event3", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'
    
    await processor.process_mqtt_message(payload)
    
    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["temperature"] == 20
    assert kwargs["weather_condition"] == "Sunny"
