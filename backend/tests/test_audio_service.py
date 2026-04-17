import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from app.services.audio.audio_service import AudioService, AudioDetection

@pytest.fixture
def audio_service():
    # Mock settings to avoid reading from config file
    with patch('app.services.audio.audio_service.settings') as mock_settings, \
         patch('app.services.taxonomy.taxonomy_service.taxonomy_service.get_names') as mock_get_names:
        mock_settings.frigate.audio_buffer_hours = 0.083  # ~5 minutes
        mock_settings.frigate.audio_correlation_window_seconds = 10
        # Mock successful taxonomy lookup
        mock_get_names.return_value = {"scientific_name": "Scientific Name", "common_name": "Common Name"}
        service = AudioService()
        yield service

@pytest.mark.asyncio
async def test_add_detection_basic(audio_service):
    data = {
        "species": "Cardinal",
        "confidence": 0.85,
        "sensor_id": "mic1"
    }
    await audio_service.add_detection(data)
    
    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.species == "Cardinal"
    assert det.confidence == 0.85
    assert det.sensor_id == "mic1"
    assert det.timestamp.tzinfo == timezone.utc

@pytest.mark.asyncio
async def test_add_detection_birdnet_go_format(audio_service):
    # Use a time that won't be cleaned up (10 seconds ago)
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=10)).isoformat().replace('+00:00', 'Z')
    data = {
        "comName": "Blue Jay",
        "score": 0.9,
        "id": "sensor_A",
        "BeginTime": ts
    }
    await audio_service.add_detection(data)
    
    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.species == "Blue Jay"
    assert det.confidence == 0.9
    assert det.sensor_id == "sensor_A"
    # Allow some precision difference in comparison
    assert abs((det.timestamp - (now - timedelta(seconds=10))).total_seconds()) < 1


@pytest.mark.asyncio
async def test_add_detection_prefers_birdnet_nm_for_mapping_key(audio_service):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=5)).isoformat().replace('+00:00', 'Z')
    data = {
        "src": "rtsp_deadbeef",
        "nm": "BirdCam",
        "CommonName": "Dunnock",
        "Confidence": 0.8,
        "BeginTime": ts,
    }
    await audio_service.add_detection(data)

    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.sensor_id == "BirdCam"


@pytest.mark.asyncio
async def test_add_detection_uses_source_display_name_when_nm_missing(audio_service):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=5)).isoformat().replace('+00:00', 'Z')
    data = {
        "Source": {"id": "rtsp_1234abcd", "displayName": "Garden Mic"},
        "CommonName": "Dunnock",
        "Confidence": 0.8,
        "BeginTime": ts,
    }
    await audio_service.add_detection(data)

    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.sensor_id == "Garden Mic"


@pytest.mark.asyncio
async def test_add_detection_falls_back_to_id_when_name_fields_missing(audio_service):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=5)).isoformat().replace('+00:00', 'Z')
    data = {
        "id": "rtsp_fallbackid",
        "CommonName": "Dunnock",
        "Confidence": 0.8,
        "BeginTime": ts,
    }
    await audio_service.add_detection(data)

    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.sensor_id == "rtsp_fallbackid"


@pytest.mark.asyncio
async def test_add_detection_falls_back_to_source_id_when_name_fields_missing(audio_service):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=5)).isoformat().replace('+00:00', 'Z')
    data = {
        "sourceId": "rtsp_livepayload",
        "CommonName": "House Sparrow",
        "Confidence": 0.91,
        "BeginTime": ts,
    }
    await audio_service.add_detection(data)

    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.sensor_id == "rtsp_livepayload"

@pytest.mark.asyncio
async def test_cleanup_buffer(audio_service):
    # Set buffer to 1 minute for test
    audio_service._buffer_duration = timedelta(minutes=1)
    
    # Old detection
    old_det = AudioDetection(
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=2),
        species="Old Bird",
        confidence=0.5,
        sensor_id="mic1",
        raw_data={}
    )
    # New detection
    new_det = AudioDetection(
        timestamp=datetime.now(timezone.utc),
        species="New Bird",
        confidence=0.9,
        sensor_id="mic1",
        raw_data={}
    )
    
    audio_service._buffer.append(old_det)
    audio_service._buffer.append(new_det)
    
    assert len(audio_service._buffer) == 2
    audio_service._cleanup_buffer()
    assert len(audio_service._buffer) == 1
    assert audio_service._buffer[0].species == "New Bird"

@pytest.mark.asyncio
async def test_find_match(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(
        timestamp=now,
        species="Robin",
        confidence=0.95,
        sensor_id="mic1",
        raw_data={}
    )
    audio_service._buffer.append(det)
    
    # Match within window
    match = await audio_service.find_match(now + timedelta(seconds=5), window_seconds=10)
    assert match is not None
    assert match.species == "Robin"
    
    # No match outside window
    match = await audio_service.find_match(now + timedelta(seconds=20), window_seconds=10)
    assert match is None

@pytest.mark.asyncio
async def test_find_match_with_camera_mapping(audio_service):
    now = datetime.now(timezone.utc)
    det1 = AudioDetection(timestamp=now, species="Bird A", confidence=0.8, sensor_id="mic1", raw_data={})
    det2 = AudioDetection(timestamp=now, species="Bird B", confidence=0.9, sensor_id="mic2", raw_data={})

    audio_service._buffer.extend([det1, det2])

    # Patch settings where audio_service accesses it
    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "mic2"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Bird B"
        assert match.sensor_id == "mic2"

@pytest.mark.asyncio
async def test_find_match_wildcard(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(timestamp=now, species="Any Bird", confidence=0.8, sensor_id="random_id", raw_data={})
    audio_service._buffer.append(det)

    # Patch settings where audio_service accesses it
    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "*"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Any Bird"


@pytest.mark.asyncio
async def test_find_match_supports_multi_source_mapping_list(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(
        timestamp=now,
        species="Garden Bird",
        confidence=0.9,
        sensor_id="Garden Mic",
        raw_data={}
    )
    audio_service._buffer.append(det)

    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "BirdCam, Garden Mic"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Garden Bird"


@pytest.mark.asyncio
async def test_correlate_species_supports_multi_source_mapping_list(audio_service):
    now = datetime.now(timezone.utc)
    audio_service._buffer.append(
        AudioDetection(
            timestamp=now,
            species="Blue Jay",
            confidence=0.91,
            sensor_id="Garden Mic",
            raw_data={},
            scientific_name=None
        )
    )
    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "BirdCam, Garden Mic"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        matched, species, score = await audio_service.correlate_species(now, "Blue Jay", camera_name="cam1")

    assert matched is True
    assert species == "Blue Jay"
    assert score == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_find_match_uses_legacy_source_id_from_raw_payload(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(
        timestamp=now,
        species="Legacy Bird",
        confidence=0.9,
        sensor_id="BirdCam",
        raw_data={"src": "rtsp_legacy_1234"}
    )
    audio_service._buffer.append(det)

    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "rtsp_legacy_1234"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Legacy Bird"


@pytest.mark.asyncio
async def test_find_match_normalizes_mapping_whitespace_and_case(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(
        timestamp=now,
        species="Case Bird",
        confidence=0.88,
        sensor_id="BirdCam",
        raw_data={}
    )
    audio_service._buffer.append(det)

    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "  birdcam  "}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Case Bird"


@pytest.mark.asyncio
async def test_add_detection_survives_taxonomy_lookup_failure(audio_service):
    data = {
        "species": "Localized Bird",
        "confidence": 0.77,
        "sensor_id": "mic1"
    }
    with patch("app.services.taxonomy.taxonomy_service.taxonomy_service.get_names", new=AsyncMock(side_effect=RuntimeError("taxonomy down"))):
        await audio_service.add_detection(data)

    assert len(audio_service._buffer) == 1
    det = audio_service._buffer[0]
    assert det.species == "Localized Bird"
    assert det.scientific_name is None


@pytest.mark.asyncio
async def test_correlate_species_falls_back_to_raw_names_when_taxonomy_lookup_fails(audio_service):
    now = datetime.now(timezone.utc)
    audio_service._buffer.append(
        AudioDetection(
            timestamp=now,
            species="Blue Jay",
            confidence=0.91,
            sensor_id="mic1",
            raw_data={},
            scientific_name=None
        )
    )
    with patch("app.services.taxonomy.taxonomy_service.taxonomy_service.get_names", new=AsyncMock(side_effect=RuntimeError("taxonomy down"))):
        matched, species, score = await audio_service.correlate_species(now, "Blue Jay")

    assert matched is True
    assert species == "Blue Jay"
    assert score == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_correlate_species_uses_legacy_source_id_mapping(audio_service):
    now = datetime.now(timezone.utc)
    audio_service._buffer.append(
        AudioDetection(
            timestamp=now,
            species="Blue Jay",
            confidence=0.91,
            sensor_id="BirdCam",
            raw_data={"src": "rtsp_legacy_5678"},
            scientific_name=None
        )
    )
    with patch("app.services.audio.audio_service.settings") as mock_settings:
        mock_settings.frigate.camera_audio_mapping = {"cam1": "rtsp_legacy_5678"}
        mock_settings.frigate.audio_correlation_window_seconds = 10
        matched, species, score = await audio_service.correlate_species(now, "Blue Jay", camera_name="cam1")

    assert matched is True
    assert species == "Blue Jay"
    assert score == pytest.approx(0.91)
