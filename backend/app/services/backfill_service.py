import structlog
from datetime import datetime
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.services.frigate_client import frigate_client
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

    async def fetch_frigate_events(self, after_ts: float, before_ts: float, cameras: list[str] = None) -> list[dict]:
        """
        Fetch bird events from Frigate API for a given time range.
        """
        all_events = []

        # If cameras are configured, fetch events for each camera
        camera_list = cameras or settings.frigate.camera or []

        if camera_list:
            # Fetch for each configured camera
            for camera in camera_list:
                events = await frigate_client.list_events(
                    after=after_ts,
                    before=before_ts,
                    label="bird",
                    camera=camera,
                    has_snapshot=True,
                    limit=100
                )
                all_events.extend(events)
        else:
            # Fetch all cameras
            events = await frigate_client.list_events(
                after=after_ts,
                before=before_ts,
                label="bird",
                has_snapshot=True,
                limit=100
            )
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

    async def process_historical_event(self, event: dict) -> str:
        """
        Process a single historical event.
        Returns: 'new', 'skipped', or 'error'
        """
        frigate_event = event.get('id')
        if not frigate_event:
            return 'error'

        try:
            # Fetch snapshot from Frigate using centralized client
            snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=95)
            if not snapshot_data:
                return 'error'

            # Classify the image
            image = Image.open(BytesIO(snapshot_data))
            results = self.classifier.classify(image)

            if not results:
                log.debug("No classification results", event_id=frigate_event)
                return 'error'

            top = results[0]
            score = top['score']
            label = top['label']

            # Relabel unknown bird classifications (e.g., "background" -> "Unknown Bird")
            if label in settings.classification.unknown_bird_labels:
                log.info("Relabeled to Unknown Bird", original=label, event_id=frigate_event)
                label = "Unknown Bird"
                top = {**top, 'label': label}

            # Apply same filters as real-time processing
            if label in settings.classification.blocked_labels:
                log.debug("Filtered blocked label", label=label, event_id=frigate_event)
                return 'skipped'

            if score < settings.classification.min_confidence:
                log.debug("Below minimum confidence", score=score, event_id=frigate_event)
                return 'skipped'

            if score <= settings.classification.threshold:
                log.debug("Below threshold", score=score, event_id=frigate_event)
                return 'skipped'

            # Save to database (atomic insert - skips if already exists)
            timestamp = datetime.fromtimestamp(event.get('start_time', datetime.now().timestamp()))
            camera_name = event.get('camera', 'unknown')
            
            # Capture Frigate metadata
            # Frigate API structure can vary; score often lives in 'data' dict
            frigate_score = event.get('top_score')
            if frigate_score is None and 'data' in event:
                frigate_score = event['data'].get('top_score')
            
            sub_label = event.get('sub_label')

            detection = Detection(
                detection_time=timestamp,
                detection_index=top['index'],
                score=score,
                display_name=label,
                category_name=label,
                frigate_event=frigate_event,
                camera_name=camera_name,
                frigate_score=frigate_score,
                sub_label=sub_label
            )

            async with get_db() as db:
                repo = DetectionRepository(db)
                # Note: insert_if_not_exists will skip if the event ID is already in DB.
                # It won't update existing records with missing metadata.
                # For a true metadata backfill, we'd need an upsert or separate update logic.
                inserted = await repo.insert_if_not_exists(detection)

            if not inserted:
                log.debug("Event already exists, skipped", event_id=frigate_event)
                return 'skipped'

            log.info("Backfilled detection", event_id=frigate_event, species=label, score=score)

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
            log.error("Error processing historical event", event_id=frigate_event, error=str(e))
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
