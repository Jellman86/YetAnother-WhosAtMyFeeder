import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from app.services.audio.audio_service import AudioService, AudioDetection
from app.config import settings

@pytest.fixture
def audio_service():
    # Mock settings to avoid reading from config file
    with patch('app.services.audio.audio_service.settings') as mock_settings:
        mock_settings.frigate.audio_buffer_hours = 0.083  # ~5 minutes
        mock_settings.frigate.audio_correlation_window_seconds = 10
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
    
    with patch("app.config.settings.frigate.camera_audio_mapping", {"cam1": "mic2"}):
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Bird B"
        assert match.sensor_id == "mic2"

@pytest.mark.asyncio
async def test_find_match_wildcard(audio_service):
    now = datetime.now(timezone.utc)
    det = AudioDetection(timestamp=now, species="Any Bird", confidence=0.8, sensor_id="random_id", raw_data={})
    audio_service._buffer.append(det)
    
    with patch("app.config.settings.frigate.camera_audio_mapping", {"cam1": "*"}):
        match = await audio_service.find_match(now, camera_name="cam1")
        assert match is not None
        assert match.species == "Any Bird"
