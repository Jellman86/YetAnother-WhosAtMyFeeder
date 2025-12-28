import json
import structlog
from datetime import datetime
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.media_cache import media_cache
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService

log = structlog.get_logger()


class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.detection_service = DetectionService(classifier)

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

                # Apply common filtering and labeling logic
                top = self.detection_service.filter_and_label(results[0], frigate_event)
                if not top:
                    return

                label = top['label']
                
                # Capture Frigate metadata
                frigate_score = after.get('top_score')
                if frigate_score is None and 'data' in after:
                    frigate_score = after['data'].get('top_score')
                    
                sub_label = after.get('sub_label')

                # Save detection (upsert)
                await self.detection_service.save_detection(
                    frigate_event=frigate_event,
                    camera=camera,
                    start_time=after['start_time'],
                    classification=top,
                    frigate_score=frigate_score,
                    sub_label=sub_label
                )
                
                # Update Frigate sublabel if we are confident
                await frigate_client.set_sublabel(frigate_event, label)

            except Exception as e:
                log.error("Error processing event", event=frigate_event, error=str(e))

        except json.JSONDecodeError:
            log.error("Invalid JSON payload")
