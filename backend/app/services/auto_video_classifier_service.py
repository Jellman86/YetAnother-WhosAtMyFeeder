import asyncio
import contextlib
import os
import random
import tempfile
import structlog
import time
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, Dict, Literal, cast

from PIL import Image

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services import classifier_service as classifier_service_module
from app.services.broadcaster import broadcaster
from app.services.media_cache import media_cache
from app.services.video_classification_waiter import video_classification_waiter
from app.services.error_diagnostics import error_diagnostics_history
from app.services.maintenance_coordinator import maintenance_coordinator
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.routers.proxy import _get_valid_cached_recording_clip_path
from app.utils.tasks import create_background_task
from app.utils.system_stats import get_ram_usage_string
from app.utils.canonical_species import user_facing_species_fields
from app.utils.api_datetime import serialize_api_datetime, utc_naive_now

log = structlog.get_logger()
MAX_PENDING_QUEUE = 1000
MAINTENANCE_VIDEO_STARVATION_RELIEF_SECONDS = 5.0
MAINTENANCE_DEPRIORITIZED_AGE_SECONDS = 15.0
MAINTENANCE_STALLED_AGE_SECONDS = 90.0
MAINTENANCE_REJECT_NEW_WORK_PENDING_THRESHOLD = 25
MAINTENANCE_REJECT_NEW_WORK_AGE_SECONDS = 45.0
MAINTENANCE_STATUS_DIAGNOSTIC_COOLDOWN_SECONDS = 60.0

# ---------------------------------------------------------------------------
# Circuit-breaker failure classification
# ---------------------------------------------------------------------------
# The circuit breaker exists to protect against a broken ML *inference*
# pipeline (timed-out workers, crashed workers, zero-result runs).  It must
# NOT open because Frigate was temporarily unreachable or because a task was
# cancelled during a normal service reset / shutdown.
#
# Errors that originate on the Frigate side (connectivity, HTTP errors,
# timing races) or from task lifecycle events are excluded from the failure
# counter.  Only genuine ML inference failures count toward the threshold.

# Fixed error codes that must never increment the circuit-breaker counter.
_FRIGATE_CONNECTIVITY_ERRORS: frozenset[str] = frozenset({
    # --- Event precheck errors (frigate_client.get_event_with_error) ---
    "event_not_found",      # Frigate 404 race: MQTT end fired before the event was committed to DB
    "event_timeout",        # Frigate API request timed out
    "event_request_error",  # Network error reaching Frigate
    "event_unknown_error",  # Unexpected error during event fetch
    # --- Clip fetch errors (frigate_client.get_clip_with_error) ---
    "clip_not_retained",    # Continuous recordings disabled or retention window expired (expected)
    "clip_not_found",       # Frigate 404 for clip (transient or expected)
    "clip_timeout",         # Clip fetch timed out
    "clip_request_error",   # Network error reaching Frigate
    "clip_unknown_error",   # Unexpected error during clip fetch
    "clip_invalid",         # Frigate returned a stub or non-MP4 body
    "clip_decode_failed",   # Frigate returned bytes that could not be decoded as video
    # --- Task lifecycle (not an inference failure) ---
    "video_cancelled",      # Task was cancelled during reset_state() or service shutdown
})

# Dynamic error-code prefixes also excluded from the circuit-breaker counter.
# These cover the pattern "event_http_<status>" and "clip_http_<status>"
# produced when Frigate returns an unexpected HTTP status code.
_FRIGATE_CONNECTIVITY_ERROR_PREFIXES: tuple[str, ...] = (
    "event_http_",  # e.g. event_http_500, event_http_503
    "clip_http_",   # e.g. clip_http_400, clip_http_502
)
SNAPSHOT_FALLBACK_MAX_ATTEMPTS = 3
SNAPSHOT_FALLBACK_BACKGROUND_IMAGE_ADMISSION_TIMEOUT_SECONDS = 3.0
_VIDEO_TOP_FRAMES_LIMIT = 8
BackgroundImageClassificationUnavailableError = getattr(
    classifier_service_module,
    "BackgroundImageClassificationUnavailableError",
    RuntimeError,
)
get_classifier = classifier_service_module.get_classifier
VideoClassificationWorkerError = classifier_service_module.VideoClassificationWorkerError
JobSource = Literal["live", "maintenance"]


def _empty_breaker_state() -> dict[JobSource, dict[str, object]]:
    return {
        "live": {
            "failure_events": deque(),
            "failure_event_ids": set(),
            "open_until": None,
        },
        "maintenance": {
            "failure_events": deque(),
            "failure_event_ids": set(),
            "open_until": None,
        },
    }


def _empty_timeout_state() -> dict[JobSource, dict[str, object]]:
    return {
        "live": {"count": 0, "last": None},
        "maintenance": {"count": 0, "last": None},
    }

class AutoVideoClassifierService:
    """
    Service to automatically classify video clips from Frigate events.

    This service polls Frigate for clip availability, downloads it,
    runs the temporal ensemble classifier, and saves results to the DB.
    """

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._classifier = get_classifier()
        self._breaker_state = _empty_breaker_state()
        self._timeout_state = _empty_timeout_state()
        self._pending_queue: asyncio.Queue[tuple[str, str, bool, bool, JobSource]] = asyncio.Queue(
            maxsize=MAX_PENDING_QUEUE
        )
        self._pending_ids: set[str] = set()
        self._pending_metadata: dict[str, dict[str, object]] = {}
        self._active_metadata: dict[str, dict[str, object]] = {}
        self._queue_lock = asyncio.Lock()
        self._processor_task: Optional[asyncio.Task] = None
        self._stale_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_mqtt_throttle_log_ts: float = 0.0
        self._maintenance_last_progress_at: float | None = None
        self._last_reported_maintenance_state: str | None = None
        self._last_reported_maintenance_state_at: float | None = None

    @staticmethod
    def _maintenance_holder_id(source: JobSource, event_id: str) -> str:
        return f"{source}:{event_id}"

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
        self._pending_metadata.clear()
        self._active_metadata.clear()
        self._timeout_state = _empty_timeout_state()
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
                item = self._pending_queue.get_nowait()
                self._pending_metadata.pop(str(item[0]), None)
                self._pending_queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._pending_ids.clear()
        self._pending_metadata.clear()
        self._active_metadata.clear()

        # Reset circuit breaker state
        self._reset_all_breakers()

    async def _process_queue_loop(self):
        """Background loop to process queued classification tasks."""
        while self._running:
            try:
                self._cleanup_completed_tasks()

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
                    frigate_event, camera, skip_delay, fallback_to_snapshot, source = await asyncio.wait_for(
                        self._pending_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    if frigate_event in self._active_tasks:
                        self._pending_ids.discard(frigate_event)
                        self._pending_metadata.pop(frigate_event, None)
                        continue

                    if self._is_circuit_open(source):
                        self._pending_queue.put_nowait(
                            (frigate_event, camera, skip_delay, fallback_to_snapshot, source)
                        )
                        await asyncio.sleep(1)
                        continue

                    maintenance_holder_id = None
                    if source == "maintenance":
                        maintenance_holder_id = self._maintenance_holder_id(source, frigate_event)
                        acquired = await maintenance_coordinator.try_acquire(
                            maintenance_holder_id,
                            kind="video_classification",
                        )
                        if not acquired:
                            self._pending_queue.put_nowait(
                                (frigate_event, camera, skip_delay, fallback_to_snapshot, source)
                            )
                            await asyncio.sleep(1)
                            continue

                    # Start task - skip initial delay for queued (historical) tasks
                    task = create_background_task(
                        self._process_event(
                            frigate_event,
                            camera,
                            skip_delay=skip_delay,
                            fallback_to_snapshot=fallback_to_snapshot,
                            source=source,
                        ),
                        name=f"video_classifier:{frigate_event}"
                    )
                    self._active_tasks[frigate_event] = task
                    self._active_metadata[frigate_event] = {
                        "source": source,
                        "started_at": time.monotonic(),
                        "maintenance_holder_id": maintenance_holder_id,
                    }
                    if source == "maintenance":
                        self._maintenance_last_progress_at = time.monotonic()
                    task.add_done_callback(lambda t: self._cleanup_task(frigate_event, t))
                    # Only clear pending dedupe marker after active registration.
                    self._pending_ids.discard(frigate_event)
                    self._pending_metadata.pop(frigate_event, None)

                    log.debug("Started queued video classification",
                              event_id=frigate_event,
                              queue_size=self._pending_queue.qsize())
                except Exception as e:
                    if source == "maintenance":
                        await maintenance_coordinator.release(self._maintenance_holder_id(source, frigate_event))
                    self._pending_ids.discard(frigate_event)
                    self._pending_metadata.pop(frigate_event, None)
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

        oldest_maintenance_pending_age = self._oldest_pending_age_seconds(source="maintenance")
        maintenance_starvation_relief_active = bool(
            live_pressure_active
            and mqtt_level != "critical"
            and isinstance(oldest_maintenance_pending_age, (int, float))
            and oldest_maintenance_pending_age >= MAINTENANCE_VIDEO_STARVATION_RELIEF_SECONDS
        )

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
        # If maintenance work has been starved for a sustained window, allow one
        # queued maintenance slot through unless MQTT pressure is already critical.
        if live_pressure_active and not maintenance_starvation_relief_active:
            effective = 0
        elif maintenance_starvation_relief_active:
            effective = max(1, min(effective, 1))

        throttled = effective < configured
        return {
            "throttled": throttled,
            "throttled_for_mqtt_pressure": mqtt_throttled,
            "throttled_for_live_pressure": live_pressure_active,
            "maintenance_starvation_relief_active": maintenance_starvation_relief_active,
            "configured_max_concurrent": configured,
            "effective_max_concurrent": effective,
            "mqtt_pressure_level": mqtt_level,
            "mqtt_in_flight": in_flight,
            "mqtt_capacity": capacity,
            "mqtt_status": mqtt_status,
            "live_pressure_active": live_pressure_active,
            "live_in_flight": live_in_flight,
            "live_queued": live_queued,
            "oldest_maintenance_pending_age_seconds": oldest_maintenance_pending_age,
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

    def _breaker_bucket(self, source: JobSource) -> dict[str, object]:
        return self._breaker_state[source]

    def _timeout_bucket(self, source: JobSource) -> dict[str, object]:
        return self._timeout_state[source]

    def _reset_all_breakers(self) -> None:
        self._breaker_state = _empty_breaker_state()

    @property
    def _failure_events(self) -> deque[tuple[float, str]]:
        return cast(deque[tuple[float, str]], self._breaker_bucket("live")["failure_events"])

    @_failure_events.setter
    def _failure_events(self, value: deque[tuple[float, str]]) -> None:
        self._breaker_bucket("live")["failure_events"] = value

    @property
    def _failure_event_ids(self) -> set[str]:
        return cast(set[str], self._breaker_bucket("live")["failure_event_ids"])

    @_failure_event_ids.setter
    def _failure_event_ids(self, value: set[str]) -> None:
        self._breaker_bucket("live")["failure_event_ids"] = value

    @property
    def _circuit_open_until(self) -> float | None:
        return cast(float | None, self._breaker_bucket("live")["open_until"])

    @_circuit_open_until.setter
    def _circuit_open_until(self, value: float | None) -> None:
        self._breaker_bucket("live")["open_until"] = value

    def _prune_failures(self, source: JobSource):
        window = settings.classification.video_classification_failure_window_minutes * 60
        now = time.time()
        failure_events = cast(deque[tuple[float, str]], self._breaker_bucket(source)["failure_events"])
        failure_event_ids = cast(set[str], self._breaker_bucket(source)["failure_event_ids"])
        while failure_events and now - failure_events[0][0] > window:
            _, event_id = failure_events.popleft()
            failure_event_ids.discard(event_id)

    def _record_failure(self, event_id: str, error: Optional[str] = None, *, source: JobSource = "live"):
        # Frigate-connectivity and task-lifecycle errors do not count toward the
        # circuit-breaker threshold.  Only genuine ML inference failures do.
        if error is not None:
            if error in _FRIGATE_CONNECTIVITY_ERRORS:
                return
            if any(error.startswith(pfx) for pfx in _FRIGATE_CONNECTIVITY_ERROR_PREFIXES):
                return
        self._prune_failures(source)
        failure_events = cast(deque[tuple[float, str]], self._breaker_bucket(source)["failure_events"])
        failure_event_ids = cast(set[str], self._breaker_bucket(source)["failure_event_ids"])
        if event_id in failure_event_ids:
            return
        now = time.time()
        failure_events.append((now, event_id))
        failure_event_ids.add(event_id)

        threshold = settings.classification.video_classification_failure_threshold
        if len(failure_events) >= threshold:
            cooldown = settings.classification.video_classification_failure_cooldown_minutes * 60
            self._breaker_bucket(source)["open_until"] = now + cooldown
            log.warning("Video classification circuit opened",
                        failures=len(failure_events),
                        source=source,
                        cooldown_minutes=settings.classification.video_classification_failure_cooldown_minutes)
            error_diagnostics_history.record(
                source="video_classifier",
                component="auto_video_classifier",
                reason_code="video_circuit_opened",
                message="Video classification circuit opened after repeated failures",
                severity="error",
                event_id=event_id,
                correlation_key=f"video:circuit_open:{source}",
                worker_pool="video",
                context={
                    "failure_count": len(failure_events),
                    "cooldown_minutes": settings.classification.video_classification_failure_cooldown_minutes,
                    "last_error": error,
                    "source": source,
                },
            )

    def _record_success(self, event_id: str, *, source: JobSource = "live"):
        self._prune_failures(source)
        failure_events = cast(deque[tuple[float, str]], self._breaker_bucket(source)["failure_events"])
        failure_event_ids = cast(set[str], self._breaker_bucket(source)["failure_event_ids"])
        if event_id in failure_event_ids:
            failure_event_ids.discard(event_id)
            self._breaker_bucket(source)["failure_events"] = deque(
                [(ts, eid) for ts, eid in failure_events if eid != event_id]
            )

    def _record_timeout(self, event_id: str, *, source: JobSource = "live", context: Optional[dict] = None) -> None:
        bucket = self._timeout_bucket(source)
        bucket["count"] = int(bucket.get("count") or 0) + 1
        details = {
            "event_id": event_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            details.update(dict(context))
        bucket["last"] = details

    def _is_circuit_open(self, source: JobSource = "live") -> bool:
        open_until = cast(float | None, self._breaker_bucket(source)["open_until"])
        if not open_until:
            return False
        now = time.time()
        if now >= open_until:
            bucket = self._breaker_bucket(source)
            cast(deque[tuple[float, str]], bucket["failure_events"]).clear()
            cast(set[str], bucket["failure_event_ids"]).clear()
            bucket["open_until"] = None
            return False
        return True

    def get_circuit_status(self, source: JobSource = "live") -> dict:
        open_status = self._is_circuit_open(source)
        until = None
        open_until = cast(float | None, self._breaker_bucket(source)["open_until"])
        if open_status and open_until:
            # Always emit UTC so diagnostics tools and the frontend display a
            # consistent timezone regardless of where the container is running.
            until = datetime.fromtimestamp(
                open_until, tz=timezone.utc
            ).isoformat()
        failure_events = cast(deque[tuple[float, str]], self._breaker_bucket(source)["failure_events"])
        return {
            "open": open_status,
            "open_until": until,
            "failure_count": len(failure_events),
            "source": source,
        }

    def reset_circuit(self) -> None:
        """Reset only the circuit breaker state.

        Unlike ``reset_state()``, this does not drain the pending queue or
        cancel active tasks.  It is the right tool for manually recovering
        from a false-positive open circuit (e.g. one caused by a transient
        Frigate outage) without discarding queued work.
        """
        self._reset_all_breakers()
        log.info("Video classification circuit breaker reset manually")

    def get_status(self) -> dict:
        """Get current queue status."""
        self._cleanup_completed_tasks()
        circuit = self.get_circuit_status("live")
        maintenance_circuit = self.get_circuit_status("maintenance")
        live_timeout = self._timeout_bucket("live")
        maintenance_timeout = self._timeout_bucket("maintenance")
        pending = self._pending_queue.qsize()
        configured_max = int(settings.classification.video_classification_max_concurrent or 1)
        throttle_state = self._get_mqtt_throttle_state(configured_max)
        maintenance_summary = self._maintenance_status_summary(throttle_state)
        self._emit_maintenance_status_diagnostic(maintenance_summary)
        active = len(self._active_tasks)
        status = self._queue_status(
            pending=pending,
            active=active,
            circuit_open=bool(circuit["open"] or maintenance_circuit["open"]),
        )
        return {
            "status": status,
            "pending": pending,
            "active": active,
            "circuit_open": circuit["open"],
            "open_until": circuit["open_until"],
            "failure_count": circuit["failure_count"],
            "maintenance_circuit_open": maintenance_circuit["open"],
            "maintenance_open_until": maintenance_circuit["open_until"],
            "maintenance_failure_count": maintenance_circuit["failure_count"],
            "live_timeout_count": int(live_timeout["count"]),
            "maintenance_timeout_count": int(maintenance_timeout["count"]),
            "last_live_timeout": live_timeout["last"],
            "last_maintenance_timeout": maintenance_timeout["last"],
            "pending_capacity": MAX_PENDING_QUEUE,
            "pending_available": max(0, MAX_PENDING_QUEUE - pending),
            "max_concurrent_configured": configured_max,
            "max_concurrent_effective": throttle_state["effective_max_concurrent"],
            "mqtt_pressure_level": throttle_state["mqtt_pressure_level"],
            "throttled_for_mqtt_pressure": throttle_state["throttled_for_mqtt_pressure"],
            "throttled_for_live_pressure": throttle_state["throttled_for_live_pressure"],
            "maintenance_starvation_relief_active": throttle_state["maintenance_starvation_relief_active"],
            "live_pressure_active": throttle_state["live_pressure_active"],
            "live_in_flight": throttle_state["live_in_flight"],
            "live_queued": throttle_state["live_queued"],
            "mqtt_in_flight": throttle_state["mqtt_in_flight"],
            "mqtt_in_flight_capacity": throttle_state["mqtt_capacity"],
            **maintenance_summary,
        }

    @staticmethod
    def _queue_status(*, pending: int, active: int, circuit_open: bool) -> str:
        if circuit_open:
            return "open"
        if active > 0:
            return "processing"
        if pending > 0:
            return "queued"
        return "idle"

    async def queue_classification(
        self,
        frigate_event: str,
        camera: str,
        *,
        skip_delay: bool = True,
        fallback_to_snapshot: bool = False,
        source: JobSource = "maintenance",
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
                    (frigate_event, camera, bool(skip_delay), bool(fallback_to_snapshot), source)
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
            self._pending_metadata[frigate_event] = {
                "source": source,
                "queued_at": time.monotonic(),
            }
            log.debug("Queued video classification", event_id=frigate_event, queue_size=self._pending_queue.qsize())
            return "queued"

    def _cleanup_task(self, frigate_event: str, task: asyncio.Task):
        """Safely cleanup a completed task from the active tasks dict."""
        try:
            self._active_tasks.pop(frigate_event, None)
            self._pending_metadata.pop(frigate_event, None)
            metadata = self._active_metadata.pop(frigate_event, None)
            maintenance_holder_id = None
            if isinstance(metadata, dict) and str(metadata.get("source") or "") == "maintenance":
                self._maintenance_last_progress_at = time.monotonic()
                maintenance_holder_id = str(metadata.get("maintenance_holder_id") or "").strip() or None
            if maintenance_holder_id:
                asyncio.get_running_loop().create_task(
                    maintenance_coordinator.release(maintenance_holder_id)
                )
            if task.cancelled():
                log.debug("Video classification task was cancelled", event_id=frigate_event)
            elif task.exception():
                log.error("Video classification task failed with exception",
                         event_id=frigate_event,
                         error=str(task.exception()))
        except Exception as e:
            log.error("Error during task cleanup", event_id=frigate_event, error=str(e))

    def _oldest_pending_age_seconds(self, *, source: JobSource | None = None) -> float | None:
        now = time.monotonic()
        ages: list[float] = []
        for metadata in self._pending_metadata.values():
            if source is not None and str(metadata.get("source") or "") != source:
                continue
            queued_at = metadata.get("queued_at")
            if isinstance(queued_at, (int, float)):
                ages.append(max(0.0, now - float(queued_at)))
        if not ages:
            return None
        return round(max(ages), 3)

    def _count_active_jobs(self, *, source: JobSource | None = None) -> int:
        count = 0
        for metadata in self._active_metadata.values():
            if source is not None and str(metadata.get("source") or "") != source:
                continue
            count += 1
        return count

    def _maintenance_status_summary(self, throttle_state: dict | None = None) -> dict[str, object]:
        throttle = throttle_state or self._get_mqtt_throttle_state(
            int(settings.classification.video_classification_max_concurrent or 1)
        )
        coordinator_status = maintenance_coordinator.get_status_nowait()
        active_by_kind = coordinator_status.get("active_by_kind") or {}
        pending_maintenance = sum(
            1
            for metadata in self._pending_metadata.values()
            if str(metadata.get("source") or "") == "maintenance"
        )
        active_video_maintenance = self._count_active_jobs(source="maintenance")
        active_external_maintenance = max(
            0,
            int(coordinator_status.get("active_total") or 0) - active_video_maintenance,
        )
        active_maintenance = active_video_maintenance + active_external_maintenance
        oldest_pending_age = throttle.get("oldest_maintenance_pending_age_seconds")
        maintenance_circuit_open = bool(self.get_circuit_status("maintenance")["open"])
        now = time.monotonic()
        seconds_since_progress = (
            round(max(0.0, now - float(self._maintenance_last_progress_at)), 3)
            if isinstance(self._maintenance_last_progress_at, (int, float))
            else None
        )

        state = "idle"
        message = ""
        if maintenance_circuit_open:
            state = "recovering"
            message = "Maintenance video circuit is recovering after repeated failures"
        elif pending_maintenance <= 0 and active_maintenance <= 0:
            state = "idle"
            message = ""
        elif pending_maintenance > 0 and bool(throttle.get("throttled_for_live_pressure")):
            if isinstance(oldest_pending_age, (int, float)) and oldest_pending_age >= MAINTENANCE_STALLED_AGE_SECONDS:
                state = "stalled"
                message = "Maintenance work is stalled while waiting for maintenance classifier capacity"
            elif isinstance(oldest_pending_age, (int, float)) and oldest_pending_age >= MAINTENANCE_DEPRIORITIZED_AGE_SECONDS:
                state = "deprioritized"
                message = "Maintenance work is deprioritized while live detections keep classifier capacity"
            else:
                state = "queued"
                message = "Maintenance work is queued behind live detections"
        elif pending_maintenance > 0:
            state = "queued"
            message = "Maintenance work is queued"
        elif active_maintenance > 0:
            state = "running"
            message = "Maintenance work is running"

        return {
            "pending_maintenance": pending_maintenance,
            "active_maintenance": active_maintenance,
            "active_video_maintenance": active_video_maintenance,
            "active_external_maintenance": active_external_maintenance,
            "maintenance_capacity": int(coordinator_status.get("capacity") or 1),
            "maintenance_available": int(coordinator_status.get("available") or 0),
            "active_maintenance_by_kind": dict(active_by_kind) if isinstance(active_by_kind, dict) else {},
            "oldest_maintenance_pending_age_seconds": oldest_pending_age,
            "maintenance_seconds_since_progress": seconds_since_progress,
            "maintenance_state": state,
            "maintenance_status_message": message,
            "maintenance_circuit_open": maintenance_circuit_open,
        }

    def get_maintenance_guardrail_status(self) -> dict[str, object]:
        throttle_state = self._get_mqtt_throttle_state(int(settings.classification.video_classification_max_concurrent or 1))
        summary = self._maintenance_status_summary(throttle_state)
        oldest_pending_age = summary.get("oldest_maintenance_pending_age_seconds")
        pending_maintenance = int(summary.get("pending_maintenance") or 0)
        state = str(summary.get("maintenance_state") or "idle")
        reject_new_work = bool(
            summary.get("maintenance_circuit_open")
            or state == "stalled"
            or pending_maintenance >= MAINTENANCE_REJECT_NEW_WORK_PENDING_THRESHOLD
            or (
                isinstance(oldest_pending_age, (int, float))
                and oldest_pending_age >= MAINTENANCE_REJECT_NEW_WORK_AGE_SECONDS
            )
        )
        coalesce_analyze_unknowns = bool(
            int(summary.get("pending_maintenance") or 0) > 0
            or int(summary.get("active_maintenance") or 0) > 0
        )
        return {
            **summary,
            "reject_new_work": reject_new_work,
            "coalesce_analyze_unknowns": coalesce_analyze_unknowns,
        }

    def _emit_maintenance_status_diagnostic(self, summary: dict[str, object]) -> None:
        state = str(summary.get("maintenance_state") or "idle")
        if state not in {"deprioritized", "stalled", "recovering"}:
            self._last_reported_maintenance_state = None
            self._last_reported_maintenance_state_at = None
            return
        now = time.monotonic()
        if (
            self._last_reported_maintenance_state == state
            and isinstance(self._last_reported_maintenance_state_at, (int, float))
            and (now - float(self._last_reported_maintenance_state_at)) < MAINTENANCE_STATUS_DIAGNOSTIC_COOLDOWN_SECONDS
        ):
            return

        self._last_reported_maintenance_state = state
        self._last_reported_maintenance_state_at = now
        severity = "warning" if state == "deprioritized" else "error"
        reason_code = f"maintenance_{state}"
        error_diagnostics_history.record(
            source="video_classifier",
            component="auto_video_classifier",
            reason_code=reason_code,
            message=str(summary.get("maintenance_status_message") or "Maintenance work is not making healthy progress"),
            severity=severity,
            correlation_key="maintenance:queue-state",
            worker_pool="video",
            context={
                "pending_maintenance": int(summary.get("pending_maintenance") or 0),
                "active_maintenance": int(summary.get("active_maintenance") or 0),
                "oldest_maintenance_pending_age_seconds": summary.get("oldest_maintenance_pending_age_seconds"),
                "maintenance_seconds_since_progress": summary.get("maintenance_seconds_since_progress"),
            },
        )

    async def trigger_classification(self, frigate_event: str, camera: str):
        """
        Trigger automatic video classification for an event.
        Queue through the same bounded scheduler used by batch analysis.
        """
        if not settings.classification.auto_video_classification:
            return

        if self._is_circuit_open("live"):
            log.warning("Circuit breaker open, skipping auto video classification", event_id=frigate_event)
            self._record_diagnostic(
                frigate_event,
                reason_code="video_circuit_open",
                message="Video classification skipped because the circuit breaker is open",
                severity="warning",
            )
            await self._update_status(frigate_event, 'failed', error="circuit_open", broadcast=True)
            return

        result = await self.queue_classification(frigate_event, camera, skip_delay=False, source="live")
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
        clip_variant: Literal["event", "recording"] = "event",
    ) -> dict[str, object]:
        context: dict[str, object] = {
            "is_cropped": bool(is_cropped),
            "event_id": str(event_id),
            "clip_variant": str(clip_variant or "event"),
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
        source: JobSource = "live",
    ):
        """Main workflow for processing a video clip."""
        log.info(
            "Starting auto video classification",
            event_id=frigate_event,
            camera=camera,
            skip_delay=skip_delay,
            source=source,
        )
        
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
                self._record_failure(frigate_event, event_error, source=source)
                await self._auto_delete_if_missing(frigate_event, event_error)
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            # 2. Prefer a cached recording/full-visit clip when available.
            clip_bytes, clip_error, clip_variant = await self._load_preferred_clip(
                frigate_event,
                skip_delay=skip_delay,
            )
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
                        self._record_success(frigate_event, source=source)
                    else:
                        self._record_failure(frigate_event, snapshot_error, source=source)
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
                self._record_failure(frigate_event, clip_error or "clip_unavailable", source=source)
                await self._auto_delete_if_missing(frigate_event, clip_error or "clip_unavailable")
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            # 3. Save to temp file for processing
            tmp_path = None
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            try:
                # 4. Run classification
                await self._update_status(frigate_event, 'processing', error=None, broadcast=False)

                _video_frame_scores: list[dict] = []

                async def progress_callback(current_frame, total_frames, frame_score, top_label, frame_thumb=None, frame_index=None, clip_total=None, model_name=None, frame_offset_seconds=None):
                    # Accumulate per-frame score data for top-frame persistence
                    if frame_index is not None and frame_score is not None:
                        _video_frame_scores.append({
                            "frame_index": int(frame_index) - 1,
                            "frame_offset_seconds": frame_offset_seconds,
                            "frame_score": float(frame_score),
                            "top_label": top_label,
                            "top_score": float(frame_score),
                        })
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
                        clip_variant=clip_variant,
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
                    timeout_context = {
                        "timeout_seconds": timeout,
                        "source": source,
                        "camera": camera,
                        "clip_bytes": len(clip_bytes),
                        "max_frames": settings.classification.video_classification_frames,
                    }
                    timeout_context.update(self._clip_probe_context(tmp_path))

                    if source == "maintenance" and fallback_to_snapshot:
                        timeout_context["snapshot_fallback_attempted"] = True
                        snapshot_error = await self._classify_from_snapshot(frigate_event, camera)
                        timeout_context["snapshot_fallback_recovered"] = snapshot_error is None
                        if snapshot_error is not None:
                            timeout_context["snapshot_fallback_error"] = snapshot_error
                        self._record_timeout(frigate_event, source=source, context=timeout_context)
                        self._record_diagnostic(
                            frigate_event,
                            reason_code="video_timeout",
                            message="Video classification exceeded the configured timeout",
                            severity="warning" if snapshot_error is None else "error",
                            context=timeout_context,
                        )
                        if snapshot_error is None:
                            self._record_success(frigate_event, source=source)
                        else:
                            self._record_failure(frigate_event, snapshot_error, source=source)
                        return

                    self._record_timeout(frigate_event, source=source, context=timeout_context)
                    self._record_diagnostic(
                        frigate_event,
                        reason_code="video_timeout",
                        message="Video classification exceeded the configured timeout",
                        severity="error",
                        context=timeout_context,
                    )
                    await self._update_status(frigate_event, 'failed', error="video_timeout", broadcast=True)
                    self._record_failure(frigate_event, "video_timeout", source=source)
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
                    self._record_failure(frigate_event, reason_code, source=source)
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })
                    return

                if results:
                    top = results[0]
                    # 5. Save results to DB
                    await self._save_results(frigate_event, top)
                    self._record_success(frigate_event, source=source)

                    # Persist top video-analysis frames for HQ snapshot reuse
                    if _video_frame_scores:
                        await self._persist_video_top_frames(frigate_event, _video_frame_scores, clip_variant)

                    # Generate HQ snapshot after top frames are persisted so the
                    # crop model works on the best-scored frames from this run.
                    if settings.media_cache.high_quality_event_snapshots:
                        try:
                            await high_quality_snapshot_service.replace_from_clip_bytes(
                                frigate_event,
                                clip_bytes,
                                event_data=event_data,
                                clip_variant=clip_variant,
                            )
                        except Exception as e:
                            log.warning(
                                "High-quality snapshot upgrade failed during auto video classification",
                                event_id=frigate_event,
                                error=str(e),
                            )

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
                    self._record_failure(frigate_event, "video_no_results", source=source)
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })

            finally:
                # Always cleanup temp file
                with contextlib.suppress(OSError):
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        except asyncio.CancelledError:
            log.info("Video classification task cancelled", event_id=frigate_event)
            # Clean up temp file if cancellation occurred before the inner finally ran.
            if tmp_path is not None:
                with contextlib.suppress(OSError):
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
            self._record_diagnostic(
                frigate_event,
                reason_code="video_cancelled",
                message="Video classification task was cancelled",
                severity="warning",
            )
            await self._update_status(frigate_event, 'failed', error="video_cancelled", broadcast=True)
            self._record_failure(frigate_event, "video_cancelled", source=source)
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
            self._record_failure(frigate_event, "video_exception", source=source)
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

    def _clip_probe_context(self, clip_path: str) -> dict:
        import cv2

        context: dict = {}
        cap = cv2.VideoCapture(clip_path)
        try:
            if not cap.isOpened():
                return context
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count > 0:
                context["clip_frame_count"] = frame_count
            if fps > 0:
                context["clip_fps"] = round(fps, 3)
            if frame_count > 0 and fps > 0:
                context["clip_duration_seconds"] = round(frame_count / fps, 3)
            return context
        finally:
            cap.release()

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

    async def _load_preferred_clip(
        self,
        frigate_event: str,
        *,
        skip_delay: bool = False,
    ) -> tuple[Optional[bytes], Optional[str], Literal["event", "recording"]]:
        """Prefer a cached recording/full-visit clip when available, otherwise poll the event clip."""
        try:
            recording_cached_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(
                frigate_event,
                "en",
            )
            if recording_cached_path:
                log.info("Using cached recording clip for auto video classification", event_id=frigate_event)
                with open(recording_cached_path, "rb") as handle:
                    clip_bytes = handle.read()
                if clip_bytes and (
                    clip_bytes.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_bytes[:32]
                ) and await self._clip_decodes(clip_bytes):
                    return clip_bytes, None, "recording"
                log.warning(
                    "Cached recording clip was invalid; falling back to Frigate event clip",
                    event_id=frigate_event,
                    cached_path=str(recording_cached_path),
                )
        except Exception as exc:
            log.debug(
                "Failed to resolve cached recording clip for auto video classification",
                event_id=frigate_event,
                error=str(exc),
            )

        clip_bytes, clip_error = await self._wait_for_clip(frigate_event, skip_delay=skip_delay)
        return clip_bytes, clip_error, "event"

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
                        "timestamp": serialize_api_datetime(utc_naive_now())
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
                    public_species = user_facing_species_fields(
                        display_name=det.display_name,
                        category_name=det.category_name,
                        scientific_name=det.scientific_name,
                        common_name=det.common_name,
                        taxa_id=det.taxa_id,
                    )
                    await broadcaster.broadcast({
                        "type": "detection_updated",
                        "data": {
                            "frigate_event": frigate_event,
                            "display_name": public_species["display_name"],
                            "category_name": public_species["category_name"],
                            "score": det.score,
                            "timestamp": serialize_api_datetime(det.detection_time),
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
                            "scientific_name": public_species["scientific_name"],
                            "common_name": public_species["common_name"],
                            "taxa_id": public_species["taxa_id"],
                            "video_classification_score": det.video_classification_score,
                            "video_classification_label": det.video_classification_label,
                            "video_classification_status": det.video_classification_status,
                            "video_classification_error": det.video_classification_error,
                            "video_classification_provider": det.video_classification_provider,
                            "video_classification_backend": det.video_classification_backend,
                            "video_classification_timestamp": serialize_api_datetime(det.video_classification_timestamp)
                        }
                    })

    async def _persist_video_top_frames(
        self,
        frigate_event: str,
        frame_scores: list[dict],
        clip_variant: str,
    ) -> None:
        """Persist top-N video-analysis frames for HQ snapshot reuse."""
        try:
            sorted_frames = sorted(frame_scores, key=lambda f: f["frame_score"], reverse=True)
            top_frames = [
                {**f, "rank": rank, "clip_variant": clip_variant}
                for rank, f in enumerate(sorted_frames[:_VIDEO_TOP_FRAMES_LIMIT], 1)
            ]
            async with get_db() as db:
                await DetectionRepository(db).replace_video_top_frames(frigate_event, top_frames)
        except Exception as e:
            log.warning("Failed to persist video top frames", event_id=frigate_event, error=str(e))

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
                    queue_timeout_seconds=SNAPSHOT_FALLBACK_BACKGROUND_IMAGE_ADMISSION_TIMEOUT_SECONDS,
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
