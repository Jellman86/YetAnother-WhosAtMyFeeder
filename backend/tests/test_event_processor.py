import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.event_processor import EventProcessor

@pytest.mark.asyncio
async def test_process_mqtt_message_valid_bird():
    # Mock classifier
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Cardinal", "score": 0.95, "index": 1}])

    # Mock dependencies
    with patch("app.services.event_processor.frigate_client") as mock_frigate, \
         patch("app.services.event_processor.DetectionService") as MockDetectionService, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.audio_service") as mock_audio, \
         patch("app.services.event_processor.weather_service") as mock_weather, \
         patch("app.services.event_processor.notification_service") as mock_notif, \
         patch("app.services.taxonomy.taxonomy_service.taxonomy_service") as mock_taxonomy, \
         patch("app.services.event_processor.Image.open") as mock_image_open:

        # Mock EventProcessor with dependencies already patched
        processor = EventProcessor(classifier)

        mock_frigate.get_snapshot = AsyncMock(return_value=b"fakeimage")
        mock_frigate.set_sublabel = AsyncMock()

        mock_cache.cache_snapshot = AsyncMock()

        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal"})

        mock_det_service = MockDetectionService.return_value
        mock_det_service.filter_and_label.return_value = ({"label": "Cardinal", "score": 0.95}, None)
        mock_det_service.save_detection = AsyncMock(return_value=True)

        mock_audio.find_match = AsyncMock(return_value=None)
        mock_weather.get_current_weather = AsyncMock(return_value={})
        mock_notif.notify_detection = AsyncMock()

        payload = b'{"after": {"id": "123", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'

        await processor.process_mqtt_message(payload)

        mock_det_service.save_detection.assert_called_once()
        mock_frigate.set_sublabel.assert_called_with("123", "Cardinal")

@pytest.mark.asyncio
async def test_process_mqtt_message_ignore_non_bird():
    classifier = MagicMock()
    processor = EventProcessor(classifier)
    
    payload = b'{"after": {"id": "124", "label": "person", "camera": "cam1"}}'
    await processor.process_mqtt_message(payload)
    
    classifier.classify_async.assert_not_called()