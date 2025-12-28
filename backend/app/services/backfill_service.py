import structlog
from datetime import datetime
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import ClassifierService
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService

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
        self.detection_service = DetectionService(classifier)

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

            # Use shared filtering and labeling logic
            top = self.detection_service.filter_and_label(results[0], frigate_event)
            if not top:
                # filter_and_label logs the reason (blocked, threshold, etc)
                return 'skipped'

            # Capture Frigate metadata
            frigate_score = event.get('top_score')
            if frigate_score is None and 'data' in event:
                frigate_score = event['data'].get('top_score')
            
            sub_label = event.get('sub_label')
            camera_name = event.get('camera', 'unknown')
            start_time = event.get('start_time', datetime.now().timestamp())

            # Use upsert logic to ensure metadata is updated even if event exists
            changed = await self.detection_service.save_detection(
                frigate_event=frigate_event,
                camera=camera_name,
                start_time=start_time,
                classification=top,
                frigate_score=frigate_score,
                sub_label=sub_label
            )

            if not changed:
                log.debug("Event already exists and score not improved, skipped", event_id=frigate_event)
                return 'skipped'

            log.info("Backfilled detection", event_id=frigate_event, species=top['label'], score=top['score'])
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
