import json
import structlog
import httpx
from datetime import datetime
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, Detection

log = structlog.get_logger()

class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.http_client = httpx.AsyncClient()
        self.broadcaster = broadcaster

    def _get_frigate_headers(self) -> dict:
        """Build headers for Frigate requests, including auth token if configured."""
        headers = {}
        if settings.frigate.frigate_auth_token:
            headers['Authorization'] = f'Bearer {settings.frigate.frigate_auth_token}'
        return headers

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
            # Only process if valid event? Original logic processes on every message? 
            # Original: "if not firstmessage ... (after_data['camera'] in config ...)"
            # It processes updates. We typically want the best snapshot.
            
            # Logic: Get snapshot.
            frigate_url = settings.frigate.frigate_url
            snapshot_url = f"{frigate_url}/api/events/{frigate_event}/snapshot.jpg"
            
            # TODO: Add specific params logic (crop=1)
            params = {"crop": 1, "quality": 95}
            
            try:
                headers = self._get_frigate_headers()
                response = await self.http_client.get(snapshot_url, params=params, headers=headers, timeout=30.0)
                if response.status_code == 200:
                   image = Image.open(BytesIO(response.content))
                   
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
                       await self._set_sublabel(frigate_event, label)
                       
                else:
                    log.warning("Failed to fetch snapshot", url=snapshot_url, status=response.status_code)

            except Exception as e:
                log.error("Error processing event", event=frigate_event, error=str(e))

        except json.JSONDecodeError:
            log.error("Invalid JSON payload")

    async def _save_detection(self, after, classification, frigate_event):
        async with get_db() as db:
            repo = DetectionRepository(db)
            existing = await repo.get_by_frigate_event(frigate_event)
            
            score = classification['score']
            display_name = classification['label']
            category_name = classification['label'] # Simplify for now
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
            
            if existing:
                if score > existing.score:
                    await repo.update(detection)
                    log.info("Updated detection", event=frigate_event, species=display_name, score=score)
            else:
                await repo.create(detection)
                log.info("New detection", event=frigate_event, species=display_name, score=score)
            
            # Broadcast event
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

    async def _set_sublabel(self, event_id: str, sublabel: str):
        url = f"{settings.frigate.frigate_url}/api/events/{event_id}/sub_label"
        payload = {"subLabel": sublabel[:20]}
        try:
            headers = self._get_frigate_headers()
            await self.http_client.post(url, json=payload, headers=headers, timeout=10.0)
        except Exception as e:
            log.error("Failed to set sublabel", error=str(e))
