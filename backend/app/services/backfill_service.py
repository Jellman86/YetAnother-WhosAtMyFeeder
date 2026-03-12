import structlog
import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
from io import BytesIO
from PIL import Image

from app.config import settings
from app.services.classifier_service import (
    BackgroundImageClassificationUnavailableError,
    ClassifierService,
)
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService
from app.services.error_diagnostics import error_diagnostics_history
from app.utils.frigate import normalize_sub_label

log = structlog.get_logger()
BACKFILL_EVENT_TIMEOUT_SECONDS = 75.0
BACKFILL_EVENTS_PAGE_LIMIT = 100
BACKFILL_EVENTS_MAX_PAGES_PER_CAMERA = 1000
BACKFILL_TRANSIENT_RETRY_ATTEMPTS = 2
BACKFILL_TRANSIENT_RETRY_BACKOFF_SECONDS = 1.0
BACKFILL_TRANSIENT_RETRY_MIN_REMAINING_SECONDS = 15.0
BACKFILL_TRANSIENT_RETRY_REASONS = {
    "background_image_worker_unavailable",
    "background_image_worker_startup_timeout",
    "background_image_worker_timed_out",
}


@dataclass
class BackfillResult:
    """Result of a backfill operation."""
    processed: int = 0
    new_detections: int = 0
    skipped: int = 0
    errors: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class BackfillService:
    """Service to fetch and process historical detections from Frigate."""

    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.detection_service = DetectionService(classifier)

    @staticmethod
    def _oldest_event_cursor(events: list[dict], fallback_before_ts: float) -> float | None:
        timestamps: list[float] = []
        for event in events:
            for key in ("start_time", "end_time"):
                value = event.get(key)
                if isinstance(value, (int, float)):
                    timestamps.append(float(value))
                    break
        if not timestamps:
            return None
        oldest = min(timestamps)
        return min(oldest, float(fallback_before_ts))

    @staticmethod
    def _should_retry_transient_error(
        *,
        status: str,
        reason: str | None,
        attempt: int,
        remaining_seconds: float,
    ) -> bool:
        return (
            status == "error"
            and (reason or "") in BACKFILL_TRANSIENT_RETRY_REASONS
            and attempt < BACKFILL_TRANSIENT_RETRY_ATTEMPTS
            and remaining_seconds >= BACKFILL_TRANSIENT_RETRY_MIN_REMAINING_SECONDS
        )

    async def _fetch_camera_events(
        self,
        *,
        after_ts: float,
        before_ts: float,
        camera: str | None,
    ) -> list[dict]:
        all_events: list[dict] = []
        cursor_before = float(before_ts)
        pages = 0

        while pages < BACKFILL_EVENTS_MAX_PAGES_PER_CAMERA:
            events = await frigate_client.list_events(
                after=after_ts,
                before=cursor_before,
                label="bird",
                camera=camera,
                has_snapshot=True,
                limit=BACKFILL_EVENTS_PAGE_LIMIT,
            )
            if not events:
                break

            all_events.extend(events)
            pages += 1

            if len(events) < BACKFILL_EVENTS_PAGE_LIMIT:
                break

            next_cursor = self._oldest_event_cursor(events, cursor_before)
            if next_cursor is None:
                log.warning(
                    "Backfill pagination stopped because Frigate events had no usable timestamps",
                    camera=camera,
                    pages=pages,
                )
                break

            next_cursor = max(after_ts, next_cursor - 0.001)
            if next_cursor >= cursor_before:
                log.warning(
                    "Backfill pagination stopped because Frigate cursor did not advance",
                    camera=camera,
                    current_before=cursor_before,
                    next_before=next_cursor,
                    pages=pages,
                )
                break
            if next_cursor <= after_ts:
                break

            cursor_before = next_cursor

        if pages >= BACKFILL_EVENTS_MAX_PAGES_PER_CAMERA:
            log.warning(
                "Backfill pagination hit maximum page budget",
                camera=camera,
                max_pages=BACKFILL_EVENTS_MAX_PAGES_PER_CAMERA,
                page_limit=BACKFILL_EVENTS_PAGE_LIMIT,
            )

        return all_events

    async def fetch_frigate_events(self, after_ts: float, before_ts: float, cameras: list[str] = None) -> list[dict]:
        """
        Fetch bird events from Frigate API for a given time range.
        """
        all_events = []

        camera_list = cameras or settings.frigate.camera or []

        if camera_list:
            for camera in camera_list:
                events = await self._fetch_camera_events(
                    after_ts=after_ts,
                    before_ts=before_ts,
                    camera=camera,
                )
                all_events.extend(events)
        else:
            events = await self._fetch_camera_events(
                after_ts=after_ts,
                before_ts=before_ts,
                camera=None,
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

    async def process_historical_event(self, event: dict) -> tuple[str, str | None]:
        """
        Process a single historical event.
        Returns: ('new'|'skipped'|'error', reason_code)
        """
        frigate_event = event.get('id')
        if not frigate_event:
            return 'error', 'missing_id'

        try:
            # Fetch snapshot from Frigate using centralized client
            snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=95)
            if not snapshot_data:
                error_diagnostics_history.record(
                    source="backfill",
                    component="detections",
                    stage="fetch_snapshot",
                    reason_code="fetch_snapshot_failed",
                    message="Historical event snapshot fetch failed",
                    severity="error",
                    event_id=frigate_event,
                    context={"camera": event.get("camera")},
                )
                return 'error', 'fetch_snapshot_failed'

            # Classify the image (async to use thread pool)
            image = Image.open(BytesIO(snapshot_data))
            results = await self.classifier.classify_async_background(
                image,
                camera_name=event.get("camera"),
            )

            if not results:
                log.debug("No classification results", event_id=frigate_event)
                error_diagnostics_history.record(
                    source="backfill",
                    component="detections",
                    stage="classify_snapshot",
                    reason_code="classification_failed",
                    message="Historical event classification returned no results",
                    severity="error",
                    event_id=frigate_event,
                    context={"camera": event.get("camera")},
                )
                return 'error', 'classification_failed'

            # Capture Frigate metadata (needed for fallback)
            frigate_score = event.get('top_score')
            if frigate_score is None and 'data' in event:
                frigate_score = event['data'].get('top_score')

            sub_label = normalize_sub_label(event.get('sub_label'))

            # Use shared filtering and labeling logic (with Frigate sublabel for fallback)
            top, reason = self.detection_service.filter_and_label(results[0], frigate_event, sub_label, frigate_score)
            if not top:
                if reason == "invalid_score":
                    log.warning("Historical event skipped due to invalid classifier score", event_id=frigate_event)
                return 'skipped', reason
            
            camera_name = event.get('camera', 'unknown')
            start_time = event.get('start_time', datetime.now().timestamp())

            # Use upsert logic to ensure metadata is updated even if event exists
            changed, _ = await self.detection_service.save_detection(
                frigate_event=frigate_event,
                camera=camera_name,
                start_time=start_time,
                classification=top,
                frigate_score=frigate_score,
                sub_label=sub_label
            )

            if not changed:
                log.debug("Event already exists and score not improved, skipped", event_id=frigate_event)
                return 'skipped', 'already_exists'

            log.info("Backfilled detection", event_id=frigate_event, species=top['label'], score=top['score'])
            return 'new', None

        except BackgroundImageClassificationUnavailableError as e:
            reason = str(getattr(e, "reason_code", "") or str(e) or "background_image_unavailable")
            log.warning("Historical event classification unavailable", event_id=frigate_event, reason=reason)
            error_diagnostics_history.record(
                source="backfill",
                component="detections",
                stage="classify_snapshot",
                reason_code=reason,
                message="Historical event classification unavailable",
                severity="error",
                event_id=frigate_event,
                context={"camera": event.get("camera")},
            )
            return "error", reason
        except Exception as e:
            log.error(
                "Error processing historical event",
                event_id=frigate_event,
                error_type=type(e).__name__,
                error=str(e) or repr(e),
            )
            error_diagnostics_history.record(
                source="backfill",
                component="detections",
                stage="process_event",
                reason_code="exception",
                message="Historical event processing failed",
                severity="error",
                event_id=frigate_event,
                context={
                    "error_type": type(e).__name__,
                    "error": str(e) or repr(e),
                },
            )
            return 'error', 'exception'

    async def process_historical_event_with_timeout(
        self,
        event: dict,
        timeout_seconds: float = BACKFILL_EVENT_TIMEOUT_SECONDS,
    ) -> tuple[str, str | None]:
        deadline = asyncio.get_running_loop().time() + max(0.01, float(timeout_seconds))
        attempt = 0
        try:
            while True:
                attempt += 1
                remaining_seconds = deadline - asyncio.get_running_loop().time()
                if remaining_seconds <= 0:
                    raise asyncio.TimeoutError()

                status, reason = await asyncio.wait_for(
                    self.process_historical_event(event),
                    timeout=remaining_seconds,
                )
                remaining_seconds = max(0.0, deadline - asyncio.get_running_loop().time())
                if not self._should_retry_transient_error(
                    status=status,
                    reason=reason,
                    attempt=attempt,
                    remaining_seconds=remaining_seconds,
                ):
                    return status, reason

                backoff_seconds = min(
                    BACKFILL_TRANSIENT_RETRY_BACKOFF_SECONDS,
                    max(0.0, remaining_seconds - BACKFILL_TRANSIENT_RETRY_MIN_REMAINING_SECONDS),
                )
                log.warning(
                    "Retrying historical event after transient classifier failure",
                    event_id=event.get("id"),
                    reason=reason,
                    attempt=attempt + 1,
                    max_attempts=BACKFILL_TRANSIENT_RETRY_ATTEMPTS,
                    remaining_seconds=round(remaining_seconds, 2),
                )
                if backoff_seconds > 0:
                    await asyncio.sleep(backoff_seconds)
        except asyncio.TimeoutError:
            log.error(
                "Historical event processing timed out",
                event_id=event.get("id"),
                timeout_seconds=timeout_seconds
            )
            error_diagnostics_history.record(
                source="backfill",
                component="detections",
                stage="process_event",
                reason_code="timeout",
                message="Historical event processing timed out",
                severity="error",
                event_id=event.get("id"),
                context={"timeout_seconds": timeout_seconds},
            )
            return "error", "timeout"

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
            status, reason = await self.process_historical_event_with_timeout(event)
            if status == 'new':
                result.new_detections += 1
            elif status == 'skipped':
                result.skipped += 1
                if reason:
                    result.skipped_reasons[reason] += 1
            else:
                result.errors += 1
                if reason:
                    result.error_reasons[reason] += 1

        log.info("Backfill complete",
                 processed=result.processed,
                 new=result.new_detections,
                 skipped=result.skipped,
                 errors=result.errors,
                 error_reasons=dict(result.error_reasons))

        return result
