import asyncio
import os
import random
import tempfile
import structlog
import time
from collections import deque
from datetime import datetime
from io import BytesIO
from typing import Optional, Dict, Literal

from PIL import Image

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services import classifier_service as classifier_service_module
from app.services.broadcaster import broadcaster
from app.services.media_cache import media_cache
from app.services.video_classification_waiter import video_classification_waiter
from app.services.error_diagnostics import error_diagnostics_history
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.utils.tasks import create_background_task
from app.utils.system_stats import get_ram_usage_string

log = structlog.get_logger()
MAX_PENDING_QUEUE = 1000
SNAPSHOT_FALLBACK_MAX_ATTEMPTS = 3
BackgroundImageClassificationUnavailableError = getattr(
    classifier_service_module,
    "BackgroundImageClassificationUnavailableError",
    RuntimeError,
)
get_classifier = classifier_service_module.get_classifier
VideoClassificationWorkerError = classifier_service_module.VideoClassificationWorkerError

class AutoVideoClassifierService:
    """
    Service to automatically classify video clips from Frigate events.

    This service polls Frigate for clip availability, downloads it,
    runs the temporal ensemble classifier, and saves results to the DB.
    """

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._classifier = get_classifier()
        self._failure_events: deque[tuple[float, str]] = deque()
        self._failure_event_ids: set[str] = set()
        self._circuit_open_until: float | None = None
        self._pending_queue: asyncio.Queue[tuple[str, str, bool, bool]] = asyncio.Queue(maxsize=MAX_PENDING_QUEUE)
        self._pending_ids: set[str] = set()
        self._queue_lock = asyncio.Lock()
        self._processor_task: Optional[asyncio.Task] = None
        self._stale_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_mqtt_throttle_log_ts: float = 0.0

    async def start(self):
        """Start the queue processor."""
        if self._running:
            return
        self._running = True
        self._processor_task = create_background_task(self._process_queue_loop(), name="video_classifier_queue")
        self._stale_task = create_background_task(self._stale_watchdog_loop(), name="video_classifier_stale_watchdog")
        log.info("AutoVideoClassifierService started")

    async def stop(self):
        """Stop the queue processor."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        if self._stale_task:
            self._stale_task.cancel()
            try:
                await self._stale_task
            except asyncio.CancelledError:
                pass
        # Cancel all active tasks
        for task in self._active_tasks.values():
            task.cancel()
        self._active_tasks.clear()
        self._pending_ids.clear()
        log.info("AutoVideoClassifierService stopped")

    async def reset_state(self):
        """Cancel active tasks and clear pending queue without stopping the service."""
        for task in self._active_tasks.values():
            task.cancel()
        for task in list(self._active_tasks.values()):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error("Video classifier task failed during reset", error=str(e))
        self._active_tasks.clear()

        # Drain pending queue
        while not self._pending_queue.empty():
            try:
                self._pending_queue.get_nowait()
                self._pending_queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._pending_ids.clear()

        # Reset circuit breaker state
        self._failure_events.clear()
        self._failure_event_ids.clear()
        self._circuit_open_until = None

    async def _process_queue_loop(self):
        """Background loop to process queued classification tasks."""
        while self._running:
            try:
                self._cleanup_completed_tasks()
                # Check constraints
                if self._is_circuit_open():
                    await asyncio.sleep(5)
                    continue

                max_concurrent = int(settings.classification.video_classification_max_concurrent or 1)
                throttle_state = self._get_mqtt_throttle_state(max_concurrent)
                effective_max = throttle_state["effective_max_concurrent"]

                if throttle_state["throttled"]:
                    now = time.time()
                    if now - self._last_mqtt_throttle_log_ts >= 15:
                        self._last_mqtt_throttle_log_ts = now
                        log.info(
                            "Throttling background video classification",
                            throttled_for_mqtt_pressure=throttle_state["throttled_for_mqtt_pressure"],
                            throttled_for_live_pressure=throttle_state["throttled_for_live_pressure"],
                            mqtt_pressure_level=throttle_state["mqtt_pressure_level"],
                            mqtt_in_flight=throttle_state["mqtt_in_flight"],
                            mqtt_capacity=throttle_state["mqtt_capacity"],
                            live_in_flight=throttle_state["live_in_flight"],
                            live_queued=throttle_state["live_queued"],
                            configured_max=max_concurrent,
                            effective_max=effective_max,
                        )

                if effective_max <= 0:
                    await asyncio.sleep(1)
                    continue

                if len(self._active_tasks) >= effective_max:
                    await asyncio.sleep(1)
                    continue

                # Get next task
                try:
                    # Wait for a task or timeout to recheck constraints
                    frigate_event, camera, skip_delay, fallback_to_snapshot = await asyncio.wait_for(
                        self._pending_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    if frigate_event in self._active_tasks:
                        self._pending_ids.discard(frigate_event)
                        continue

                    # Start task - skip initial delay for queued (historical) tasks
                    task = create_background_task(
                        self._process_event(
                            frigate_event,
                            camera,
                            skip_delay=skip_delay,
                            fallback_to_snapshot=fallback_to_snapshot,
                        ),
                        name=f"video_classifier:{frigate_event}"
                    )
                    self._active_tasks[frigate_event] = task
                    task.add_done_callback(lambda t: self._cleanup_task(frigate_event, t))
                    # Only clear pending dedupe marker after active registration.
                    self._pending_ids.discard(frigate_event)

                    log.debug("Started queued video classification",
                              event_id=frigate_event,
                              queue_size=self._pending_queue.qsize())
                except Exception as e:
                    self._pending_ids.discard(frigate_event)
                    log.error(
                        "Failed to start queued video classification",
                        event_id=frigate_event,
                        error=str(e),
                        exc_info=True,
                    )
                finally:
                    self._pending_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in video classification queue loop", error=str(e))
                await asyncio.sleep(5)

    def _get_mqtt_throttle_state(self, configured_max: int) -> dict:
        """Reduce background concurrency when MQTT ingest pressure or Live Classifier pressure rises."""
        configured = max(1, int(configured_max or 1))
        
        # 1. Check MQTT Pressure
        try:
            from app.services.mqtt_service import mqtt_service
            mqtt_status = mqtt_service.get_status()
            mqtt_level = str(mqtt_status.get("pressure_level") or "normal")
            in_flight = int(mqtt_status.get("in_flight") or 0)
            capacity = int(mqtt_status.get("in_flight_capacity") or 0)
        except Exception:
            mqtt_status = {}
            mqtt_level = "unknown"
            in_flight = 0
            capacity = 0

        # 2. Check Live Classifier Pressure
        live_in_flight = 0
        live_queued = 0
        live_pressure_active = False
        try:
            admission_status = self._classifier.get_admission_status()
            live_status = admission_status.get("live") or {}
            live_in_flight = int(live_status.get("running") or 0)
            live_queued = int(live_status.get("queued") or 0)
            # Drain existing video work but stop starting new work whenever any live work exists.
            live_pressure_active = live_in_flight > 0 or live_queued > 0
        except Exception:
            live_in_flight = 0
            live_queued = 0
            live_pressure_active = False

        effective = configured

        # Priority 1: MQTT ingest pressure (system-wide safety)
        if mqtt_level == "critical":
            effective = 0
        elif mqtt_level == "high":
            effective = min(effective, 1)
        elif mqtt_level == "elevated":
            effective = min(effective, max(1, configured // 2))

        mqtt_throttled = effective < configured

        # Priority 2: Live event pressure (UI responsiveness)
        # Drain in-flight video work, but do not start new video jobs while live work exists.
        if live_pressure_active:
            effective = 0

        throttled = effective < configured
        return {
            "throttled": throttled,
            "throttled_for_mqtt_pressure": mqtt_throttled,
            "throttled_for_live_pressure": live_pressure_active,
            "configured_max_concurrent": configured,
            "effective_max_concurrent": effective,
            "mqtt_pressure_level": mqtt_level,
            "mqtt_in_flight": in_flight,
            "mqtt_capacity": capacity,
            "mqtt_status": mqtt_status,
            "live_pressure_active": live_pressure_active,
            "live_in_flight": live_in_flight,
            "live_queued": live_queued,
        }

    async def _stale_watchdog_loop(self):
        """Periodically mark stale pending/processing detections as failed."""
        while self._running:
            try:
                max_age = settings.classification.video_classification_stale_minutes
                async with get_db() as db:
                    repo = DetectionRepository(db)
                    count = await repo.reset_stale_video_statuses(max_age)
                if count:
                    log.warning("Reset stale video classifications", count=count, max_age_minutes=max_age)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in stale watchdog loop", error=str(e))
            await asyncio.sleep(60)

    def _prune_failures(self):
        window = settings.classification.video_classification_failure_window_minutes * 60
        now = time.time()
        while self._failure_events and now - self._failure_events[0][0] > window:
            _, event_id = self._failure_events.popleft()
            self._failure_event_ids.discard(event_id)

    def _record_failure(self, event_id: str, error: Optional[str] = None):
        if error == "clip_not_retained":
            return
        self._prune_failures()
        if event_id in self._failure_event_ids:
            return
        now = time.time()
        self._failure_events.append((now, event_id))
        self._failure_event_ids.add(event_id)

        threshold = settings.classification.video_classification_failure_threshold
        if len(self._failure_events) >= threshold:
            cooldown = settings.classification.video_classification_failure_cooldown_minutes * 60
            self._circuit_open_until = now + cooldown
            log.warning("Video classification circuit opened",
                        failures=len(self._failure_events),
                        cooldown_minutes=settings.classification.video_classification_failure_cooldown_minutes)
            error_diagnostics_history.record(
                source="video_classifier",
                component="auto_video_classifier",
                reason_code="video_circuit_opened",
                message="Video classification circuit opened after repeated failures",
                severity="error",
                event_id=event_id,
                correlation_key="video:circuit_open",
                worker_pool="video",
                context={
                    "failure_count": len(self._failure_events),
                    "cooldown_minutes": settings.classification.video_classification_failure_cooldown_minutes,
                    "last_error": error,
                },
            )

    def _record_success(self, event_id: str):
        self._prune_failures()
        if event_id in self._failure_event_ids:
            self._failure_event_ids.discard(event_id)
            self._failure_events = deque([(ts, eid) for ts, eid in self._failure_events if eid != event_id])

    def _is_circuit_open(self) -> bool:
        if not self._circuit_open_until:
            return False
        now = time.time()
        if now >= self._circuit_open_until:
            self._circuit_open_until = None
            self._failure_events.clear()
            self._failure_event_ids.clear()
            return False
        return True

    def get_circuit_status(self) -> dict:
        open_status = self._is_circuit_open()
        until = None
        if open_status and self._circuit_open_until:
            until = datetime.fromtimestamp(self._circuit_open_until).isoformat()
        return {
            "open": open_status,
            "open_until": until,
            "failure_count": len(self._failure_events)
        }

    def get_status(self) -> dict:
        """Get current queue status."""
        self._cleanup_completed_tasks()
        circuit = self.get_circuit_status()
        pending = self._pending_queue.qsize()
        configured_max = int(settings.classification.video_classification_max_concurrent or 1)
        throttle_state = self._get_mqtt_throttle_state(configured_max)
        return {
            "pending": pending,
            "active": len(self._active_tasks),
            "circuit_open": circuit["open"],
            "open_until": circuit["open_until"],
            "failure_count": circuit["failure_count"],
            "pending_capacity": MAX_PENDING_QUEUE,
            "pending_available": max(0, MAX_PENDING_QUEUE - pending),
            "max_concurrent_configured": configured_max,
            "max_concurrent_effective": throttle_state["effective_max_concurrent"],
            "mqtt_pressure_level": throttle_state["mqtt_pressure_level"],
            "throttled_for_mqtt_pressure": throttle_state["throttled_for_mqtt_pressure"],
            "throttled_for_live_pressure": throttle_state["throttled_for_live_pressure"],
            "live_pressure_active": throttle_state["live_pressure_active"],
            "live_in_flight": throttle_state["live_in_flight"],
            "live_queued": throttle_state["live_queued"],
            "mqtt_in_flight": throttle_state["mqtt_in_flight"],
            "mqtt_in_flight_capacity": throttle_state["mqtt_capacity"],
        }

    async def queue_classification(
        self,
        frigate_event: str,
        camera: str,
        *,
        skip_delay: bool = True,
        fallback_to_snapshot: bool = False,
    ) -> Literal["queued", "duplicate", "full"]:
        """
        Queue a video classification task.
        Use this for bulk operations or retries.
        """
        async with self._queue_lock:
            self._cleanup_completed_tasks()
            if frigate_event in self._active_tasks or frigate_event in self._pending_ids:
                log.debug("Video classification already queued/active; skipping duplicate", event_id=frigate_event)
                return "duplicate"
            try:
                self._pending_queue.put_nowait(
                    (frigate_event, camera, bool(skip_delay), bool(fallback_to_snapshot))
                )
            except asyncio.QueueFull:
                log.warning(
                    "Video classification queue full; dropping task",
                    event_id=frigate_event,
                    queue_size=self._pending_queue.qsize(),
                    max_pending=MAX_PENDING_QUEUE
                )
                return "full"
            self._pending_ids.add(frigate_event)
            log.debug("Queued video classification", event_id=frigate_event, queue_size=self._pending_queue.qsize())
            return "queued"

    def _cleanup_task(self, frigate_event: str, task: asyncio.Task):
        """Safely cleanup a completed task from the active tasks dict."""
        try:
            self._active_tasks.pop(frigate_event, None)
            if task.cancelled():
                log.debug("Video classification task was cancelled", event_id=frigate_event)
            elif task.exception():
                log.error("Video classification task failed with exception",
                         event_id=frigate_event,
                         error=str(task.exception()))
        except Exception as e:
            log.error("Error during task cleanup", event_id=frigate_event, error=str(e))

    async def trigger_classification(self, frigate_event: str, camera: str):
        """
        Trigger automatic video classification for an event.
        Queue through the same bounded scheduler used by batch analysis.
        """
        if not settings.classification.auto_video_classification:
            return

        if self._is_circuit_open():
            log.warning("Circuit breaker open, skipping auto video classification", event_id=frigate_event)
            self._record_diagnostic(
                frigate_event,
                reason_code="video_circuit_open",
                message="Video classification skipped because the circuit breaker is open",
                severity="warning",
            )
            await self._update_status(frigate_event, 'failed', error="circuit_open", broadcast=True)
            return

        result = await self.queue_classification(frigate_event, camera, skip_delay=False)
        if result == "duplicate":
            log.debug("Video classification already queued/active; skipping duplicate", event_id=frigate_event)
        elif result == "full":
            log.warning(
                "Video classification queue full for auto trigger; dropping task",
                event_id=frigate_event,
                queue_size=self._pending_queue.qsize(),
                max_pending=MAX_PENDING_QUEUE
            )
            self._record_diagnostic(
                frigate_event,
                reason_code="video_queue_full",
                message="Video classification queue was full and the task was dropped",
                severity="warning",
                context={"queue_size": self._pending_queue.qsize(), "max_pending": MAX_PENDING_QUEUE},
            )

    def _cleanup_completed_tasks(self):
        """Remove all completed/failed tasks from the active tasks dict."""
        completed = [event_id for event_id, task in self._active_tasks.items() if task.done()]
        for event_id in completed:
            self._active_tasks.pop(event_id, None)
        if completed:
            log.debug("Cleaned up completed tasks", count=len(completed))

    def _build_classification_input_context(
        self,
        *,
        event_id: str,
        event_data: dict | None,
        is_cropped: bool,
    ) -> dict[str, object]:
        context: dict[str, object] = {
            "is_cropped": bool(is_cropped),
            "event_id": str(event_id),
        }
        payload = dict((event_data or {}).get("data") or {})
        frigate_box = payload.get("box")
        frigate_region = payload.get("region")
        if isinstance(frigate_box, (list, tuple)) and len(frigate_box) == 4:
            context["frigate_box"] = list(frigate_box)
        if isinstance(frigate_region, (list, tuple)) and len(frigate_region) == 4:
            context["frigate_region"] = list(frigate_region)
        return context

    async def _process_event(
        self,
        frigate_event: str,
        camera: str,
        skip_delay: bool = False,
        fallback_to_snapshot: bool = False,
    ):
        """Main workflow for processing a video clip."""
        log.info("Starting auto video classification", event_id=frigate_event, camera=camera, skip_delay=skip_delay)
        
        try:
            # 1. Update status in DB to 'pending'
            await self._update_status(frigate_event, 'pending', error=None, broadcast=False)

            # Broadcast start
            await broadcaster.broadcast({
                "type": "reclassification_started",
                "data": {
                    "event_id": frigate_event,
                    "strategy": "auto_video"
                }
            })

            # Retry precheck on event_not_found to handle the Frigate race condition
            # where the MQTT `end` event fires before the event is queryable via API.
            # Only retry for 404 (transient); fail fast on timeouts, 5xx, etc.
            _PRECHECK_RETRIES = 3
            _PRECHECK_RETRY_DELAY = 2.0
            event_data, event_error = None, None
            _precheck_attempts = 0
            for _attempt in range(_PRECHECK_RETRIES + 1):
                _precheck_attempts = _attempt + 1
                event_data, event_error = await frigate_client.get_event_with_error(frigate_event, timeout=8.0)
                if not event_error or event_error != "event_not_found":
                    break
                if _attempt < _PRECHECK_RETRIES:
                    log.info(
                        "Frigate event not yet available, retrying precheck",
                        event_id=frigate_event,
                        attempt=_attempt + 1,
                        max_attempts=_PRECHECK_RETRIES,
                        delay=_PRECHECK_RETRY_DELAY,
                    )
                    await asyncio.sleep(_PRECHECK_RETRY_DELAY)

            if event_error:
                log.warning(
                    "Frigate event precheck failed",
                    event_id=frigate_event,
                    error=event_error,
                    attempts=_precheck_attempts,
                )
                self._record_diagnostic(
                    frigate_event,
                    reason_code=event_error,
                    message="Frigate event precheck failed during video classification",
                    severity="warning",
                    context={"error": event_error, "attempts": _precheck_attempts},
                )
                await self._update_status(frigate_event, 'failed', error=event_error, broadcast=True)
                self._record_failure(frigate_event)
                await self._auto_delete_if_missing(frigate_event, event_error)
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            # 2. Wait for clip availability
            clip_bytes, clip_error = await self._wait_for_clip(frigate_event, skip_delay=skip_delay)
            if not clip_bytes:
                if clip_error == "clip_not_retained" and fallback_to_snapshot:
                    log.info(
                        "Falling back to snapshot classification for missing retained clip",
                        event_id=frigate_event,
                    )
                    # Small random jitter before the first snapshot admission
                    # attempt.  During bulk backfill runs many workers hit
                    # "clip not retained" simultaneously; without jitter they
                    # all race the single background-image admission slot at the
                    # same instant, generating a burst of admission timeouts.
                    await asyncio.sleep(random.uniform(0.0, 0.5))
                    snapshot_error = await self._classify_from_snapshot(frigate_event, camera)
                    if snapshot_error is None:
                        self._record_success(frigate_event)
                    else:
                        self._record_failure(frigate_event, snapshot_error)
                    return
                log.warning("Clip not available after retries", event_id=frigate_event)
                self._record_diagnostic(
                    frigate_event,
                    reason_code=clip_error or "clip_unavailable",
                    message="Video clip was not available for classification",
                    severity="warning",
                    context={"error": clip_error or "clip_unavailable"},
                )
                await self._update_status(frigate_event, 'failed', error=clip_error or "clip_unavailable", broadcast=True)
                self._record_failure(frigate_event, clip_error or "clip_unavailable")
                await self._auto_delete_if_missing(frigate_event, clip_error or "clip_unavailable")
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            if settings.media_cache.high_quality_event_snapshots:
                try:
                    await high_quality_snapshot_service.replace_from_clip_bytes(frigate_event, clip_bytes)
                except Exception as e:
                    log.warning(
                        "High-quality snapshot upgrade failed during auto video classification",
                        event_id=frigate_event,
                        error=str(e),
                    )

            # 3. Save to temp file for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            try:
                # 4. Run classification
                await self._update_status(frigate_event, 'processing', error=None, broadcast=False)
                
                async def progress_callback(current_frame, total_frames, frame_score, top_label, frame_thumb=None, frame_index=None, clip_total=None, model_name=None):
                    # Broadcast progress via SSE
                    await broadcaster.broadcast({
                        "type": "reclassification_progress",
                        "data": {
                            "event_id": frigate_event,
                            "current_frame": current_frame,
                            "total_frames": total_frames,
                            "frame_score": frame_score,
                            "top_label": top_label,
                            "frame_thumb": frame_thumb,
                            "frame_index": frame_index,
                            "clip_total": clip_total,
                            "model_name": model_name,
                            "ram_usage": get_ram_usage_string()
                        }
                    })

                timeout = settings.classification.video_classification_timeout_seconds
                try:
                    input_context = self._build_classification_input_context(
                        event_id=frigate_event,
                        event_data=event_data,
                        is_cropped=False,
                    )
                    results = await asyncio.wait_for(
                        self._classifier.classify_video_async(
                            tmp_path,
                            max_frames=settings.classification.video_classification_frames,
                            progress_callback=progress_callback,
                            camera_name=camera,
                            input_context=input_context,
                            propagate_worker_failure=True,
                        ),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    log.warning("Video classification timed out", event_id=frigate_event, timeout_seconds=timeout)
                    self._record_diagnostic(
                        frigate_event,
                        reason_code="video_timeout",
                        message="Video classification exceeded the configured timeout",
                        severity="error",
                        context={"timeout_seconds": timeout},
                    )
                    await self._update_status(frigate_event, 'failed', error="video_timeout", broadcast=True)
                    self._record_failure(frigate_event, "video_timeout")
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })
                    return
                except VideoClassificationWorkerError as exc:
                    reason_code = exc.reason_code
                    self._record_diagnostic(
                        frigate_event,
                        reason_code=reason_code,
                        message="Video classification worker failed before producing results",
                        severity="error",
                        context={"error": reason_code},
                    )
                    await self._update_status(frigate_event, 'failed', error=reason_code, broadcast=True)
                    self._record_failure(frigate_event, reason_code)
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })
                    return

                if results:
                    top = results[0]
                    # 5. Save results to DB
                    await self._save_results(frigate_event, top)
                    self._record_success(frigate_event)
                    
                    # Broadcast completion
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": {
                            "event_id": frigate_event,
                            "results": results
                        }
                    })

                    log.info("Auto video classification completed", 
                             event_id=frigate_event, 
                             label=top['label'], 
                             score=top['score'])
                else:
                    log.warning("Video classification returned no results", event_id=frigate_event)
                    self._record_diagnostic(
                        frigate_event,
                        reason_code="video_no_results",
                        message="Video classification completed without any candidate results",
                        severity="warning",
                    )
                    await self._update_status(frigate_event, 'failed', error="video_no_results", broadcast=True)
                    self._record_failure(frigate_event, "video_no_results")
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })

            finally:
                # Always cleanup temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except asyncio.CancelledError:
            log.info("Video classification task cancelled", event_id=frigate_event)
            self._record_diagnostic(
                frigate_event,
                reason_code="video_cancelled",
                message="Video classification task was cancelled",
                severity="warning",
            )
            await self._update_status(frigate_event, 'failed', error="video_cancelled", broadcast=True)
            self._record_failure(frigate_event, "video_cancelled")
            raise
        except Exception as e:
            log.error(
                "Video classification failed",
                event_id=frigate_event,
                error=str(e),
                error_type=type(e).__name__,
                error_repr=repr(e),
            )
            self._record_diagnostic(
                frigate_event,
                reason_code="video_exception",
                message="Video classification failed with an unexpected exception",
                severity="error",
                context={"error": str(e), "error_type": type(e).__name__, "error_repr": repr(e)},
            )
            await self._update_status(frigate_event, 'failed', error="video_exception", broadcast=True)
            self._record_failure(frigate_event, "video_exception")
            await self._auto_delete_if_missing(frigate_event, "video_exception")
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": { "event_id": frigate_event, "results": [] }
            })

    def _record_diagnostic(
        self,
        frigate_event: str,
        *,
        reason_code: str,
        message: str,
        severity: Literal["warning", "error", "critical"] = "warning",
        context: Optional[dict] = None,
    ) -> None:
        merged_context = self._classifier_runtime_context()
        if context:
            merged_context.update(context)
        error_diagnostics_history.record(
            source="video_classifier",
            component="auto_video_classifier",
            reason_code=reason_code,
            message=message,
            severity=severity,
            event_id=frigate_event,
            correlation_key=f"video:{frigate_event}",
            worker_pool="video",
            context=merged_context or None,
        )

    def _classifier_runtime_context(self) -> dict:
        status_fn = getattr(self._classifier, "get_status", None)
        if not callable(status_fn):
            return {}
        try:
            status = status_fn() or {}
        except Exception:
            return {}
        if not isinstance(status, dict):
            return {}
        context: dict = {}
        for key in ("inference_backend", "active_provider", "selected_provider"):
            value = status.get(key)
            if value is not None:
                context[key] = value
        recovery = status.get("last_runtime_recovery")
        if isinstance(recovery, dict):
            context["last_runtime_recovery"] = dict(recovery)
        return context

    async def _wait_for_clip(self, frigate_event: str, skip_delay: bool = False) -> tuple[Optional[bytes], Optional[str]]:
        """Poll Frigate for clip availability with retries."""
        # Initial delay to allow Frigate to finalize the clip
        if not skip_delay:
            await asyncio.sleep(settings.classification.video_classification_delay)

        max_retries = settings.classification.video_classification_max_retries
        retry_interval = settings.classification.video_classification_retry_interval

        last_error: Optional[str] = None
        for attempt in range(max_retries + 1):
            log.debug("Polling for clip", event_id=frigate_event, attempt=attempt)
            clip_bytes, error = await frigate_client.get_clip_with_error(frigate_event, timeout=10.0)
            
            if clip_bytes and len(clip_bytes) > 0:
                # Basic sanity check: MP4 header
                if clip_bytes.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_bytes[:32]:
                    if await self._clip_decodes(clip_bytes):
                        return clip_bytes, None
                    last_error = "clip_decode_failed"
                else:
                    last_error = "clip_invalid"
            else:
                last_error = error or "clip_unavailable"

            if last_error == "clip_not_retained":
                break
            
            if attempt < max_retries:
                # Exponential backoff: 1x, 2x, 4x...
                wait_time = retry_interval * (2 ** attempt)
                log.debug(f"Clip not ready, waiting {wait_time}s", event_id=frigate_event)
                await asyncio.sleep(wait_time)

        return None, last_error

    async def _clip_decodes(self, clip_bytes: bytes) -> bool:
        """Ensure clip bytes decode into at least one frame."""
        import cv2

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                cap.release()
                return False
            ok, _frame = cap.read()
            cap.release()
            return ok
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _auto_delete_if_missing(self, frigate_event: str, error: str):
        """Auto-delete detection when clip/event is missing (if enabled)."""
        if not settings.maintenance.auto_delete_missing_clips:
            return

        missing_errors = {
            "event_not_found",
            "clip_unavailable",
            "clip_not_retained",
            "clip_invalid",
            "clip_decode_failed",
            "video_exception",
        }
        if error not in missing_errors:
            return

        try:
            await media_cache.delete_cached_media(frigate_event)
            async with get_db() as db:
                repo = DetectionRepository(db)
                deleted = await repo.delete_by_frigate_event(frigate_event)
            if deleted:
                await broadcaster.broadcast({
                    "type": "detection_deleted",
                    "data": {
                        "frigate_event": frigate_event,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
                log.info("Auto-deleted detection due to missing clip/event",
                         event_id=frigate_event, error=error)
        except Exception as e:
            log.error("Failed to auto-delete missing clip detection",
                      event_id=frigate_event, error=str(e))

    async def _update_status(self, frigate_event: str, status: str, error: Optional[str] = None, broadcast: bool = False):
        """Update video classification status in DB."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.update_video_status(frigate_event, status, error=error)
            await video_classification_waiter.publish(
                frigate_event,
                status,
                error=error
            )
            if broadcast:
                det = await repo.get_by_frigate_event(frigate_event)
                if det:
                    await broadcaster.broadcast({
                        "type": "detection_updated",
                        "data": {
                            "frigate_event": frigate_event,
                            "display_name": det.display_name,
                            "score": det.score,
                            "timestamp": det.detection_time.isoformat(),
                            "camera": det.camera_name,
                            "is_hidden": det.is_hidden,
                            "is_favorite": det.is_favorite,
                            "frigate_score": det.frigate_score,
                            "sub_label": det.sub_label,
                            "manual_tagged": det.manual_tagged,
                            "audio_confirmed": det.audio_confirmed,
                            "audio_species": det.audio_species,
                            "audio_score": det.audio_score,
                            "temperature": det.temperature,
                            "weather_condition": det.weather_condition,
                            "weather_cloud_cover": det.weather_cloud_cover,
                            "weather_wind_speed": det.weather_wind_speed,
                            "weather_wind_direction": det.weather_wind_direction,
                            "weather_precipitation": det.weather_precipitation,
                            "weather_rain": det.weather_rain,
                            "weather_snowfall": det.weather_snowfall,
                            "scientific_name": det.scientific_name,
                            "common_name": det.common_name,
                            "taxa_id": det.taxa_id,
                            "video_classification_score": det.video_classification_score,
                            "video_classification_label": det.video_classification_label,
                            "video_classification_status": det.video_classification_status,
                            "video_classification_error": det.video_classification_error,
                            "video_classification_provider": det.video_classification_provider,
                            "video_classification_backend": det.video_classification_backend,
                            "video_classification_timestamp": det.video_classification_timestamp.isoformat() if det.video_classification_timestamp else None
                        }
                    })

    async def _save_results(self, frigate_event: str, result: dict):
        """Save final results via DetectionService to handle intelligent overrides."""
        from app.services.detection_service import DetectionService
        svc = DetectionService(self._classifier)
        
        await svc.apply_video_result(
            frigate_event=frigate_event,
            video_label=result['label'],
            video_score=result['score'],
            video_index=result['index'],
            video_provider=result.get("inference_provider"),
            video_backend=result.get("inference_backend"),
            video_model_id=result.get("model_id"),
        )
        await video_classification_waiter.publish(
            frigate_event,
            "completed",
            label=result.get("label"),
            score=result.get("score"),
            error=None
        )
        # _record_success is already called on completion in _process_event.

    async def _classify_from_snapshot(self, frigate_event: str, camera: str) -> str | None:
        """Fallback path for queued user-initiated analysis when Frigate clips are no longer retained."""
        snapshot_data = await frigate_client.get_snapshot(frigate_event, crop=True, quality=95)
        if not snapshot_data:
            await self._update_status(frigate_event, 'failed', error="snapshot_fetch_failed", broadcast=True)
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": {"event_id": frigate_event, "results": []}
            })
            return "snapshot_fetch_failed"

        await self._update_status(frigate_event, 'processing', error=None, broadcast=False)
        image = Image.open(BytesIO(snapshot_data))
        results: list[dict] = []
        input_context = {"is_cropped": True, "event_id": frigate_event}
        last_unavailable_error: str | None = None
        for attempt in range(1, SNAPSHOT_FALLBACK_MAX_ATTEMPTS + 1):
            try:
                results = await self._classifier.classify_async_background(
                    image,
                    camera_name=camera,
                    input_context=input_context,
                )
                last_unavailable_error = None
                break
            except BackgroundImageClassificationUnavailableError as exc:
                last_unavailable_error = str(exc) or "background_image_unavailable"
                if attempt >= SNAPSHOT_FALLBACK_MAX_ATTEMPTS:
                    break
                backoff_seconds = min(0.5 * attempt, 1.5)
                log.info(
                    "Snapshot fallback classification delayed by background image pressure; retrying",
                    event_id=frigate_event,
                    attempt=attempt,
                    max_attempts=SNAPSHOT_FALLBACK_MAX_ATTEMPTS,
                    retry_in_seconds=backoff_seconds,
                    error=last_unavailable_error,
                )
                await asyncio.sleep(backoff_seconds)

        if last_unavailable_error is not None:
            self._record_diagnostic(
                frigate_event,
                reason_code=last_unavailable_error,
                message="Snapshot fallback classification could not acquire background image capacity",
                severity="warning",
                context={"attempts": SNAPSHOT_FALLBACK_MAX_ATTEMPTS},
            )
            await self._update_status(frigate_event, 'failed', error=last_unavailable_error, broadcast=True)
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": {"event_id": frigate_event, "results": []}
            })
            return last_unavailable_error

        if not results:
            await self._update_status(frigate_event, 'failed', error="snapshot_no_results", broadcast=True)
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": {"event_id": frigate_event, "results": []}
            })
            return "snapshot_no_results"

        top = results[0]
        await self._save_results(frigate_event, top)
        await broadcaster.broadcast({
            "type": "reclassification_completed",
            "data": {"event_id": frigate_event, "results": results}
        })
        log.info(
            "Snapshot fallback classification completed",
            event_id=frigate_event,
            label=top['label'],
            score=top['score'],
        )
        return None

# Global singleton
auto_video_classifier = AutoVideoClassifierService()
