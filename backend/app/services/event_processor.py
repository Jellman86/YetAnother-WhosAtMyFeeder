import json
import asyncio
import time
import os
import structlog
from collections import Counter, deque
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image
from typing import Optional, Dict, Any, Tuple
from types import SimpleNamespace

from app.config import settings
from app.services.classification_admission import ClassificationLeaseExpiredError
from app.services.classifier_service import ClassifierService, LiveImageClassificationOverloadedError
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.media_cache import media_cache
from app.services.frigate_client import frigate_client
from app.services.detection_service import DetectionService
from app.services.audio.audio_service import audio_service
from app.services.weather_service import weather_service
from app.services.notification_orchestrator import NotificationOrchestrator
from app.services.notification_dispatcher import notification_dispatcher
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.error_diagnostics import error_diagnostics_history
from app.utils.frigate import normalize_sub_label
# Backward-compat for tests that patch event_processor.notification_service
from app.services.notification_service import notification_service  # noqa: F401
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

log = structlog.get_logger()
FALSE_POSITIVE_TOMBSTONE_TTL_SECONDS = 600.0
EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS = max(
    1.0, float(os.getenv("EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS", "30"))
)
EVENT_STAGE_TIMEOUT_CONTEXT_SECONDS = max(
    0.5, float(os.getenv("EVENT_STAGE_TIMEOUT_CONTEXT_SECONDS", "6"))
)
EVENT_STAGE_TIMEOUT_AUDIO_CORRELATE_SECONDS = max(
    0.5, float(os.getenv("EVENT_STAGE_TIMEOUT_AUDIO_CORRELATE_SECONDS", "4"))
)
EVENT_STAGE_TIMEOUT_SAVE_AND_NOTIFY_SECONDS = max(
    1.0, float(os.getenv("EVENT_STAGE_TIMEOUT_SAVE_AND_NOTIFY_SECONDS", "6"))
)
EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS = max(
    0.25, float(os.getenv("EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS", "2"))
)
EVENT_PIPELINE_RECOVERY_WINDOW_SECONDS = max(
    1.0, float(os.getenv("EVENT_PIPELINE_RECOVERY_WINDOW_SECONDS", "300"))
)
LIVE_EVENT_STALE_SECONDS = max(
    1.0, float(os.getenv("LIVE_EVENT_STALE_SECONDS", "45"))
)
_CLASSIFY_SNAPSHOT_OVERLOADED = object()
_CLASSIFY_SNAPSHOT_TIMED_OUT = object()


class EventData:
    """Data class to hold parsed event information."""

    def __init__(self, data: Dict[str, Any]):
        self.type: str = data.get('type')
        after = data.get('after', {})
        self.frigate_event: str = after.get('id', 'unknown')
        self.camera: str = after.get('camera')
        self.label: str = after.get('label')
        self.start_time_ts: float = after.get('start_time', 0.0)
        self.sub_label: Optional[str] = normalize_sub_label(after.get('sub_label'))
        self.frigate_score: Optional[float] = after.get('top_score')
        self.is_false_positive: bool = after.get('false_positive', False)
        
        if self.frigate_score is None and 'data' in after:
            self.frigate_score = after['data'].get('top_score')
        # Create timezone-aware datetime (Frigate timestamps are in UTC)
        self.detection_dt: datetime = datetime.fromtimestamp(self.start_time_ts, tz=timezone.utc)


class EventProcessor:
    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.detection_service = DetectionService(classifier)
        self.notification_orchestrator = NotificationOrchestrator()
        self._false_positive_tombstones: dict[str, float] = {}
        self._started_events = 0
        self._completed_events = 0
        self._dropped_events = 0
        self._stage_timeouts: Counter[str] = Counter()
        self._stage_failures: Counter[str] = Counter()
        self._stage_fallbacks: Counter[str] = Counter()
        self._drop_reasons: Counter[str] = Counter()
        self._recent_outcomes: deque[dict[str, Any]] = deque(maxlen=50)
        self._last_stage_timeout: dict[str, Any] | None = None
        self._last_stage_failure: dict[str, Any] | None = None
        self._last_drop: dict[str, Any] | None = None
        self._last_completed: dict[str, Any] | None = None
        self._last_critical_failure_monotonic: float | None = None
        self._last_critical_failure: dict[str, Any] | None = None
        self._active_live_event_keys: set[str] = set()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_critical_stage(self, stage: str) -> bool:
        return stage in {"classify_snapshot", "save_and_notify"}

    def _record_critical_failure(self, stage: str, event_id: str, kind: str, **details: Any) -> None:
        if not self._is_critical_stage(stage):
            return
        payload = {
            "event_id": event_id,
            "stage": stage,
            "kind": kind,
            "timestamp": self._utc_now(),
        }
        payload.update(details)
        self._last_critical_failure_monotonic = time.monotonic()
        self._last_critical_failure = payload

    def _critical_failure_active(self) -> bool:
        if self._last_critical_failure_monotonic is None:
            return False
        age = time.monotonic() - self._last_critical_failure_monotonic
        return age < EVENT_PIPELINE_RECOVERY_WINDOW_SECONDS

    def _has_historical_critical_failure(self) -> bool:
        return self._last_critical_failure_monotonic is not None

    def _record_recent_outcome(self, event_id: str, outcome: str, **details: Any) -> None:
        payload = {
            "event_id": event_id,
            "outcome": outcome,
            "timestamp": self._utc_now(),
        }
        payload.update(details)
        self._recent_outcomes.append(payload)

    def _record_drop(self, event_id: str, reason: str, **details: Any) -> None:
        reason_key = str(reason or "unknown")
        self._dropped_events += 1
        self._drop_reasons[reason_key] += 1
        payload = {
            "event_id": event_id,
            "reason": reason_key,
            "timestamp": self._utc_now(),
        }
        payload.update(details)
        self._last_drop = payload
        severity = "error" if reason_key in {"classify_snapshot_unavailable", "classify_snapshot_timeout", "save_and_notify_failed"} else "warning"
        error_diagnostics_history.record(
            source="event_pipeline",
            component="event_processor",
            stage=str(details.get("stage", "") or "") or None,
            reason_code=f"drop_{reason_key}",
            message=f"Dropped event due to {reason_key}",
            severity=severity,
            event_id=event_id,
            context=dict(details) if details else None,
        )
        self._record_recent_outcome(event_id, "dropped", reason=reason_key, **details)

    def _record_completed(self, event_id: str, duration_ms: float) -> None:
        self._completed_events += 1
        payload = {
            "event_id": event_id,
            "duration_ms": round(duration_ms, 1),
            "timestamp": self._utc_now(),
        }
        self._last_completed = payload
        self._record_recent_outcome(event_id, "completed", duration_ms=round(duration_ms, 1))

    def _record_stage_timeout(self, stage: str, event_id: str, timeout_seconds: float) -> None:
        self._stage_timeouts[stage] += 1
        payload = {
            "event_id": event_id,
            "stage": stage,
            "timeout_seconds": timeout_seconds,
            "timestamp": self._utc_now(),
        }
        self._last_stage_timeout = payload
        self._record_critical_failure(stage, event_id, "timeout", timeout_seconds=timeout_seconds)
        error_diagnostics_history.record(
            source="event_pipeline",
            component="event_processor",
            stage=stage,
            reason_code="stage_timeout",
            message=f"Stage {stage} timed out after {timeout_seconds}s",
            severity="error",
            event_id=event_id,
            context={"timeout_seconds": timeout_seconds},
        )
        self._record_recent_outcome(
            event_id,
            "stage_timeout",
            stage=stage,
            timeout_seconds=timeout_seconds,
        )

    def _record_stage_failure(self, stage: str, event_id: str, error: str) -> None:
        self._stage_failures[stage] += 1
        payload = {
            "event_id": event_id,
            "stage": stage,
            "error": error,
            "timestamp": self._utc_now(),
        }
        self._last_stage_failure = payload
        self._record_critical_failure(stage, event_id, "failure", error=error)
        error_diagnostics_history.record(
            source="event_pipeline",
            component="event_processor",
            stage=stage,
            reason_code="stage_failure",
            message=f"Stage {stage} failed: {error}",
            severity="critical",
            event_id=event_id,
            context={"error": error},
        )
        self._record_recent_outcome(event_id, "stage_failure", stage=stage, error=error)

    def _record_stage_fallback(self, stage: str, event_id: str) -> None:
        self._stage_fallbacks[stage] += 1
        self._record_recent_outcome(event_id, "stage_fallback", stage=stage)

    def _is_classify_snapshot_overload(self, stage: str, error: Exception) -> bool:
        if stage != "classify_snapshot":
            return False
        return isinstance(error, LiveImageClassificationOverloadedError) or str(error) == "classify_snapshot_overloaded"

    def _is_classify_snapshot_lease_expired(self, stage: str, error: Exception) -> bool:
        return stage == "classify_snapshot" and isinstance(error, ClassificationLeaseExpiredError)

    def get_status(self) -> dict[str, Any]:
        stage_timeouts = dict(self._stage_timeouts)
        stage_failures = dict(self._stage_failures)
        stage_fallbacks = dict(self._stage_fallbacks)
        drop_reasons = dict(self._drop_reasons)
        critical_failures = (
            int(stage_timeouts.get("classify_snapshot", 0))
            + int(stage_failures.get("classify_snapshot", 0))
            + int(stage_timeouts.get("save_and_notify", 0))
            + int(stage_failures.get("save_and_notify", 0))
        )
        incomplete_events = max(0, self._started_events - self._completed_events - self._dropped_events)
        critical_failure_active = self._critical_failure_active()
        has_unresolved_post_failure_work = self._has_historical_critical_failure() and incomplete_events > 0
        return {
            "status": "degraded" if (critical_failure_active or has_unresolved_post_failure_work) else "ok",
            "started_events": self._started_events,
            "completed_events": self._completed_events,
            "dropped_events": self._dropped_events,
            "incomplete_events": incomplete_events,
            "stage_timeouts": stage_timeouts,
            "stage_failures": stage_failures,
            "stage_fallbacks": stage_fallbacks,
            "drop_reasons": drop_reasons,
            "critical_failures": critical_failures,
            "last_stage_timeout": self._last_stage_timeout,
            "last_stage_failure": self._last_stage_failure,
            "last_drop": self._last_drop,
            "last_completed": self._last_completed,
            "last_critical_failure": self._last_critical_failure,
            "critical_failure_recovery_window_seconds": EVENT_PIPELINE_RECOVERY_WINDOW_SECONDS,
            "critical_failure_active": critical_failure_active,
            "has_unresolved_post_failure_work": has_unresolved_post_failure_work,
            "recent_outcomes": list(self._recent_outcomes),
        }

    async def _run_stage(
        self,
        *,
        event_id: str,
        stage: str,
        timeout_seconds: float,
        coro,
        fallback: Any = None,
    ) -> tuple[bool, Any]:
        try:
            return True, await asyncio.wait_for(coro, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self._record_stage_timeout(stage, event_id, timeout_seconds)
            log.warning(
                "MQTT event stage timed out",
                event_id=event_id,
                stage=stage,
                timeout_seconds=timeout_seconds,
            )
            if stage == "classify_snapshot":
                return False, _CLASSIFY_SNAPSHOT_TIMED_OUT
            return False, fallback
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self._is_classify_snapshot_overload(stage, e):
                log.warning(
                    "MQTT event stage overloaded",
                    event_id=event_id,
                    stage=stage,
                    error=str(e),
                )
                return False, _CLASSIFY_SNAPSHOT_OVERLOADED
            if self._is_classify_snapshot_lease_expired(stage, e):
                timeout_seconds = float(getattr(e, "timeout_seconds", EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS))
                self._record_stage_timeout(stage, event_id, timeout_seconds)
                log.warning(
                    "MQTT event stage lease expired",
                    event_id=event_id,
                    stage=stage,
                    timeout_seconds=timeout_seconds,
                )
                return False, _CLASSIFY_SNAPSHOT_TIMED_OUT
            self._record_stage_failure(stage, event_id, str(e))
            log.error(
                "MQTT event stage failed",
                event_id=event_id,
                stage=stage,
                error=str(e),
                exc_info=True,
            )
            return False, fallback

    async def _lookup_taxonomy_aliases(self, query: str, event_id: str | None = None) -> Dict[str, Any]:
        try:
            taxonomy = await asyncio.wait_for(
                taxonomy_service.get_names(query),
                timeout=EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS,
            )
            if isinstance(taxonomy, dict):
                return taxonomy
        except asyncio.TimeoutError:
            log.warning(
                "Taxonomy alias lookup timed out during audio correlation",
                event_id=event_id,
                query=query,
                timeout_seconds=EVENT_TAXONOMY_LOOKUP_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.debug(
                "Taxonomy alias lookup failed during audio correlation",
                event_id=event_id,
                query=query,
                error=str(e),
            )
        return {}

    async def process_audio_message(self, payload: bytes):
        """Process audio detections from BirdNET-Go."""
        try:
            data = json.loads(payload)
            await audio_service.add_detection(data)
        except Exception as e:
            log.error("Failed to process audio message", error=str(e))

    async def process_mqtt_message(self, payload: bytes):
        """Main entry point for processing Frigate MQTT events."""
        event_id = "unknown"
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                after = data.get("after")
                if isinstance(after, dict):
                    event_id = str(after.get("id") or "unknown")
            await self._process_event_payload(data)
        except json.JSONDecodeError as e:
            log.error("Invalid JSON payload", error=str(e))
        except Exception as e:
            log.error("Error processing event", event_id=event_id, error=str(e), exc_info=True)
            return

    async def _process_event_payload(self, data: Dict[str, Any]) -> None:
        """Process a decoded MQTT payload end-to-end with guardrails."""
        event = self._parse_and_validate_event(data)
        if not event:
            return
        self._started_events += 1
        started = time.monotonic()

        if event.is_false_positive:
            self._mark_false_positive_tombstone(event.frigate_event)
            log.info("Frigate marked event as false positive - cleaning up", event_id=event.frigate_event)
            await self._handle_false_positive(event.frigate_event)
            duration_ms = (time.monotonic() - started) * 1000.0
            self._record_completed(event.frigate_event, duration_ms)
            self._record_recent_outcome(event.frigate_event, "false_positive_cleanup")
            return

        if self._is_false_positive_tombstone_active(event.frigate_event):
            log.info("Skipping event previously marked as false positive", event_id=event.frigate_event)
            self._record_drop(event.frigate_event, "false_positive_tombstone_active")
            return

        if self._is_stale_live_event(event):
            age_seconds = round(self._live_event_age_seconds(event), 1)
            log.info(
                "Dropping stale live MQTT event before classification",
                event_id=event.frigate_event,
                age_seconds=age_seconds,
                stale_after_seconds=LIVE_EVENT_STALE_SECONDS,
            )
            self._record_drop(
                event.frigate_event,
                "live_event_stale",
                age_seconds=age_seconds,
                stale_after_seconds=LIVE_EVENT_STALE_SECONDS,
            )
            return

        if not self._try_acquire_live_event_key(event):
            event_key = self._live_event_key(event)
            log.info(
                "Coalescing duplicate live MQTT event",
                event_id=event.frigate_event,
                event_key=event_key,
            )
            self._record_drop(
                event.frigate_event,
                "live_event_coalesced",
                event_key=event_key,
            )
            return

        try:
            _classification_ok, classification_result = await self._run_stage(
                event_id=event.frigate_event,
                stage="classify_snapshot",
                timeout_seconds=EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS,
                coro=self._classify_snapshot(event),
                fallback=None,
            )
            if classification_result is _CLASSIFY_SNAPSHOT_OVERLOADED:
                self._record_drop(event.frigate_event, "classify_snapshot_overloaded", stage="classify_snapshot")
                return
            if classification_result is _CLASSIFY_SNAPSHOT_TIMED_OUT:
                self._record_drop(event.frigate_event, "classify_snapshot_timeout", stage="classify_snapshot")
                return
            if not classification_result:
                log.info(
                    "Dropping MQTT event after classification stage failure",
                    event_id=event.frigate_event,
                    stage="classify_snapshot",
                )
                self._record_drop(event.frigate_event, "classify_snapshot_unavailable")
                return

            results, snapshot_data = classification_result
            if not results:
                log.info(
                    "Dropping MQTT event because classifier returned no results",
                    event_id=event.frigate_event,
                )
                self._record_drop(event.frigate_event, "classifier_empty_results")
                return

            top, reason = self.detection_service.filter_and_label(
                results[0], event.frigate_event, event.sub_label, event.frigate_score
            )
            if not top:
                top_candidate = results[0] if results else {}
                log.info(
                    "Dropping MQTT event after classification filter",
                    event_id=event.frigate_event,
                    reason=reason or "unknown",
                    label=top_candidate.get("label"),
                    score=top_candidate.get("score"),
                )
                self._record_drop(
                    event.frigate_event,
                    f"filter_{reason or 'unknown'}",
                    label=top_candidate.get("label"),
                    score=top_candidate.get("score"),
                )
                return

            context_ok, context_result = await self._run_stage(
                event_id=event.frigate_event,
                stage="gather_context",
                timeout_seconds=EVENT_STAGE_TIMEOUT_CONTEXT_SECONDS,
                coro=self._gather_context_data(event),
                fallback={"audio_match": None, "weather_data": {}},
            )
            context = context_result if isinstance(context_result, dict) else {"audio_match": None, "weather_data": {}}
            if not context_ok:
                self._record_stage_fallback("gather_context", event.frigate_event)
                log.info(
                    "Proceeding without full context after stage failure",
                    event_id=event.frigate_event,
                    stage="gather_context",
                )

            _audio_ok, top_with_audio = await self._run_stage(
                event_id=event.frigate_event,
                stage="correlate_audio",
                timeout_seconds=EVENT_STAGE_TIMEOUT_AUDIO_CORRELATE_SECONDS,
                coro=self._correlate_audio(top, context.get("audio_match"), event.frigate_event),
                fallback=top,
            )
            if not isinstance(top_with_audio, dict):
                self._record_stage_fallback("correlate_audio", event.frigate_event)
                top_with_audio = top

            save_ok, _ = await self._run_stage(
                event_id=event.frigate_event,
                stage="save_and_notify",
                timeout_seconds=EVENT_STAGE_TIMEOUT_SAVE_AND_NOTIFY_SECONDS,
                coro=self._handle_detection_save_and_notify(
                    event, top_with_audio, snapshot_data, context
                ),
                fallback=None,
            )
            if not save_ok:
                self._record_drop(event.frigate_event, "save_and_notify_failed")
                return

            duration_ms = (time.monotonic() - started) * 1000.0
            self._record_completed(event.frigate_event, duration_ms)
            log.debug(
                "Completed MQTT event processing",
                event_id=event.frigate_event,
                duration_ms=round(duration_ms, 1),
            )
        finally:
            self._release_live_event_key(event)

    def _prune_false_positive_tombstones(self) -> None:
        now = time.monotonic()
        expired = [event_id for event_id, expiry in self._false_positive_tombstones.items() if expiry <= now]
        for event_id in expired:
            self._false_positive_tombstones.pop(event_id, None)

    def _mark_false_positive_tombstone(self, event_id: str) -> None:
        if not event_id:
            return
        self._prune_false_positive_tombstones()
        self._false_positive_tombstones[event_id] = time.monotonic() + FALSE_POSITIVE_TOMBSTONE_TTL_SECONDS

    def _is_false_positive_tombstone_active(self, event_id: str) -> bool:
        if not event_id:
            return False
        self._prune_false_positive_tombstones()
        expiry = self._false_positive_tombstones.get(event_id)
        return bool(expiry and expiry > time.monotonic())

    async def _handle_false_positive(self, frigate_event_id: str):
        """Delete detection if Frigate marks it as false positive."""
        try:
            # Clean up cached media immediately
            await media_cache.delete_cached_media(frigate_event_id)

            async with get_db() as db:
                repo = DetectionRepository(db)
                # Check if it exists
                exists = await repo.get_by_frigate_event(frigate_event_id)
                if exists:
                    log.info("Deleting false positive detection", event_id=frigate_event_id)
                    await repo.delete(frigate_event_id)
                    
                    # Notify frontend of deletion (if SSE connected)
                    from app.services.broadcaster import broadcaster
                    await broadcaster.broadcast({
                        "type": "detection_deleted",
                        "data": {
                            "frigate_event": frigate_event_id,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
        except Exception as e:
            log.error("Failed to cleanup false positive", event_id=frigate_event_id, error=str(e))

    def _parse_and_validate_event(self, data: Dict[str, Any]) -> Optional[EventData]:
        """Parse MQTT message and validate it should be processed.

        Returns:
            EventData if valid, None if should be skipped
        """
        after = data.get('after', {})
        if not after:
            return None

        event = EventData(data)
        event_type = (event.type or "new").lower()
        
        # Log processing start
        if event_type == "new" or event.is_false_positive:
             log.info("Processing MQTT event", event_id=event.frigate_event, label=event.label, type=event.type, false_positive=event.is_false_positive)

        # Only process bird events
        if event.label != 'bird':
            return None

        # Ignore routine update/end chatter; keep first actionable event only.
        # False positives can arrive on updates, so always allow cleanup path.
        if not event.is_false_positive and event_type != "new":
            return None

        if not event.frigate_event or event.frigate_event == "unknown":
            log.warning("Skipping event with missing id", event_id=event.frigate_event)
            return None

        if not event.camera:
            log.warning("Skipping event with missing camera", event_id=event.frigate_event)
            return None

        # Filter by camera if configured
        if settings.frigate.camera and event.camera not in settings.frigate.camera:
            # Only log this once per event (on new) to avoid spam
            if event_type == "new":
                log.info("Filtering event by camera", camera=event.camera, allowed=settings.frigate.camera)
            return None

        return event

    def _live_event_key(self, event: EventData) -> str:
        return f"{event.camera}:{event.frigate_event}"

    def _live_event_age_seconds(self, event: EventData) -> float:
        if event.start_time_ts <= 0:
            return 0.0
        return max(0.0, time.time() - float(event.start_time_ts))

    def _is_stale_live_event(self, event: EventData) -> bool:
        if event.is_false_positive:
            return False
        return self._live_event_age_seconds(event) >= LIVE_EVENT_STALE_SECONDS

    def _try_acquire_live_event_key(self, event: EventData) -> bool:
        if not getattr(settings.classification, "live_event_coalescing_enabled", True):
            return True
        event_key = self._live_event_key(event)
        if event_key in self._active_live_event_keys:
            return False
        self._active_live_event_keys.add(event_key)
        return True

    def _release_live_event_key(self, event: EventData) -> None:
        if not getattr(settings.classification, "live_event_coalescing_enabled", True):
            return
        self._active_live_event_keys.discard(self._live_event_key(event))

    async def _classify_snapshot(self, event: EventData) -> Optional[Tuple[list, Optional[bytes]]]:
        """Classify snapshot or use Frigate sublabel if trusted.

        Returns:
            Tuple of (classification_results, snapshot_data) if successful, None otherwise
        """
        # Trust Frigate sublabel path
        if settings.classification.trust_frigate_sublabel and event.sub_label:
            log.info("Using Frigate sublabel (skipping classification)",
                     event=event.frigate_event, sub_label=event.sub_label, score=event.frigate_score)

            results = [{
                "label": event.sub_label,
                "score": event.frigate_score or 1.0,
                "index": -1
            }]
            return (results, None)

        # Normal classification path
        try:
            snapshot_data = await frigate_client.get_snapshot(event.frigate_event, crop=True, quality=95)
            if not snapshot_data:
                log.info("Skipping MQTT event - snapshot unavailable", event_id=event.frigate_event)
                return None

            image = Image.open(BytesIO(snapshot_data))
            results = await self.classifier.classify_async_live(image, camera_name=event.camera)

            if not results:
                log.info("Skipping MQTT event - classifier returned empty results", event_id=event.frigate_event)
                return None

            return (results, snapshot_data)

        except (LiveImageClassificationOverloadedError, ClassificationLeaseExpiredError):
            raise
        except Exception as e:
            log.error("Classification failed", event_id=event.frigate_event, error=str(e))
            return None

    async def _gather_context_data(self, event: EventData) -> Dict[str, Any]:
        """Gather audio and weather context data in parallel.

        Returns:
            Dict with 'audio_match' and 'weather_data' keys
        """
        async def fetch_audio():
            """Fetch audio match with error handling."""
            try:
                return await audio_service.find_match(
                    event.detection_dt,
                    camera_name=event.camera,
                    window_seconds=settings.frigate.audio_correlation_window_seconds
                )
            except Exception as e:
                log.warning("Audio match failed", error=str(e))
                return None

        async def fetch_weather():
            """Fetch weather with error handling."""
            try:
                return await weather_service.get_current_weather()
            except Exception as e:
                log.warning("Weather fetch failed", error=str(e))
                return None

        # Execute both lookups in parallel
        audio_match, weather_data = await asyncio.gather(
            fetch_audio(),
            fetch_weather(),
            return_exceptions=False
        )

        return {
            'audio_match': audio_match,
            'weather_data': weather_data
        }

    async def _correlate_audio(
        self,
        classification: Dict[str, Any],
        audio_match,
        event_id: str | None = None,
    ) -> Dict[str, Any]:
        """Correlate audio detection with visual classification.

        Modifies classification dict with audio correlation data.

        Returns:
            Updated classification dict
        """
        # Initialize audio fields (only set when confirmed or used for upgrade)
        classification['audio_confirmed'] = False
        classification['audio_species'] = None
        classification['audio_score'] = None

        if not audio_match:
            return classification

        audio_species = audio_match.species
        audio_score = audio_match.confidence
        visual_label = classification['label']
        visual_label_normalized = str(visual_label or "").strip().lower()
        audio_species_normalized = str(audio_species or "").strip().lower()
        audio_scientific_normalized = str(getattr(audio_match, "scientific_name", "") or "").strip().lower()

        visual_aliases = {visual_label_normalized}
        try:
            taxonomy = await self._lookup_taxonomy_aliases(visual_label, event_id=event_id)
            sci = str(taxonomy.get("scientific_name") or "").strip().lower()
            common = str(taxonomy.get("common_name") or "").strip().lower()
            if sci:
                visual_aliases.add(sci)
            if common:
                visual_aliases.add(common)
        except Exception as e:
            log.debug("Visual taxonomy lookup failed during audio correlation", label=visual_label, error=str(e))

        audio_aliases = {audio_species_normalized}
        if audio_scientific_normalized:
            audio_aliases.add(audio_scientific_normalized)
        else:
            try:
                audio_taxonomy = await self._lookup_taxonomy_aliases(audio_species, event_id=event_id)
                audio_sci = str(audio_taxonomy.get("scientific_name") or "").strip().lower()
                audio_common = str(audio_taxonomy.get("common_name") or "").strip().lower()
                if audio_sci:
                    audio_aliases.add(audio_sci)
                if audio_common:
                    audio_aliases.add(audio_common)
            except Exception as e:
                log.debug("Audio taxonomy lookup failed during audio correlation", species=audio_species, error=str(e))

        # Logic 1: Confirmation - audio matches visual
        if visual_aliases.intersection(audio_aliases):
            classification['audio_confirmed'] = True
            classification['audio_species'] = audio_species
            classification['audio_score'] = audio_score
            # Boost score if audio is more confident
            if audio_score > classification['score']:
                classification['score'] = audio_score
            log.info("Audio confirmed visual detection", species=visual_label, score=classification['score'])
        else:
            # Mismatch: Attach audio species/score for 'also heard' display, but don't confirm or upgrade
            classification['audio_confirmed'] = False
            classification['audio_species'] = audio_species
            classification['audio_score'] = audio_score
            log.debug("Audio recorded as heard (not confirmed)", visual=visual_label, audio=audio_species)

        return classification

    def _extract_weather_fields(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract weather fields from context payload."""
        weather = context.get('weather_data') or {}
        return {
            "temperature": weather.get("temperature"),
            "weather_condition": weather.get("condition_text"),
            "weather_cloud_cover": weather.get("cloud_cover"),
            "weather_wind_speed": weather.get("wind_speed"),
            "weather_wind_direction": weather.get("wind_direction"),
            "weather_precipitation": weather.get("precipitation"),
            "weather_rain": weather.get("rain"),
            "weather_snowfall": weather.get("snowfall"),
        }

    async def _handle_detection_save_and_notify(
        self,
        event: EventData,
        classification: Dict[str, Any],
        snapshot_data: Optional[bytes],
        context: Dict[str, Any]
    ):
        """Save detection to database and send notifications.

        Args:
            event: Parsed event data
            classification: Classification result with audio correlation
            snapshot_data: Snapshot image bytes (may be None)
            context: Context data (audio_match, weather_data)
        """
        label = classification['label']
        score = classification['score']

        weather_fields = self._extract_weather_fields(context)

        # Save detection (upsert)
        changed, was_inserted = await self.detection_service.save_detection(
            frigate_event=event.frigate_event,
            camera=event.camera,
            start_time=event.start_time_ts,
            classification=classification,
            frigate_score=event.frigate_score,
            sub_label=event.sub_label,
            audio_confirmed=classification['audio_confirmed'],
            audio_species=classification['audio_species'],
            audio_score=classification['audio_score'],
            temperature=weather_fields["temperature"],
            weather_condition=weather_fields["weather_condition"],
            weather_cloud_cover=weather_fields["weather_cloud_cover"],
            weather_wind_speed=weather_fields["weather_wind_speed"],
            weather_wind_direction=weather_fields["weather_wind_direction"],
            weather_precipitation=weather_fields["weather_precipitation"],
            weather_rain=weather_fields["weather_rain"],
            weather_snowfall=weather_fields["weather_snowfall"]
        )

        # Update Frigate sublabel if confident
        if (
            settings.classification.write_frigate_sublabel
            and (score > settings.classification.threshold or classification['audio_confirmed'])
        ):
            await frigate_client.set_sublabel(event.frigate_event, label)

        # Send notifications based on policy
        if changed:
            # Cache snapshot if we updated the DB (ensures image matches score)
            if snapshot_data and settings.media_cache.enabled and settings.media_cache.cache_snapshots:
                await media_cache.cache_snapshot(event.frigate_event, snapshot_data)
                if settings.media_cache.high_quality_event_snapshots:
                    high_quality_snapshot_service.schedule_replacement(event.frigate_event)

            # Trigger auto video classification
            if settings.classification.auto_video_classification:
                from app.services.auto_video_classifier_service import auto_video_classifier
                await auto_video_classifier.trigger_classification(event.frigate_event, event.camera)
        else:
            log.debug(
                "Detection unchanged after upsert",
                event_id=event.frigate_event,
                score=score,
            )

        # Keep remote notification I/O off MQTT ingest hot path.
        notify_event = SimpleNamespace(
            frigate_event=event.frigate_event,
            camera=event.camera,
            detection_dt=event.detection_dt,
            type=event.type,
        )
        notify_classification = dict(classification)

        async def _run_notification_flow() -> None:
            await self.notification_orchestrator.handle_notifications(
                event=notify_event,
                classification=notify_classification,
                snapshot_data=snapshot_data,
                changed=changed,
                was_inserted=was_inserted,
            )

        job_name = f"notify:{event.frigate_event}:{event.type or 'new'}"
        enqueued = await notification_dispatcher.enqueue(job_name=job_name, job_factory=_run_notification_flow)
        if not enqueued:
            log.warning("Notification queue saturated; dropping notification job", event_id=event.frigate_event)
