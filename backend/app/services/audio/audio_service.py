import structlog
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Deque
from dataclasses import dataclass
from collections import deque
from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

log = structlog.get_logger()

@dataclass
class AudioDetection:
    timestamp: datetime
    species: str
    confidence: float
    sensor_id: Optional[str]
    raw_data: dict
    scientific_name: Optional[str] = None

class AudioService:
    def __init__(self):
        # Store recent audio detections in memory for correlation
        self._buffer: Deque[AudioDetection] = deque()
        # Get buffer duration from settings (convert hours to minutes)
        buffer_minutes = settings.frigate.audio_buffer_hours * 60
        self._buffer_duration = timedelta(minutes=buffer_minutes)
        self._lock = asyncio.Lock()
        log.info("AudioService initialized",
                 buffer_duration_hours=settings.frigate.audio_buffer_hours,
                 correlation_window_seconds=settings.frigate.audio_correlation_window_seconds)

    @staticmethod
    def _extract_birdnet_mapping_key(data: dict) -> Optional[str]:
        """Return the canonical BirdNET source key used for camera mapping.

        Hard switch semantics:
        - Prefer stable source names (`nm`, `Source.displayName`)
        - Fall back to ID-style values for malformed/older payloads
        """
        source = data.get("Source")
        source = source if isinstance(source, dict) else {}

        candidates = (
            data.get("nm"),
            source.get("displayName"),
            data.get("sourceId"),
            data.get("src"),
            data.get("id"),
            data.get("sensor_id"),
            source.get("id"),
        )
        for value in candidates:
            if isinstance(value, str):
                value = value.strip()
                if value:
                    return value
        return None

    @staticmethod
    def _normalize_mapping_key(value: Optional[str]) -> Optional[str]:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.casefold()

    @classmethod
    def _parse_expected_mapping_keys(cls, expected_sensor_id: Optional[str]) -> tuple[bool, set[str]]:
        if not isinstance(expected_sensor_id, str):
            return True, set()

        tokens = [
            cls._normalize_mapping_key(token)
            for token in re.split(r"[,\n;|]+", expected_sensor_id)
        ]
        normalized_keys = {token for token in tokens if token}
        if not normalized_keys or "*" in normalized_keys:
            return True, set()
        return False, normalized_keys

    @classmethod
    def _extract_birdnet_source_keys(cls, data: dict | None) -> set[str]:
        source = data.get("Source") if isinstance(data, dict) else None
        source = source if isinstance(source, dict) else {}

        keys: set[str] = set()
        for candidate in (
            data.get("nm") if isinstance(data, dict) else None,
            source.get("displayName"),
            data.get("src") if isinstance(data, dict) else None,
            data.get("sourceId") if isinstance(data, dict) else None,
            source.get("id"),
            data.get("id") if isinstance(data, dict) else None,
            data.get("sensor_id") if isinstance(data, dict) else None,
        ):
            normalized = cls._normalize_mapping_key(candidate)
            if normalized:
                keys.add(normalized)
        return keys

    @classmethod
    def _camera_mapping_matches_detection(cls, expected_sensor_id: Optional[str], detection: AudioDetection) -> bool:
        wildcard, expected_keys = cls._parse_expected_mapping_keys(expected_sensor_id)
        if wildcard:
            return True

        detection_keys: set[str] = set()
        normalized_sensor = cls._normalize_mapping_key(detection.sensor_id)
        if normalized_sensor:
            detection_keys.add(normalized_sensor)
        detection_keys.update(cls._extract_birdnet_source_keys(detection.raw_data))
        return bool(expected_keys.intersection(detection_keys))

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

            # Canonical BirdNET source key for camera mapping (prefer stable source names)
            sensor_id = self._extract_birdnet_mapping_key(data)

            # Resolve scientific name for robust matching across languages
            scientific_name = data.get("ScientificName")
            if not scientific_name:
                try:
                    from app.services.taxonomy.taxonomy_service import taxonomy_service
                    taxonomy = await taxonomy_service.get_names(species)
                    scientific_name = taxonomy.get("scientific_name")
                except Exception as e:
                    # Keep ingesting audio events even if taxonomy lookup is unavailable.
                    scientific_name = None
                    log.warning("Failed to resolve audio taxonomy; using raw species name",
                                species=species, error=str(e))

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
                raw_data=data,
                scientific_name=scientific_name
            )

            async with self._lock:
                self._buffer.append(detection)
                buffer_len = len(self._buffer)
                log.info("Audio detection added to buffer", species=species, scientific=scientific_name, confidence=confidence, sensor_id=sensor_id, ts=timestamp.isoformat(), buffer_len=buffer_len)
                self._cleanup_buffer()

            try:
                async with get_db() as db:
                    repo = DetectionRepository(db)
                    await repo.insert_audio_detection(
                        timestamp=timestamp,
                        species=species,
                        confidence=float(confidence),
                        sensor_id=sensor_id,
                        raw_data=data,
                        scientific_name=scientific_name
                    )
            except Exception as e:
                log.warning("Failed to persist audio detection", error=str(e))
            
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

    async def find_match(self, target_time: datetime, camera_name: str = None, window_seconds: int = None) -> Optional[AudioDetection]:
        """Find an audio detection matching the visual timestamp and camera.

        Args:
            target_time: Timestamp of the visual detection
            camera_name: Name of the Frigate camera (used for mapping)
            window_seconds: Match window in seconds (defaults to settings value)
        """
        if window_seconds is None:
            window_seconds = settings.frigate.audio_correlation_window_seconds
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
                # Match against normalized sensor keys, with raw payload fallbacks for legacy IDs.
                if not self._camera_mapping_matches_detection(expected_sensor_id, detection):
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
        window_seconds: int = None
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """Check if a specific species has audio confirmation at target time.

        This is used during reclassification to re-correlate audio with the new species.

        Args:
            target_time: Timestamp of the visual detection
            species_name: Scientific or common name to match against
            camera_name: Name of the Frigate camera (used for mapping)
            window_seconds: Match window in seconds (defaults to settings value)

        Returns:
            Tuple of (audio_confirmed, audio_species, audio_score)
            - If match found: (True, matched_species_name, confidence)
            - If no match: (False, None, None)
        """
        if window_seconds is None:
            window_seconds = settings.frigate.audio_correlation_window_seconds
        
        # Get scientific name for the species we're looking for
        taxonomy: dict = {}
        try:
            from app.services.taxonomy.taxonomy_service import taxonomy_service
            taxonomy = await taxonomy_service.get_names(species_name)
        except Exception as e:
            log.warning("Audio correlation taxonomy lookup failed; falling back to raw names",
                        species=species_name, error=str(e))

        target_query = (species_name or "").lower().strip()
        target_scientific = (taxonomy.get("scientific_name") or species_name or "").lower().strip()
        target_common = (taxonomy.get("common_name") or species_name or "").lower().strip()

        async with self._lock:
            self._cleanup_buffer()

            # Determine which sensor ID we are looking for based on camera mapping
            expected_sensor_id = None
            if camera_name and settings.frigate.camera_audio_mapping:
                expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera_name)

            # Ensure target_time is timezone-aware (assume UTC if naive)
            if target_time.tzinfo is None:
                target_time = target_time.replace(tzinfo=timezone.utc)

            best_match = None
            highest_score = 0.0

            for detection in self._buffer:
                # Match against normalized sensor keys, with raw payload fallbacks for legacy IDs.
                if not self._camera_mapping_matches_detection(expected_sensor_id, detection):
                    continue

                # Ensure detection timestamp is timezone-aware (assume UTC if naive)
                det_ts = detection.timestamp
                if det_ts.tzinfo is None:
                    det_ts = det_ts.replace(tzinfo=timezone.utc)

                # Check if time window matches
                delta = abs((det_ts - target_time).total_seconds())
                if delta > window_seconds:
                    continue

                # Match against multiple fields for cross-language robustness
                audio_species = detection.species.lower().strip()
                audio_scientific = (detection.scientific_name or "").lower().strip()
                
                matches = (
                    audio_species == target_query or
                    audio_species == target_scientific or
                    audio_species == target_common or
                    (audio_scientific and (
                        audio_scientific == target_query or
                        audio_scientific == target_scientific or
                        audio_scientific == target_common
                    ))
                )

                if matches:
                    if detection.confidence > highest_score:
                        highest_score = detection.confidence
                        best_match = detection

            if best_match:
                log.info("Audio correlation match found",
                         query=species_name,
                         target_sci=target_scientific,
                         audio_species=best_match.species,
                         audio_sci=best_match.scientific_name,
                         confidence=best_match.confidence,
                         time_delta_sec=abs((best_match.timestamp - target_time).total_seconds()))
                return (True, best_match.species, best_match.confidence)
            else:
                log.debug("No audio correlation found",
                          species=species_name,
                          target_time=target_time.isoformat(),
                          window_seconds=window_seconds,
                          buffer_size=len(self._buffer))
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
                    "sensor_id": d.sensor_id,
                    "scientific_name": d.scientific_name,
                }
                for d in sorted_detections[:limit]
            ]

    async def get_detections_near(
        self,
        target_time: datetime,
        camera_name: str | None = None,
        window_seconds: int | None = None,
        limit: int = 5
    ) -> list[dict]:
        """Get audio detections within a time window around a target timestamp."""
        if window_seconds is None:
            window_seconds = 300

        async with self._lock:
            self._cleanup_buffer()

            expected_sensor_id = None
            if camera_name and settings.frigate.camera_audio_mapping:
                expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera_name)

            if target_time.tzinfo is None:
                target_time = target_time.replace(tzinfo=timezone.utc)

            matches: list[tuple[float, AudioDetection]] = []
            for detection in self._buffer:
                if not self._camera_mapping_matches_detection(expected_sensor_id, detection):
                    continue

                det_ts = detection.timestamp
                if det_ts.tzinfo is None:
                    det_ts = det_ts.replace(tzinfo=timezone.utc)

                delta = (det_ts - target_time).total_seconds()
                if abs(delta) <= window_seconds:
                    matches.append((delta, detection))

            matches.sort(key=lambda item: (abs(item[0]), -item[1].confidence))
            return [
                {
                    "timestamp": d.timestamp.isoformat(),
                    "species": d.species,
                    "confidence": d.confidence,
                    "sensor_id": d.sensor_id,
                    "offset_seconds": int(delta)
                }
                for delta, d in matches[:limit]
            ]

audio_service = AudioService()
