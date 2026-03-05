import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.event_processor import EventProcessor

@pytest.fixture
def mock_dependencies():
    with patch("app.services.event_processor.frigate_client") as mock_frigate, \
         patch("app.services.event_processor.DetectionService") as MockDetectionService, \
         patch("app.services.event_processor.media_cache") as mock_cache, \
         patch("app.services.event_processor.audio_service") as mock_audio, \
         patch("app.services.event_processor.weather_service") as mock_weather, \
         patch("app.services.event_processor.notification_service") as mock_notif, \
         patch("app.services.event_processor.taxonomy_service") as mock_taxonomy, \
         patch("app.services.event_processor.Image.open"):

        mock_frigate.get_snapshot = AsyncMock(return_value=b"fakeimage")
        mock_frigate.set_sublabel = AsyncMock()
        mock_cache.cache_snapshot = AsyncMock()
        mock_weather.get_current_weather = AsyncMock(return_value={"temperature": 20, "condition_text": "Sunny"})
        mock_taxonomy.get_names = AsyncMock(return_value={"scientific_name": "Scientific Name", "common_name": "Common Name"})

        # CRITICAL: notification_service.notify_detection must be AsyncMock
        mock_notif.notify_detection = AsyncMock(return_value=False)

        mock_det_service = MockDetectionService.return_value
        mock_det_service.save_detection = AsyncMock(return_value=(True, True))
        mock_det_service.get_detection_by_frigate_event = AsyncMock(return_value=MagicMock(notified_at=None))

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
async def test_audio_enhancement_no_upgrade(mock_dependencies):
    """Test that audio no longer upgrades visual 'Unknown Bird' detections."""
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
    
    # Verify label remains Unknown Bird and audio_confirmed is False
    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["classification"]["label"] == "Unknown Bird"
    assert kwargs["audio_confirmed"] is False
    assert kwargs["audio_species"] == "Blue Jay"

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

@pytest.mark.asyncio
async def test_audio_mismatch_recorded_as_heard(mock_dependencies):
    """Test that mismatched audio is still recorded as metadata but not confirmed."""
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Blue Tit", "score": 0.9, "index": 1}])
    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Blue Tit", "score": 0.9}, {})

    # Audio match is a different species with high confidence
    audio_match = MagicMock()
    audio_match.species = "European Robin"
    audio_match.confidence = 0.95
    mock_dependencies["audio"].find_match = AsyncMock(return_value=audio_match)

    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event4", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'

    await processor.process_mqtt_message(payload)

    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["audio_confirmed"] is False
    assert kwargs["audio_species"] == "European Robin"
    assert kwargs["audio_score"] == 0.95


@pytest.mark.asyncio
async def test_audio_confirmation_accepts_localized_audio_name_via_scientific_name(mock_dependencies):
    """Localized audio common names should confirm when scientific names match visual label taxonomy."""
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Eurasian Blue Tit", "score": 0.89, "index": 1}])

    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Eurasian Blue Tit", "score": 0.89}, {})

    mock_dependencies["taxonomy"].get_names = AsyncMock(
        return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Eurasian Blue Tit"}
    )

    audio_match = MagicMock()
    audio_match.species = "Лазоревка"
    audio_match.scientific_name = "Cyanistes caeruleus"
    audio_match.confidence = 0.97
    mock_dependencies["audio"].find_match = AsyncMock(return_value=audio_match)

    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event5", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'

    await processor.process_mqtt_message(payload)

    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["audio_confirmed"] is True
    assert kwargs["audio_species"] == "Лазоревка"
    assert kwargs["audio_score"] == 0.97


@pytest.mark.asyncio
async def test_audio_confirmation_accepts_audio_name_variants_via_taxonomy(mock_dependencies):
    """Audio name variants should confirm when audio taxonomy resolves to same species."""
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Common Wood-Pigeon", "score": 0.83, "index": 1}])

    mock_dependencies["det_service"].filter_and_label.return_value = ({"label": "Common Wood-Pigeon", "score": 0.83}, {})

    async def taxonomy_lookup(name: str):
        normalized = (name or "").strip().lower()
        if normalized in {"common wood-pigeon", "woodpigeon"}:
            return {"scientific_name": "Columba palumbus", "common_name": "Common Wood-Pigeon"}
        return {"scientific_name": "Scientific Name", "common_name": "Common Name"}

    audio_match = MagicMock()
    audio_match.species = "Woodpigeon"
    audio_match.scientific_name = None
    audio_match.confidence = 0.94
    mock_dependencies["audio"].find_match = AsyncMock(return_value=audio_match)

    processor = EventProcessor(classifier)
    payload = b'{"after": {"id": "event6", "label": "bird", "camera": "cam1", "start_time": 1700000000}}'

    with patch("app.services.event_processor.taxonomy_service.get_names", new=AsyncMock(side_effect=taxonomy_lookup)):
        await processor.process_mqtt_message(payload)

    args, kwargs = mock_dependencies["det_service"].save_detection.call_args
    assert kwargs["audio_confirmed"] is True
    assert kwargs["audio_species"] == "Woodpigeon"
    assert kwargs["audio_score"] == 0.94
