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
                         frigate_sub_label: str = None) -> dict | None:
        """
        Apply filtering and relabeling rules to a classification result.
        Returns the modified classification dict or None if filtered out.

        If YA-WAMF classification fails threshold but Frigate has a sublabel,
        falls back to using Frigate's identification (when trust_frigate_sublabel is enabled).
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
            return None

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
            return top

        # Classification failed primary threshold - check if we can fall back to Frigate sublabel
        if settings.classification.trust_frigate_sublabel and frigate_sub_label:
            # Only allow fallback if above the absolute floor (effective_min)
            if not below_min_confidence:
                # Frigate sublabel exists - use it as fallback
                log.info("Using Frigate sublabel as fallback",
                         frigate_label=frigate_sub_label,
                         yawamf_label=original_label,
                         yawamf_score=score,
                         event_id=frigate_event)
                return {
                    'label': frigate_sub_label,
                    'score': score,  # Keep original score for reference
                    'index': top.get('index', -1),
                    'source': 'frigate_fallback'
                }

        # No fallback available or below absolute floor
        if below_min_confidence:
            log.debug("Below minimum confidence", score=score, min=effective_min, event_id=frigate_event)
        else:
            log.debug("Below threshold", score=score, threshold=settings.classification.threshold, event_id=frigate_event)

        return None

    async def save_detection(self, frigate_event: str, camera: str, start_time: float, 
                           classification: dict, frigate_score: float = None, sub_label: str = None,
                           audio_confirmed: bool = False, audio_species: str = None, audio_score: float = None,
                           temperature: float = None, weather_condition: str = None) -> bool:
        """
        Save or update a detection in the database and broadcast the event.
        Returns True if a change was made (insert or update).
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
            changed, _ = await repo.upsert_if_higher_score(detection)

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
            
            return changed
