import json
import asyncio
import time
import structlog
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image
from typing import Optional, Dict, Any, Tuple

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.media_cache import media_cache
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService
from app.services.audio.audio_service import audio_service
from app.services.weather_service import weather_service
from app.services.notification_orchestrator import NotificationOrchestrator
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.utils.frigate import normalize_sub_label
# Backward-compat for tests that patch event_processor.notification_service
from app.services.notification_service import notification_service  # noqa: F401
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

log = structlog.get_logger()
FALSE_POSITIVE_TOMBSTONE_TTL_SECONDS = 600.0


class EventData:
    """Data class to hold parsed event information."""

    def __init__(self, data: Dict[str, Any]):
        self.type: str = data.get('type')
        after = data.get('after', {})
        self.frigate_event: str = after.get('id', 'unknown')
        self.camera: str = after.get('camera')
        self.label: str = after.get('label')
        self.start_time_ts: float = after.get('start_time', 0.0)
        self.sub_label: Optional[str] = normalize_sub_label(after.get('sub_label'))
        self.frigate_score: Optional[float] = after.get('top_score')
        self.is_false_positive: bool = after.get('false_positive', False)
        
        if self.frigate_score is None and 'data' in after:
            self.frigate_score = after['data'].get('top_score')
        # Create timezone-aware datetime (Frigate timestamps are in UTC)
        self.detection_dt: datetime = datetime.fromtimestamp(self.start_time_ts, tz=timezone.utc)


class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.detection_service = DetectionService(classifier)
        self.notification_orchestrator = NotificationOrchestrator()
        self._false_positive_tombstones: dict[str, float] = {}

    async def process_audio_message(self, payload: bytes):
        """Process audio detections from BirdNET-Go."""
        try:
            data = json.loads(payload)
            await audio_service.add_detection(data)
        except Exception as e:
            log.error("Failed to process audio message", error=str(e))

    async def process_mqtt_message(self, payload: bytes):
        """Main entry point for processing Frigate MQTT events."""
        event_id = "unknown"
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                after = data.get("after")
                if isinstance(after, dict):
                    event_id = str(after.get("id") or "unknown")
            await self._process_event_payload(data)
        except json.JSONDecodeError as e:
            log.error("Invalid JSON payload", error=str(e))
        except Exception as e:
            log.error("Error processing event", event_id=event_id, error=str(e), exc_info=True)
            return

    async def _process_event_payload(self, data: Dict[str, Any]) -> None:
        """Process a decoded MQTT payload end-to-end with guardrails."""
        event = self._parse_and_validate_event(data)
        if not event:
            return

        if event.is_false_positive:
            self._mark_false_positive_tombstone(event.frigate_event)
            log.info("Frigate marked event as false positive - cleaning up", event_id=event.frigate_event)
            await self._handle_false_positive(event.frigate_event)
            return

        if self._is_false_positive_tombstone_active(event.frigate_event):
            log.info("Skipping event previously marked as false positive", event_id=event.frigate_event)
            return

        classification_result = await self._classify_snapshot(event)
        if not classification_result:
            return

        results, snapshot_data = classification_result
        if not results:
            return

        top, _ = self.detection_service.filter_and_label(
            results[0], event.frigate_event, event.sub_label, event.frigate_score
        )
        if not top:
            return

        context = await self._gather_context_data(event)
        top_with_audio = await self._correlate_audio(top, context['audio_match'])
        await self._handle_detection_save_and_notify(
            event, top_with_audio, snapshot_data, context
        )

    def _prune_false_positive_tombstones(self) -> None:
        now = time.monotonic()
        expired = [event_id for event_id, expiry in self._false_positive_tombstones.items() if expiry <= now]
        for event_id in expired:
            self._false_positive_tombstones.pop(event_id, None)

    def _mark_false_positive_tombstone(self, event_id: str) -> None:
        if not event_id:
            return
        self._prune_false_positive_tombstones()
        self._false_positive_tombstones[event_id] = time.monotonic() + FALSE_POSITIVE_TOMBSTONE_TTL_SECONDS

    def _is_false_positive_tombstone_active(self, event_id: str) -> bool:
        if not event_id:
            return False
        self._prune_false_positive_tombstones()
        expiry = self._false_positive_tombstones.get(event_id)
        return bool(expiry and expiry > time.monotonic())

    async def _handle_false_positive(self, frigate_event_id: str):
        """Delete detection if Frigate marks it as false positive."""
        try:
            # Clean up cached media immediately
            await media_cache.delete_cached_media(frigate_event_id)

            async with get_db() as db:
                repo = DetectionRepository(db)
                # Check if it exists
                exists = await repo.get_by_frigate_event(frigate_event_id)
                if exists:
                    log.info("Deleting false positive detection", event_id=frigate_event_id)
                    await repo.delete(frigate_event_id)
                    
                    # Notify frontend of deletion (if SSE connected)
                    from app.services.broadcaster import broadcaster
                    await broadcaster.broadcast({
                        "type": "detection_deleted",
                        "data": {
                            "frigate_event": frigate_event_id,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
        except Exception as e:
            log.error("Failed to cleanup false positive", event_id=frigate_event_id, error=str(e))

    def _parse_and_validate_event(self, data: Dict[str, Any]) -> Optional[EventData]:
        """Parse MQTT message and validate it should be processed.

        Returns:
            EventData if valid, None if should be skipped
        """
        after = data.get('after', {})
        if not after:
            return None

        event = EventData(data)
        event_type = (event.type or "new").lower()
        
        # Log processing start
        if event_type == "new" or event.is_false_positive:
             log.info("Processing MQTT event", event_id=event.frigate_event, label=event.label, type=event.type, false_positive=event.is_false_positive)

        # Only process bird events
        if event.label != 'bird':
            return None

        # Ignore routine update chatter; keep actionable events only.
        # False positives can arrive on updates, so always allow cleanup path.
        if not event.is_false_positive and event_type not in {"new", "end"}:
            return None

        if not event.frigate_event or event.frigate_event == "unknown":
            log.warning("Skipping event with missing id", event_id=event.frigate_event)
            return None

        if not event.camera:
            log.warning("Skipping event with missing camera", event_id=event.frigate_event)
            return None

        # Filter by camera if configured
        if settings.frigate.camera and event.camera not in settings.frigate.camera:
            # Only log this once per event (on new) to avoid spam
            if event_type == "new":
                log.info("Filtering event by camera", camera=event.camera, allowed=settings.frigate.camera)
            return None

        return event

    async def _classify_snapshot(self, event: EventData) -> Optional[Tuple[list, Optional[bytes]]]:
        """Classify snapshot or use Frigate sublabel if trusted.

        Returns:
            Tuple of (classification_results, snapshot_data) if successful, None otherwise
        """
        # Trust Frigate sublabel path
        if settings.classification.trust_frigate_sublabel and event.sub_label:
            log.info("Using Frigate sublabel (skipping classification)",
                     event=event.frigate_event, sub_label=event.sub_label, score=event.frigate_score)

            results = [{
                "label": event.sub_label,
                "score": event.frigate_score or 1.0,
                "index": -1
            }]
            return (results, None)

        # Normal classification path
        try:
            snapshot_data = await frigate_client.get_snapshot(event.frigate_event, crop=True, quality=95)
            if not snapshot_data:
                return None

            image = Image.open(BytesIO(snapshot_data))
            results = await self.classifier.classify_async(image, camera_name=event.camera)

            if not results:
                return None

            return (results, snapshot_data)

        except Exception as e:
            log.error("Classification failed", event_id=event.frigate_event, error=str(e))
            return None

    async def _gather_context_data(self, event: EventData) -> Dict[str, Any]:
        """Gather audio and weather context data in parallel.

        Returns:
            Dict with 'audio_match' and 'weather_data' keys
        """
        async def fetch_audio():
            """Fetch audio match with error handling."""
            try:
                return await audio_service.find_match(
                    event.detection_dt,
                    camera_name=event.camera,
                    window_seconds=settings.frigate.audio_correlation_window_seconds
                )
            except Exception as e:
                log.warning("Audio match failed", error=str(e))
                return None

        async def fetch_weather():
            """Fetch weather with error handling."""
            try:
                return await weather_service.get_current_weather()
            except Exception as e:
                log.warning("Weather fetch failed", error=str(e))
                return None

        # Execute both lookups in parallel
        audio_match, weather_data = await asyncio.gather(
            fetch_audio(),
            fetch_weather(),
            return_exceptions=False
        )

        return {
            'audio_match': audio_match,
            'weather_data': weather_data
        }

    async def _correlate_audio(self, classification: Dict[str, Any], audio_match) -> Dict[str, Any]:
        """Correlate audio detection with visual classification.

        Modifies classification dict with audio correlation data.

        Returns:
            Updated classification dict
        """
        # Initialize audio fields (only set when confirmed or used for upgrade)
        classification['audio_confirmed'] = False
        classification['audio_species'] = None
        classification['audio_score'] = None

        if not audio_match:
            return classification

        audio_species = audio_match.species
        audio_score = audio_match.confidence
        visual_label = classification['label']
        visual_label_normalized = str(visual_label or "").strip().lower()
        audio_species_normalized = str(audio_species or "").strip().lower()
        audio_scientific_normalized = str(getattr(audio_match, "scientific_name", "") or "").strip().lower()

        visual_aliases = {visual_label_normalized}
        try:
            taxonomy = await taxonomy_service.get_names(visual_label)
            sci = str(taxonomy.get("scientific_name") or "").strip().lower()
            common = str(taxonomy.get("common_name") or "").strip().lower()
            if sci:
                visual_aliases.add(sci)
            if common:
                visual_aliases.add(common)
        except Exception as e:
            log.debug("Visual taxonomy lookup failed during audio correlation", label=visual_label, error=str(e))

        audio_aliases = {audio_species_normalized}
        if audio_scientific_normalized:
            audio_aliases.add(audio_scientific_normalized)
        else:
            try:
                audio_taxonomy = await taxonomy_service.get_names(audio_species)
                audio_sci = str(audio_taxonomy.get("scientific_name") or "").strip().lower()
                audio_common = str(audio_taxonomy.get("common_name") or "").strip().lower()
                if audio_sci:
                    audio_aliases.add(audio_sci)
                if audio_common:
                    audio_aliases.add(audio_common)
            except Exception as e:
                log.debug("Audio taxonomy lookup failed during audio correlation", species=audio_species, error=str(e))

        # Logic 1: Confirmation - audio matches visual
        if visual_aliases.intersection(audio_aliases):
            classification['audio_confirmed'] = True
            classification['audio_species'] = audio_species
            classification['audio_score'] = audio_score
            # Boost score if audio is more confident
            if audio_score > classification['score']:
                classification['score'] = audio_score
            log.info("Audio confirmed visual detection", species=visual_label, score=classification['score'])
        else:
            # Mismatch: Attach audio species/score for 'also heard' display, but don't confirm or upgrade
            classification['audio_confirmed'] = False
            classification['audio_species'] = audio_species
            classification['audio_score'] = audio_score
            log.debug("Audio recorded as heard (not confirmed)", visual=visual_label, audio=audio_species)

        return classification

    def _extract_weather_fields(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract weather fields from context payload."""
        weather = context.get('weather_data') or {}
        return {
            "temperature": weather.get("temperature"),
            "weather_condition": weather.get("condition_text"),
            "weather_cloud_cover": weather.get("cloud_cover"),
            "weather_wind_speed": weather.get("wind_speed"),
            "weather_wind_direction": weather.get("wind_direction"),
            "weather_precipitation": weather.get("precipitation"),
            "weather_rain": weather.get("rain"),
            "weather_snowfall": weather.get("snowfall"),
        }

    async def _handle_detection_save_and_notify(
        self,
        event: EventData,
        classification: Dict[str, Any],
        snapshot_data: Optional[bytes],
        context: Dict[str, Any]
    ):
        """Save detection to database and send notifications.

        Args:
            event: Parsed event data
            classification: Classification result with audio correlation
            snapshot_data: Snapshot image bytes (may be None)
            context: Context data (audio_match, weather_data)
        """
        label = classification['label']
        score = classification['score']

        weather_fields = self._extract_weather_fields(context)

        # Save detection (upsert)
        changed, was_inserted = await self.detection_service.save_detection(
            frigate_event=event.frigate_event,
            camera=event.camera,
            start_time=event.start_time_ts,
            classification=classification,
            frigate_score=event.frigate_score,
            sub_label=event.sub_label,
            audio_confirmed=classification['audio_confirmed'],
            audio_species=classification['audio_species'],
            audio_score=classification['audio_score'],
            temperature=weather_fields["temperature"],
            weather_condition=weather_fields["weather_condition"],
            weather_cloud_cover=weather_fields["weather_cloud_cover"],
            weather_wind_speed=weather_fields["weather_wind_speed"],
            weather_wind_direction=weather_fields["weather_wind_direction"],
            weather_precipitation=weather_fields["weather_precipitation"],
            weather_rain=weather_fields["weather_rain"],
            weather_snowfall=weather_fields["weather_snowfall"]
        )

        # Update Frigate sublabel if confident
        if score > settings.classification.threshold or classification['audio_confirmed']:
            await frigate_client.set_sublabel(event.frigate_event, label)

        # Send notifications based on policy
        if changed:
            # Cache snapshot if we updated the DB (ensures image matches score)
            if snapshot_data and settings.media_cache.enabled and settings.media_cache.cache_snapshots:
                await media_cache.cache_snapshot(event.frigate_event, snapshot_data)

            # Trigger auto video classification
            if settings.classification.auto_video_classification:
                from app.services.auto_video_classifier_service import auto_video_classifier
                await auto_video_classifier.trigger_classification(event.frigate_event, event.camera)

        await self.notification_orchestrator.handle_notifications(
            event=event,
            classification=classification,
            snapshot_data=snapshot_data,
            changed=changed,
            was_inserted=was_inserted
        )
