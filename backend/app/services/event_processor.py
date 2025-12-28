import json
import structlog
from datetime import datetime
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.services.media_cache import media_cache
from app.services.frigate_client import frigate_client
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, Detection

log = structlog.get_logger()


class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.broadcaster = broadcaster

    async def process_mqtt_message(self, payload: bytes):
        try:
            data = json.loads(payload)
            after = data.get('after', {})
            
            if not after:
                return

            if after.get('label') != 'bird':
                return

            camera = after.get('camera')
            if settings.frigate.camera and camera not in settings.frigate.camera:
                return

            frigate_event = after['id']

            try:
                # Fetch snapshot using centralized Frigate client
                snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=95)
                if not snapshot_data:
                    return

                # Cache snapshot immediately when processing detection
                if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
                    await media_cache.cache_snapshot(frigate_event, snapshot_data)

                image = Image.open(BytesIO(snapshot_data))

                # Classify
                results = self.classifier.classify(image)
                if not results:
                    return

                top = results[0]
                score = top['score']
                label = top['label']

                # Relabel unknown bird classifications (e.g., "background" -> "Unknown Bird")
                if label in settings.classification.unknown_bird_labels:
                    log.info("Relabeled to Unknown Bird", original=label, event=frigate_event)
                    label = "Unknown Bird"
                    top = {**top, 'label': label}

                # Filter out blocked labels (if any configured)
                if label in settings.classification.blocked_labels:
                    log.debug("Filtered blocked label", label=label, event=frigate_event)
                    return

                # Check minimum confidence floor
                if score < settings.classification.min_confidence:
                    log.debug("Below minimum confidence", score=score, min=settings.classification.min_confidence)
                    return

                if score > settings.classification.threshold:
                    await self._save_detection(after, top, frigate_event)
                    await frigate_client.set_sublabel(frigate_event, label)

            except Exception as e:
                log.error("Error processing event", event=frigate_event, error=str(e))

        except json.JSONDecodeError:
            log.error("Invalid JSON payload")

    async def _save_detection(self, after, classification, frigate_event):
        async with get_db() as db:
            repo = DetectionRepository(db)

            score = classification['score']
            display_name = classification['label']
            category_name = classification['label']  # Simplify for now
            timestamp = datetime.fromtimestamp(after['start_time'])

            detection = Detection(
                detection_time=timestamp,
                detection_index=classification['index'],
                score=score,
                display_name=display_name,
                category_name=category_name,
                frigate_event=frigate_event,
                camera_name=after['camera']
            )

            # Atomic upsert: insert or update only if score is higher
            changed, _ = await repo.upsert_if_higher_score(detection)

            if changed:
                log.info("Saved detection", event=frigate_event, species=display_name, score=score)

                # Broadcast event only when actually saved/updated
                await self.broadcaster.broadcast({
                    "type": "detection",
                    "data": {
                        "frigate_event": frigate_event,
                        "display_name": display_name,
                        "score": score,
                        "timestamp": timestamp.isoformat(),
                        "camera": after['camera']
                    }
                })
