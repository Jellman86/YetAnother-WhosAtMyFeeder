import structlog
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Deque
from dataclasses import dataclass
from collections import deque
from app.config import settings

log = structlog.get_logger()

@dataclass
class AudioDetection:
    timestamp: datetime
    species: str
    confidence: float
    sensor_id: Optional[str]
    raw_data: dict

class AudioService:
    def __init__(self, buffer_minutes: int = 5):
        # Store recent audio detections in memory for correlation
        self._buffer: Deque[AudioDetection] = deque()
        self._buffer_duration = timedelta(minutes=buffer_minutes)
        self._lock = asyncio.Lock()

    async def add_detection(self, data: dict):
        """Ingest a detection from MQTT."""
        try:
            timestamp = datetime.now()
            # Handle standard BirdNET format
            species = data.get("comName", data.get("species", "Unknown"))
            confidence = data.get("score", data.get("confidence", 0.0))
            # Capture sensor/id for camera matching
            sensor_id = data.get("id", data.get("sensor_id"))
            
            # If timestamp provided in payload, use it
            ts_raw = data.get("timestamp") or data.get("ts")
            if ts_raw:
                try:
                    timestamp = datetime.fromtimestamp(float(ts_raw))
                except Exception:
                    pass

            detection = AudioDetection(
                timestamp=timestamp,
                species=species,
                confidence=float(confidence),
                sensor_id=sensor_id,
                raw_data=data
            )

            async with self._lock:
                self._buffer.append(detection)
                self._cleanup_buffer()
            
            log.info("Audio detection received", species=species, confidence=confidence, sensor_id=sensor_id)

        except Exception as e:
            log.error("Failed to process audio detection", error=str(e))

    def _cleanup_buffer(self):
        """Remove old detections from buffer."""
        now = datetime.now()
        while self._buffer and (now - self._buffer[0].timestamp) > self._buffer_duration:
            self._buffer.popleft()

    async def find_match(self, target_time: datetime, camera_name: str = None, window_seconds: int = 15) -> Optional[AudioDetection]:
        """Find an audio detection matching the visual timestamp and camera.
        
        Args:
            target_time: Timestamp of the visual detection
            camera_name: Name of the Frigate camera (used for mapping)
            window_seconds: Match window in seconds
        """
        # Determine which sensor ID we are looking for based on camera mapping
        expected_sensor_id = None
        if camera_name and settings.frigate.camera_audio_mapping:
            expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera_name)

        async with self._lock:
            best_match = None
            highest_score = 0.0
            
            for detection in self._buffer:
                # If a mapping exists, only match if the sensor ID matches
                if expected_sensor_id and detection.sensor_id != expected_sensor_id:
                    continue

                delta = abs((detection.timestamp - target_time).total_seconds())
                if delta <= window_seconds:
                    if detection.confidence > highest_score:
                        highest_score = detection.confidence
                        best_match = detection
            
            return best_match

audio_service = AudioService()