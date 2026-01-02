import structlog
from datetime import datetime
from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services.classifier_service import ClassifierService
from app.services.frigate_client import frigate_client
from app.services.broadcaster import broadcaster
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

        # Check minimum confidence floor
        below_min_confidence = score < settings.classification.min_confidence

        # Check primary threshold
        below_threshold = score <= settings.classification.threshold

        # If classification passes, return it
        if not below_min_confidence and not below_threshold:
            return top

        # Classification failed - check if we can fall back to Frigate sublabel
        if settings.classification.trust_frigate_sublabel and frigate_sub_label:
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

        # No fallback available - log the failure reason and return None
        if below_min_confidence:
            log.debug("Below minimum confidence", score=score, min=settings.classification.min_confidence, event_id=frigate_event)
        else:
            log.debug("Below threshold", score=score, threshold=settings.classification.threshold, event_id=frigate_event)

        return None

    async def save_detection(self, frigate_event: str, camera: str, start_time: float, 
                           classification: dict, frigate_score: float = None, sub_label: str = None) -> bool:
        """
        Save or update a detection in the database and broadcast the event.
        Returns True if a change was made (insert or update).
        """
        async with get_db() as db:
            repo = DetectionRepository(db)

            score = classification['score']
            display_name = classification['label']
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
                sub_label=sub_label
            )

            # Atomic upsert: insert or update only if score is higher
            changed, _ = await repo.upsert_if_higher_score(detection)

            if changed:
                log.info("Saved detection", 
                         event_id=frigate_event, 
                         species=display_name, 
                         score=score,
                         frigate_score=frigate_score)

                # Broadcast event only when actually saved/updated
                await self.broadcaster.broadcast({
                    "type": "detection",
                    "data": {
                        "frigate_event": frigate_event,
                        "display_name": display_name,
                        "score": score,
                        "timestamp": timestamp.isoformat(),
                        "camera": camera,
                        "frigate_score": frigate_score,
                        "sub_label": sub_label
                    }
                })
            
            return changed
