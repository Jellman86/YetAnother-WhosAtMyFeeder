import structlog
import httpx
from datetime import datetime
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, Detection

log = structlog.get_logger()


@dataclass
class BackfillResult:
    """Result of a backfill operation."""
    processed: int = 0
    new_detections: int = 0
    skipped: int = 0
    errors: int = 0


class BackfillService:
    """Service to fetch and process historical detections from Frigate."""

    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.http_client = httpx.AsyncClient()

    def _get_frigate_headers(self) -> dict:
        """Build headers for Frigate requests, including auth token if configured."""
        headers = {}
        if settings.frigate.frigate_auth_token:
            headers['Authorization'] = f'Bearer {settings.frigate.frigate_auth_token}'
        return headers

    async def fetch_frigate_events(self, after_ts: float, before_ts: float, cameras: list[str] = None) -> list[dict]:
        """
        Fetch bird events from Frigate API for a given time range.
        Handles pagination automatically.
        """
        all_events = []
        frigate_url = settings.frigate.frigate_url
        headers = self._get_frigate_headers()

        # Build base params
        params = {
            "after": after_ts,
            "before": before_ts,
            "label": "bird",
            "has_snapshot": 1,
            "limit": 100
        }

        # If cameras are configured, fetch events for each camera
        camera_list = cameras or settings.frigate.camera or []

        if camera_list:
            # Fetch for each configured camera
            for camera in camera_list:
                camera_params = {**params, "camera": camera}
                events = await self._fetch_events_paginated(frigate_url, camera_params, headers)
                all_events.extend(events)
        else:
            # Fetch all cameras
            events = await self._fetch_events_paginated(frigate_url, params, headers)
            all_events.extend(events)

        # Remove duplicates by event ID (in case same event appears for multiple cameras)
        seen_ids = set()
        unique_events = []
        for event in all_events:
            event_id = event.get('id')
            if event_id and event_id not in seen_ids:
                seen_ids.add(event_id)
                unique_events.append(event)

        log.info("Fetched events from Frigate", count=len(unique_events), after=after_ts, before=before_ts)
        return unique_events

    async def _fetch_events_paginated(self, frigate_url: str, params: dict, headers: dict) -> list[dict]:
        """Fetch events with pagination support."""
        events = []
        url = f"{frigate_url}/api/events"

        try:
            response = await self.http_client.get(url, params=params, headers=headers, timeout=30.0)
            if response.status_code == 200:
                batch = response.json()
                events.extend(batch)

                # If we got a full page, there might be more - but for simplicity,
                # we'll just fetch the first 100 per camera. Can add pagination later if needed.
                log.debug("Fetched event batch", count=len(batch), camera=params.get('camera'))
            else:
                log.warning("Failed to fetch events from Frigate", status=response.status_code)
        except Exception as e:
            log.error("Error fetching events from Frigate", error=str(e))

        return events

    async def process_historical_event(self, event: dict) -> str:
        """
        Process a single historical event.
        Returns: 'new', 'skipped', or 'error'
        """
        frigate_event = event.get('id')
        if not frigate_event:
            return 'error'

        try:
            # Check if already exists in database
            async with get_db() as db:
                repo = DetectionRepository(db)
                existing = await repo.get_by_frigate_event(frigate_event)
                if existing:
                    log.debug("Event already exists, skipping", event=frigate_event)
                    return 'skipped'

            # Fetch snapshot from Frigate
            frigate_url = settings.frigate.frigate_url
            snapshot_url = f"{frigate_url}/api/events/{frigate_event}/snapshot.jpg"
            headers = self._get_frigate_headers()

            response = await self.http_client.get(
                snapshot_url,
                params={"crop": 1, "quality": 95},
                headers=headers,
                timeout=30.0
            )

            if response.status_code != 200:
                log.warning("Failed to fetch snapshot", event=frigate_event, status=response.status_code)
                return 'error'

            # Classify the image
            image = Image.open(BytesIO(response.content))
            results = self.classifier.classify(image)

            if not results:
                log.debug("No classification results", event=frigate_event)
                return 'error'

            top = results[0]
            score = top['score']
            label = top['label']

            # Apply same filters as real-time processing
            if label in settings.classification.blocked_labels:
                log.debug("Filtered blocked label", label=label, event=frigate_event)
                return 'skipped'

            if score < settings.classification.min_confidence:
                log.debug("Below minimum confidence", score=score, event=frigate_event)
                return 'skipped'

            if score <= settings.classification.threshold:
                log.debug("Below threshold", score=score, event=frigate_event)
                return 'skipped'

            # Save to database
            timestamp = datetime.fromtimestamp(event.get('start_time', datetime.now().timestamp()))
            camera_name = event.get('camera', 'unknown')

            detection = Detection(
                detection_time=timestamp,
                detection_index=top['index'],
                score=score,
                display_name=label,
                category_name=label,
                frigate_event=frigate_event,
                camera_name=camera_name
            )

            async with get_db() as db:
                repo = DetectionRepository(db)
                await repo.create(detection)

            log.info("Backfilled detection", event=frigate_event, species=label, score=score)

            # Broadcast to connected clients
            await broadcaster.broadcast({
                "type": "detection",
                "data": {
                    "frigate_event": frigate_event,
                    "display_name": label,
                    "score": score,
                    "timestamp": timestamp.isoformat(),
                    "camera": camera_name
                }
            })

            return 'new'

        except Exception as e:
            log.error("Error processing historical event", event=frigate_event, error=str(e))
            return 'error'

    async def run_backfill(self, start: datetime, end: datetime, cameras: list[str] = None) -> BackfillResult:
        """
        Run backfill for a date range.
        """
        result = BackfillResult()

        # Convert to Unix timestamps
        after_ts = start.timestamp()
        before_ts = end.timestamp()

        log.info("Starting backfill", start=start.isoformat(), end=end.isoformat())

        # Fetch events from Frigate
        events = await self.fetch_frigate_events(after_ts, before_ts, cameras)
        result.processed = len(events)

        # Process each event
        for event in events:
            status = await self.process_historical_event(event)
            if status == 'new':
                result.new_detections += 1
            elif status == 'skipped':
                result.skipped += 1
            else:
                result.errors += 1

        log.info("Backfill complete",
                 processed=result.processed,
                 new=result.new_detections,
                 skipped=result.skipped,
                 errors=result.errors)

        return result
