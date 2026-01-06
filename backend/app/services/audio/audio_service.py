import structlog
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Deque
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
            # Handle standard BirdNET format (camelCase) and BirdNET-Go format (PascalCase)
            species = data.get("comName", data.get("species"))
            if not species:
                species = data.get("CommonName", data.get("ScientificName", "Unknown"))
                
            confidence = data.get("score", data.get("confidence"))
            if confidence is None:
                confidence = data.get("Confidence", 0.0)
                
            # Capture sensor/id for camera matching
            sensor_id = data.get("id", data.get("sensor_id"))
            if not sensor_id and "Source" in data:
                sensor_id = data.get("Source", {}).get("id")
            
            # If timestamp provided in payload, use it
            ts_raw = data.get("timestamp") or data.get("ts")
            if ts_raw:
                try:
                    timestamp = datetime.fromtimestamp(float(ts_raw))
                except Exception:
                    pass
            else:
                # Try ISO format from BirdNET-Go (BeginTime)
                iso_ts = data.get("BeginTime") or data.get("EndTime")
                if iso_ts:
                    try:
                        # Handle potential trailing 'Z' or extra precision
                        timestamp = datetime.fromisoformat(iso_ts.replace('Z', '+00:00'))
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
        # Ensure we are comparing offset-naive or offset-aware correctly
        # Most of our timestamps are naive (local time)
        while self._buffer:
            ts = self._buffer[0].timestamp
            # If the timestamp is offset-aware (from ISO), make it naive for comparison
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
                
            if (now - ts) > self._buffer_duration:
                self._buffer.popleft()
            else:
                break

    async def find_match(self, target_time: datetime, camera_name: str = None, window_seconds: int = 15) -> Optional[AudioDetection]:
        """Find an audio detection matching the visual timestamp and camera.
        
        Args:
            target_time: Timestamp of the visual detection
            camera_name: Name of the Frigate camera (used for mapping)
            window_seconds: Match window in seconds
        """
        async with self._lock:
            self._cleanup_buffer() # Clean before matching
            
            # Determine which sensor ID we are looking for based on camera mapping
            expected_sensor_id = None
            if camera_name and settings.frigate.camera_audio_mapping:
                expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera_name)

            best_match = None
            highest_score = 0.0
            
            for detection in self._buffer:
                # If a mapping exists, only match if the sensor ID matches
                if expected_sensor_id and detection.sensor_id != expected_sensor_id:
                    continue

                # Ensure naive comparison
                det_ts = detection.timestamp.replace(tzinfo=None) if detection.timestamp.tzinfo else detection.timestamp
                target_ts = target_time.replace(tzinfo=None) if target_time.tzinfo else target_time

                delta = abs((det_ts - target_ts).total_seconds())
                if delta <= window_seconds:
                    if detection.confidence > highest_score:
                        highest_score = detection.confidence
                        best_match = detection
            
            return best_match

    async def get_recent_detections(self, limit: int = 10) -> list[dict]:
        """Get the most recent audio detections from the buffer."""
        async with self._lock:
            self._cleanup_buffer() # Clean before returning to UI
            # Sort by timestamp descending
            sorted_detections = sorted(self._buffer, key=lambda x: x.timestamp, reverse=True)
            return [
                {
                    "timestamp": d.timestamp.isoformat(),
                    "species": d.species,
                    "confidence": d.confidence,
                    "sensor_id": d.sensor_id
                }
                for d in sorted_detections[:limit]
            ]

audio_service = AudioService()