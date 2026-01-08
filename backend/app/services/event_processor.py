import json
import asyncio
import structlog
from datetime import datetime
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.media_cache import media_cache
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService
from app.services.audio.audio_service import audio_service
from app.services.weather_service import weather_service
from app.services.notification_service import notification_service

log = structlog.get_logger()


class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.detection_service = DetectionService(classifier)

    async def process_audio_message(self, payload: bytes):
        """Process audio detections from BirdNET-Go."""
        try:
            data = json.loads(payload)
            await audio_service.add_detection(data)
        except Exception as e:
            log.error("Failed to process audio message", error=str(e))

    async def process_mqtt_message(self, payload: bytes):
        try:
            data = json.loads(payload)
            after = data.get('after', {})
            
            if not after:
                return

            label = after.get('label')
            log.info("Processing MQTT event", event_id=after.get('id'), label=label, type=data.get('type'))

            if label != 'bird':
                return

            camera = after.get('camera')
            if settings.frigate.camera and camera not in settings.frigate.camera:
                log.info("Filtering event by camera", camera=camera, allowed=settings.frigate.camera)
                return

            frigate_event = after['id']
            start_time_ts = after['start_time']

            sub_label = after.get('sub_label')
            frigate_score = after.get('top_score')
            if frigate_score is None and 'data' in after:
                frigate_score = after['data'].get('top_score')

            # --- Trust Frigate Sublabel Logic ---
            # If Frigate already identified a species and we trust it, skip our classification
            if settings.classification.trust_frigate_sublabel and sub_label:
                log.info("Using Frigate sublabel (skipping classification)", 
                         event=frigate_event, sub_label=sub_label, score=frigate_score)
                
                # We still need to format it for the detection service
                results = [{
                    "label": sub_label,
                    "score": frigate_score or 1.0,
                    "index": -1
                }]
            else:
                # Normal path: YA-WAMF classification
                try:
                    # Fetch snapshot using centralized Frigate client
                    snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=95)
                    if not snapshot_data:
                        return

                    # Cache snapshot immediately when processing detection
                    if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
                        await media_cache.cache_snapshot(frigate_event, snapshot_data)

                    image = Image.open(BytesIO(snapshot_data))

                    # Classify (async to prevent blocking loop)
                    results = await self.classifier.classify_async(image)
                    if not results:
                        return
                except Exception as e:
                    log.error("Classification failed", event_id=frigate_event, error=str(e))
                    return

            # Apply common filtering and labeling logic (with Frigate sublabel for fallback if needed)
            top, _ = self.detection_service.filter_and_label(results[0], frigate_event, sub_label)
            if not top:
                return

            label = top['label']
            score = top['score']

            # --- Parallel Context Gathering (Audio + Weather) ---
            # Fetch audio and weather data concurrently for better performance
            detection_dt = datetime.fromtimestamp(start_time_ts)

            async def fetch_audio():
                """Fetch audio match with error handling."""
                try:
                    return await audio_service.find_match(detection_dt, camera_name=camera, window_seconds=30)
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

            # --- Audio Correlation ---
            audio_confirmed = False
            audio_species = None
            audio_score = None

            if audio_match:
                audio_species = audio_match.species
                audio_score = audio_match.confidence

                # Logic 1: Confirmation
                if audio_species.lower() == label.lower():
                    audio_confirmed = True
                    log.info("Audio confirmed visual detection", event_id=frigate_event, species=label)

                # Logic 2: Enhancement (Unknown -> Audio Label)
                # If visual is generic/unknown but audio is strong, upgrade it
                elif label in settings.classification.unknown_bird_labels or label == "Unknown Bird":
                    if audio_score > 0.7: # High confidence audio
                        log.info("Upgrading visual detection with audio", old=label, new=audio_species)
                        label = audio_species
                        top['label'] = label # Update the classification dict passed to filtering
                        audio_confirmed = True # Implicitly confirmed by audio source
            # -------------------------

            # --- Weather Context ---
            temperature = None
            weather_condition = None
            if weather_data:
                temperature = weather_data.get("temperature")
                weather_condition = weather_data.get("condition_text")
            # -----------------------

            # -----------------------

            # Save detection (upsert)
            changed = await self.detection_service.save_detection(
                frigate_event=frigate_event,
                camera=camera,
                start_time=start_time_ts,
                classification=top,
                frigate_score=frigate_score,
                sub_label=sub_label,
                audio_confirmed=audio_confirmed,
                audio_species=audio_species,
                audio_score=audio_score,
                temperature=temperature,
                weather_condition=weather_condition
            )
            
            # Update Frigate sublabel if we are confident (visual or audio confirmed)
            # Only if score is high enough or audio confirmed it
            if score > settings.classification.threshold or audio_confirmed:
                await frigate_client.set_sublabel(frigate_event, label)

            # --- Notifications ---
            if changed:
                # Prepare notification data
                snapshot_url = f"{settings.frigate.frigate_url}/api/events/{frigate_event}/snapshot.jpg"

                # Fetch snapshot data if we don't have it (e.g. Frigate fallback path) 
                # AND notification settings require it
                needs_snapshot = (settings.notifications.pushover.enabled and settings.notifications.pushover.include_snapshot) or \
                                 (settings.notifications.telegram.enabled and settings.notifications.telegram.include_snapshot)
                
                if snapshot_data is None and needs_snapshot:
                     snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=85)

                # Resolve names (we rely on detection service doing this internally, 
                # but we need them here for the notification text. 
                # Optimization: detection service could return the full detection object, 
                # but for now we can just re-resolve or assume 'label' is scientific if unknown, etc.
                # Actually, detection service broadcasts the resolved names. 
                # Ideally, save_detection should return the detection object.
                # For now, let's just trigger it. The notification service handles some text formatting,
                # but we need scientific/common names. 
                # We can call taxonomy service here, it's cached.
                from app.services.taxonomy.taxonomy_service import taxonomy_service
                taxonomy = await taxonomy_service.get_names(label)
                
                # Fire notification
                await notification_service.notify_detection(
                    frigate_event=frigate_event,
                    species=label,
                    scientific_name=taxonomy.get("scientific_name"),
                    common_name=taxonomy.get("common_name"),
                    confidence=score,
                    camera=camera,
                    timestamp=detection_dt,
                    snapshot_url=snapshot_url,
                    audio_confirmed=audio_confirmed,
                    audio_species=audio_species,
                    snapshot_data=snapshot_data
                )

                # --- Auto Video Classification ---
                if settings.classification.auto_video_classification:
                    from app.services.auto_video_classifier_service import auto_video_classifier
                    await auto_video_classifier.trigger_classification(frigate_event, camera)

        except json.JSONDecodeError as e:
            log.error("Invalid JSON payload", error=str(e))
        except Exception as e:
            # frigate_event may not be defined if error occurred early
            event_id = locals().get('frigate_event', 'unknown')
            log.error("Error processing event", event_id=event_id, error=str(e), exc_info=True)
