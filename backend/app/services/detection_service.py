import structlog
from datetime import datetime
from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.birdweather_service import birdweather_service
from app.database import get_db

log = structlog.get_logger()

class DetectionService:
    """
    Centralized service for processing and saving detections.
    
    Shared logic used by:
    - EventProcessor (real-time MQTT events)
    - BackfillService (historical API events)
    """
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.broadcaster = broadcaster

    def filter_and_label(self, classification: dict, frigate_event: str,
                         frigate_sub_label: str = None, frigate_score: float = None) -> tuple[dict | None, str | None]:
        """
        Apply filtering and relabeling rules to a classification result.
        Returns (result_dict, reason_code).
        reason_code is populated when result is None (skip reason) or informative when result exists.
        """
        top = classification
        score = top['score']
        label = top['label']
        original_label = label

        # Relabel unknown bird classifications
        if label in settings.classification.unknown_bird_labels:
            log.info("Relabeled to Unknown Bird", original=label, event_id=frigate_event)
            label = "Unknown Bird"
            top = {**top, 'label': label}

        # Filter out blocked labels
        if label in settings.classification.blocked_labels:
            log.debug("Filtered blocked label", label=label, event_id=frigate_event)
            return None, "blocked_label"

        # Determine effective minimum confidence (floor)
        # If user sets threshold lower than min_confidence, use threshold as floor
        effective_min = min(settings.classification.min_confidence, settings.classification.threshold)

        # Check minimum confidence floor
        below_min_confidence = score < effective_min

        # Check primary threshold
        below_threshold = score <= settings.classification.threshold

        # If classification passes primary threshold, return it
        # (Implicitly passes min_confidence because threshold >= effective_min)
        if not below_threshold:
            return top, "threshold_passed"

        # Classification failed primary threshold - check if we can fall back to Frigate sublabel
        if settings.classification.trust_frigate_sublabel and frigate_sub_label:
            # Use Frigate score if available, otherwise boost current score to threshold to ensure visibility
            # but usually Frigate score is reliable.
            final_score = frigate_score if (frigate_score and frigate_score > 0) else max(score, settings.classification.threshold)
            
            # Frigate sublabel exists - use it as fallback regardless of confidence
            log.info("Using Frigate sublabel as fallback",
                     frigate_label=frigate_sub_label,
                     yawamf_label=original_label,
                     yawamf_score=score,
                     final_score=final_score,
                     event_id=frigate_event)
            return {
                'label': frigate_sub_label,
                'score': final_score,
                'index': top.get('index', -1),
                'source': 'frigate_fallback'
            }, "frigate_fallback"

        # Check for "Unknown Bird" catch-all (middle ground between min_confidence and threshold)
        if not below_min_confidence:
            log.info("Low confidence detection, saving as Unknown", 
                     original=original_label, 
                     score=score, 
                     event_id=frigate_event)
            return {
                'label': "Unknown Bird",
                'score': score,
                'index': top.get('index', -1),
                'source': 'low_confidence_catchall'
            }, "unknown_catchall"

        # No fallback available or below absolute floor
        if below_min_confidence:
            log.debug("Below minimum confidence", score=score, min=effective_min, event_id=frigate_event)
            return None, "low_confidence"
        else:
            # This branch implies (not below_min and below_threshold) which is handled by catch-all above
            # But just in case logic drifts:
            log.debug("Below threshold", score=score, threshold=settings.classification.threshold, event_id=frigate_event)
            return None, "below_threshold"

    async def save_detection(self, frigate_event: str, camera: str, start_time: float, 
                           classification: dict, frigate_score: float = None, sub_label: str = None,
                           audio_confirmed: bool = False, audio_species: str = None, audio_score: float = None,
                           temperature: float = None, weather_condition: str = None) -> tuple[bool, bool]:
        """
        Save or update a detection in the database and broadcast the event.
        Returns (changed, was_inserted).
        """
        # 1. Normalize names (Bidirectional Scientific <-> Common)
        label = classification['label']
        taxonomy = await taxonomy_service.get_names(label)
        
        scientific_name = taxonomy.get("scientific_name") or label
        common_name = taxonomy.get("common_name")
        taxa_id = taxonomy.get("taxa_id")

        # 2. Determine display name based on user preference
        display_name = label
        if settings.classification.display_common_names and common_name:
            display_name = common_name
        elif not settings.classification.display_common_names and scientific_name:
            display_name = scientific_name

        async with get_db() as db:
            repo = DetectionRepository(db)

            score = classification['score']
            category_name = classification['label']
            timestamp = datetime.fromtimestamp(start_time)

            detection = Detection(
                detection_time=timestamp,
                detection_index=classification['index'],
                score=score,
                display_name=display_name,
                category_name=category_name,
                frigate_event=frigate_event,
                camera_name=camera,
                frigate_score=frigate_score,
                sub_label=sub_label,
                audio_confirmed=audio_confirmed,
                audio_species=audio_species,
                audio_score=audio_score,
                temperature=temperature,
                weather_condition=weather_condition,
                scientific_name=scientific_name,
                common_name=common_name,
                taxa_id=taxa_id
            )

            # Atomic upsert: insert or update only if score is higher
            was_inserted, was_updated = await repo.upsert_if_higher_score(detection)
            changed = was_inserted or was_updated

            if changed:
                log.info("Saved detection", 
                         event_id=frigate_event, 
                         species=display_name, 
                         scientific=scientific_name,
                         score=score,
                         frigate_score=frigate_score,
                         audio_confirmed=audio_confirmed,
                         weather=weather_condition)

                # Broadcast event only when actually saved/updated
                await self.broadcaster.broadcast({
                    "type": "detection",
                    "data": {
                        "frigate_event": frigate_event,
                        "display_name": display_name,
                        "scientific_name": scientific_name,
                        "common_name": common_name,
                        "taxa_id": taxa_id,
                        "score": score,
                        "timestamp": timestamp.isoformat(),
                        "camera": camera,
                        "frigate_score": frigate_score,
                        "sub_label": sub_label,
                        "manual_tagged": detection.manual_tagged,
                        "audio_confirmed": audio_confirmed,
                        "audio_species": audio_species,
                        "audio_score": audio_score,
                        "temperature": temperature,
                        "weather_condition": weather_condition
                    }
                })

                # 3. Report to BirdWeather (if enabled)
                if scientific_name and scientific_name != "Unknown Bird":
                    # Run in background to not block the main loop
                    import asyncio
                    asyncio.create_task(birdweather_service.report_detection(
                        scientific_name=scientific_name,
                        common_name=common_name,
                        confidence=score,
                        timestamp=timestamp
                    ))
            
            return changed, was_inserted

    async def get_detection_by_frigate_event(self, frigate_event: str) -> Detection | None:
        """Fetch a detection by Frigate event ID."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            return await repo.get_by_frigate_event(frigate_event)
