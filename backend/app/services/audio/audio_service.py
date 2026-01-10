import structlog
import asyncio
from datetime import datetime, timedelta, timezone
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
    def __init__(self, buffer_minutes: int = 1440):  # 24 hours = 1440 minutes
        # Store recent audio detections in memory for correlation
        self._buffer: Deque[AudioDetection] = deque()
        self._buffer_duration = timedelta(minutes=buffer_minutes)
        self._lock = asyncio.Lock()
        log.info("AudioService initialized", buffer_duration_hours=buffer_minutes/60)

    async def add_detection(self, data: dict):
        """Ingest a detection from MQTT."""
        try:
            # Use UTC timezone-aware datetime by default
            timestamp = datetime.now(timezone.utc)
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
                    # Create timezone-aware timestamp from Unix timestamp (assumed UTC)
                    timestamp = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                except Exception:
                    pass
            else:
                # Try ISO format from BirdNET-Go (BeginTime)
                iso_ts = data.get("BeginTime") or data.get("EndTime")
                if iso_ts:
                    try:
                        # Handle potential trailing 'Z' or extra precision
                        timestamp = datetime.fromisoformat(iso_ts.replace('Z', '+00:00'))
                        # Ensure timezone-aware (if naive, assume UTC)
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
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
                buffer_len = len(self._buffer)
                log.info("Audio detection added to buffer", species=species, confidence=confidence, sensor_id=sensor_id, ts=timestamp.isoformat(), buffer_len=buffer_len)
                self._cleanup_buffer()
            
        except Exception as e:
            log.error("Failed to process audio detection", error=str(e))

    def _cleanup_buffer(self):
        """Remove old detections from buffer."""
        now = datetime.now(timezone.utc)
        removed_count = 0

        while self._buffer:
            ts = self._buffer[0].timestamp

            # Ensure timezone-aware comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age = (now - ts).total_seconds()

            if age > self._buffer_duration.total_seconds():
                removed_species = self._buffer[0].species
                self._buffer.popleft()
                removed_count += 1
                log.debug("Removed old audio detection", species=removed_species, age=age)
            else:
                break

        if removed_count > 0:
            log.info("Cleaned up audio buffer", removed=removed_count, remaining=len(self._buffer))

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

            # Ensure target_time is timezone-aware (assume UTC if naive)
            if target_time.tzinfo is None:
                target_time = target_time.replace(tzinfo=timezone.utc)

            for detection in self._buffer:
                # If a mapping exists, only match if the sensor ID matches (unless wildcard used)
                if expected_sensor_id and expected_sensor_id != "*" and detection.sensor_id != expected_sensor_id:
                    continue

                # Ensure detection timestamp is timezone-aware (assume UTC if naive)
                det_ts = detection.timestamp
                if det_ts.tzinfo is None:
                    det_ts = det_ts.replace(tzinfo=timezone.utc)

                delta = abs((det_ts - target_time).total_seconds())
                if delta <= window_seconds:
                    if detection.confidence > highest_score:
                        highest_score = detection.confidence
                        best_match = detection

            return best_match

    async def correlate_species(
        self,
        target_time: datetime,
        species_name: str,
        camera_name: str = None,
        window_seconds: int = 15
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """Check if a specific species has audio confirmation at target time.

        This is used during reclassification to re-correlate audio with the new species.

        Args:
            target_time: Timestamp of the visual detection
            species_name: Scientific or common name to match against
            camera_name: Name of the Frigate camera (used for mapping)
            window_seconds: Match window in seconds

        Returns:
            Tuple of (audio_confirmed, audio_species, audio_score)
            - If match found: (True, matched_species_name, confidence)
            - If no match: (False, None, None)
        """
        async with self._lock:
            self._cleanup_buffer()

            # Determine which sensor ID we are looking for based on camera mapping
            expected_sensor_id = None
            if camera_name and settings.frigate.camera_audio_mapping:
                expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera_name)

            # Ensure target_time is timezone-aware (assume UTC if naive)
            if target_time.tzinfo is None:
                target_time = target_time.replace(tzinfo=timezone.utc)

            # Normalize species name for matching (case-insensitive)
            species_lower = species_name.lower().strip()

            best_match = None
            highest_score = 0.0

            for detection in self._buffer:
                # If a mapping exists, only match if the sensor ID matches (unless wildcard used)
                if expected_sensor_id and expected_sensor_id != "*" and detection.sensor_id != expected_sensor_id:
                    continue

                # Ensure detection timestamp is timezone-aware (assume UTC if naive)
                det_ts = detection.timestamp
                if det_ts.tzinfo is None:
                    det_ts = det_ts.replace(tzinfo=timezone.utc)

                # Check if time window matches
                delta = abs((det_ts - target_time).total_seconds())
                if delta > window_seconds:
                    continue

                # Check if species matches (case-insensitive)
                audio_species_lower = detection.species.lower().strip()
                if audio_species_lower == species_lower:
                    # Direct match
                    if detection.confidence > highest_score:
                        highest_score = detection.confidence
                        best_match = detection

            if best_match:
                log.info("Audio correlation match found",
                         species=species_name,
                         audio_species=best_match.species,
                         confidence=best_match.confidence,
                         time_delta_sec=abs((best_match.timestamp - target_time).total_seconds()))
                return (True, best_match.species, best_match.confidence)
            else:
                log.debug("No audio correlation found",
                          species=species_name,
                          target_time=target_time.isoformat())
                return (False, None, None)

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