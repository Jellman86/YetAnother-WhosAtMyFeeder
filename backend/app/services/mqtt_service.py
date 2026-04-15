import asyncio
import contextlib
import json
import os
import structlog
import uuid
import random
import time
from aiomqtt import Client, MqttError
from app.config import settings
from app.services.error_diagnostics import error_diagnostics_history
from app.utils.tasks import create_background_task

log = structlog.get_logger()

# Reconnection backoff parameters
INITIAL_BACKOFF = 1  # Start with 1 second
MAX_BACKOFF = 60     # Cap at 60 seconds
BACKOFF_MULTIPLIER = 2
MQTT_HANDLER_CONCURRENCY = 4
MQTT_MAX_IN_FLIGHT_MESSAGES = 200
MQTT_FRIGATE_HANDLER_TIMEOUT_SECONDS = 45.0
MQTT_AUDIO_HANDLER_TIMEOUT_SECONDS = 10.0
MQTT_PRESSURE_ELEVATED_RATIO = 0.50
MQTT_PRESSURE_HIGH_RATIO = 0.70
MQTT_PRESSURE_CRITICAL_RATIO = 0.90
MQTT_FRIGATE_TOPIC_STALE_SECONDS = max(30.0, float(os.getenv("MQTT_FRIGATE_TOPIC_STALE_SECONDS", "1800")))
MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES = max(1, int(os.getenv("MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", "20")))
MQTT_TOPIC_STALL_GRACE_SECONDS = max(10.0, float(os.getenv("MQTT_TOPIC_STALL_GRACE_SECONDS", "60")))
MQTT_WATCHDOG_INTERVAL_SECONDS = max(10.0, float(os.getenv("MQTT_WATCHDOG_INTERVAL_SECONDS", "30")))
MAX_HANDLER_WAIT_SECONDS = max(30.0, float(os.getenv("MQTT_MAX_HANDLER_WAIT_SECONDS", "120")))
MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS = max(1, int(os.getenv("MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS", "5")))
MQTT_HANDLER_WAIT_EXHAUSTION_HEALTH_WINDOW_SECONDS = max(
    30.0,
    float(os.getenv("MQTT_HANDLER_WAIT_EXHAUSTION_HEALTH_WINDOW_SECONDS", "120")),
)

class MQTTService:
    def __init__(self, version: str = "unknown"):
        self.client = None
        self.running = False
        self.paused = False
        self.reconnect_delay = INITIAL_BACKOFF
        self._handler_semaphore = asyncio.Semaphore(MQTT_HANDLER_CONCURRENCY)
        self._in_flight_tasks: set[asyncio.Task] = set()
        self._event_task_tails: dict[str, asyncio.Task] = {}
        self._event_tail_depths: dict[str, int] = {}
        self._event_pending_tasks: dict[str, asyncio.Task] = {}
        self._event_pending_payloads: dict[str, bytes] = {}
        self._topic_last_message_monotonic: dict[str, float] = {}
        self._topic_message_counts: dict[str, int] = {}
        self._topic_message_counts_lifetime: dict[str, int] = {}
        self._task_kind_by_id: dict[int, str] = {}
        self._audio_active_task: asyncio.Task | None = None
        self._audio_pending_task: asyncio.Task | None = None
        self._audio_pending_payload: bytes | None = None
        self._audio_messages_superseded = 0
        self._audio_dispatch_count = 0
        self._frigate_dispatch_count = 0
        self._frigate_messages_superseded = 0
        self._max_event_tail_depth = 0
        self._connection_started_monotonic: float | None = None
        self._topic_liveness_reconnects = 0
        self._stall_recovery_consecutive_no_frigate_reconnects = 0
        self._last_reconnect_reason: str | None = None
        self._intentional_reconnect: bool = False
        self._backlog_wait_started_monotonic: float | None = None
        self._handler_slot_wait_exhaustions = 0
        self._last_handler_slot_wait_exhausted_monotonic: float | None = None
        self._frigate_availability: str | None = None          # "online", "offline", or None (never seen)
        self._frigate_availability_monotonic: float | None = None  # monotonic time of last payload
        # Simplified Client ID: yawamf-{git_hash}
        # version format is usually "2.0.0+abc1234"
        git_hash = version.split('+')[-1] if '+' in version else "unknown"

        # If hash is unknown (local dev or missing build arg), append session ID to avoid collisions
        if git_hash == "unknown":
            session_id = str(uuid.uuid4())[:8]
            self.client_id = f"yawamf-unknown-{session_id}"
        else:
            self.client_id = f"yawamf-{git_hash}"

    def _compute_pressure_level(self, in_flight: int) -> str:
        if MQTT_MAX_IN_FLIGHT_MESSAGES <= 0:
            return "normal"
        load = in_flight / float(MQTT_MAX_IN_FLIGHT_MESSAGES)
        if load >= MQTT_PRESSURE_CRITICAL_RATIO:
            return "critical"
        if load >= MQTT_PRESSURE_HIGH_RATIO:
            return "high"
        if load >= MQTT_PRESSURE_ELEVATED_RATIO:
            return "elevated"
        return "normal"

    def get_status(self) -> dict:
        in_flight = len(self._in_flight_tasks)
        pressure_level = self._compute_pressure_level(in_flight)
        now = self._now_monotonic()
        in_flight_by_topic = {
            "frigate": 0,
            "birdnet": 0,
        }
        for task in self._in_flight_tasks:
            kind = self._task_kind_by_id.get(id(task))
            if kind in in_flight_by_topic:
                in_flight_by_topic[kind] += 1
        frigate_topic = f"{settings.frigate.main_topic}/events"
        birdnet_topic = settings.frigate.audio_topic
        # Half the Frigate stale threshold: BirdNET traffic must be this fresh to
        # trigger the higher-confidence BirdNET-assisted stall check.  On low-traffic
        # feeders (long inter-visit gaps) this threshold will normally not be met, so
        # the independent watchdog path (_should_reconnect_independent) becomes the
        # primary stall-detection path.  That is expected and fine.
        birdnet_active_age_threshold = max(10.0, MQTT_FRIGATE_TOPIC_STALE_SECONDS / 2.0)
        backlog_wait_started = self._backlog_wait_started_monotonic
        backlog_wait_seconds = (
            round(max(0.0, now - backlog_wait_started), 1)
            if backlog_wait_started is not None
            else None
        )
        last_wait_exhausted = self._last_handler_slot_wait_exhausted_monotonic
        last_wait_exhausted_age_seconds = (
            round(max(0.0, now - last_wait_exhausted), 1)
            if last_wait_exhausted is not None
            else None
        )
        recent_handler_slot_wait_exhaustion = bool(
            last_wait_exhausted_age_seconds is not None
            and last_wait_exhausted_age_seconds <= MQTT_HANDLER_WAIT_EXHAUSTION_HEALTH_WINDOW_SECONDS
        )
        topic_ages = {
            frigate_topic: self._topic_age_seconds(frigate_topic, now),
            birdnet_topic: self._topic_age_seconds(birdnet_topic, now),
        }
        stall_recovery_warning_active = bool(
            not self._frigate_confirmed_online()
            and self._stall_recovery_consecutive_no_frigate_reconnects > 0
            and topic_ages[birdnet_topic] is not None
            and topic_ages[birdnet_topic] <= birdnet_active_age_threshold
        )
        return {
            "running": self.running,
            "paused": self.paused,
            "connected": self.client is not None,
            "in_flight": in_flight,
            "in_flight_by_topic": in_flight_by_topic,
            "in_flight_capacity": MQTT_MAX_IN_FLIGHT_MESSAGES,
            "handler_concurrency": MQTT_HANDLER_CONCURRENCY,
            "dispatch_counts": {
                "frigate": self._frigate_dispatch_count,
                "birdnet": self._audio_dispatch_count,
            },
            "pressure_level": pressure_level,
            "under_pressure": pressure_level in {"high", "critical"},
            "backlog_wait_active": backlog_wait_started is not None,
            "backlog_wait_seconds": backlog_wait_seconds,
            "audio_pending_coalesced": self._audio_pending_payload is not None,
            "audio_messages_superseded": self._audio_messages_superseded,
            "frigate_messages_superseded": self._frigate_messages_superseded,
            "frigate_event_tail_count": len(self._event_task_tails),
            "max_frigate_event_tail_depth": self._max_event_tail_depth,
            "handler_slot_wait_exhaustions": self._handler_slot_wait_exhaustions,
            "recent_handler_slot_wait_exhaustion": recent_handler_slot_wait_exhaustion,
            "last_handler_slot_wait_exhausted_age_seconds": last_wait_exhausted_age_seconds,
            "connection_uptime_seconds": (
                round(now - self._connection_started_monotonic, 1)
                if self._connection_started_monotonic is not None
                else None
            ),
            "topic_message_counts": {
                "frigate": self._topic_message_counts.get(frigate_topic, 0),
                "birdnet": self._topic_message_counts.get(birdnet_topic, 0),
            },
            "topic_last_message_age_seconds": {
                "frigate": round(topic_ages[frigate_topic], 1) if topic_ages[frigate_topic] is not None else None,
                "birdnet": round(topic_ages[birdnet_topic], 1) if topic_ages[birdnet_topic] is not None else None,
            },
            "frigate_topic_stale_seconds": MQTT_FRIGATE_TOPIC_STALE_SECONDS,
            "topic_liveness_reconnects": self._topic_liveness_reconnects,
            "last_reconnect_reason": self._last_reconnect_reason,
            "stall_recovery_consecutive_no_frigate_reconnects": self._stall_recovery_consecutive_no_frigate_reconnects,
            "stall_recovery_warning_active": stall_recovery_warning_active,
            "stall_recovery_warning_age_threshold_seconds": birdnet_active_age_threshold,
            "intentional_reconnect_pending": self._intentional_reconnect,
            "frigate_availability": {
                "status": self._frigate_availability if self._frigate_availability is not None else "unknown",
                "last_seen_age_seconds": (
                    round(max(0.0, now - self._frigate_availability_monotonic), 1)
                    if self._frigate_availability_monotonic is not None
                    else None
                ),
            },
        }

    def is_under_pressure(self, min_level: str = "high") -> bool:
        order = {"normal": 0, "elevated": 1, "high": 2, "critical": 3}
        status = self.get_status()
        level = str(status.get("pressure_level", "normal"))
        return order.get(level, 0) >= order.get(min_level, 2)

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff with jitter.

        Returns delay in seconds with random jitter to prevent thundering herd.
        """
        # Add ±25% jitter to prevent connection storms
        jitter = random.uniform(0.75, 1.25)
        delay = min(self.reconnect_delay * jitter, MAX_BACKOFF)
        return delay

    def _increase_backoff(self):
        """Increase backoff delay exponentially."""
        self.reconnect_delay = min(self.reconnect_delay * BACKOFF_MULTIPLIER, MAX_BACKOFF)

    def _reset_backoff(self):
        """Reset backoff delay after successful connection."""
        self.reconnect_delay = INITIAL_BACKOFF

    def _track_handler_task(self, task: asyncio.Task, kind: str):
        self._in_flight_tasks.add(task)
        self._task_kind_by_id[id(task)] = kind

        def _cleanup(done: asyncio.Task) -> None:
            self._in_flight_tasks.discard(done)
            self._task_kind_by_id.pop(id(done), None)
            if kind == "birdnet" and self._audio_active_task is done:
                self._audio_active_task = None

        task.add_done_callback(_cleanup)

    def _now_monotonic(self) -> float:
        return time.monotonic()

    def _record_topic_message(self, topic: str, now: float | None = None) -> None:
        ts = now if now is not None else self._now_monotonic()
        frigate_topic = f"{settings.frigate.main_topic}/events"
        if (
            topic == frigate_topic
            and self._topic_message_counts.get(topic, 0) <= 0
            and self._stall_recovery_consecutive_no_frigate_reconnects > 0
        ):
            log.info(
                "Frigate traffic resumed after stalled MQTT recovery",
                consecutive_reconnects_without_frigate=self._stall_recovery_consecutive_no_frigate_reconnects,
            )
            self._stall_recovery_consecutive_no_frigate_reconnects = 0
        self._topic_last_message_monotonic[topic] = ts
        self._topic_message_counts[topic] = self._topic_message_counts.get(topic, 0) + 1
        self._topic_message_counts_lifetime[topic] = self._topic_message_counts_lifetime.get(topic, 0) + 1

    def _topic_count_lifetime(self, topic: str) -> int:
        return int(self._topic_message_counts_lifetime.get(topic, 0) or 0)

    def _frigate_confirmed_online(self) -> bool:
        """True if Frigate has explicitly confirmed it is online via frigate/available."""
        return self._frigate_availability == "online"

    def _handle_frigate_availability(self, payload: bytes) -> None:
        """Process a message from the frigate/available topic."""
        value = payload.decode("utf-8", errors="replace").strip()
        now = self._now_monotonic()
        previous = self._frigate_availability
        self._frigate_availability = value
        self._frigate_availability_monotonic = now

        if value == "online":
            if self._stall_recovery_consecutive_no_frigate_reconnects > 0:
                log.info(
                    "Frigate reported online; clearing stall-recovery counter",
                    consecutive_reconnects_cleared=self._stall_recovery_consecutive_no_frigate_reconnects,
                )
                self._stall_recovery_consecutive_no_frigate_reconnects = 0
            if previous == "offline":
                log.info("Frigate availability restored: online")
                error_diagnostics_history.record(
                    source="mqtt",
                    component="mqtt_service",
                    reason_code="frigate_came_online",
                    message="Frigate has come back online (frigate/available: online).",
                    severity="info",
                    context={"previous": previous},
                )
        elif value == "offline":
            log.warning("Frigate reported offline via frigate/available")
            if previous != "offline":
                error_diagnostics_history.record(
                    source="mqtt",
                    component="mqtt_service",
                    reason_code="frigate_went_offline",
                    message="Frigate has gone offline (frigate/available: offline). No new detections until Frigate restarts.",
                    severity="warning",
                    context={"previous": previous},
                )
        else:
            log.debug("Unknown frigate/available payload", value=value)

    def _note_stall_reconnect(
        self,
        *,
        reason: str,
        now: float,
        frigate_topic: str,
        birdnet_topic: str,
        no_frigate_after_previous_reconnect: bool,
    ) -> bool:
        self._topic_liveness_reconnects += 1
        self._last_reconnect_reason = reason
        if not no_frigate_after_previous_reconnect:
            return True

        self._stall_recovery_consecutive_no_frigate_reconnects += 1

        at_cap = self._stall_recovery_consecutive_no_frigate_reconnects >= MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS
        if at_cap:
            reason_code = "frigate_recovery_abandoned"
            message = (
                f"Frigate topic absent after {self._stall_recovery_consecutive_no_frigate_reconnects} consecutive "
                "stall-recovery reconnects; giving up further reconnects. Check the Frigate MQTT topic "
                "configuration and verify Frigate is publishing events."
            )
        else:
            reason_code = "frigate_recovery_no_frigate_resume"
            message = "Frigate topic still absent after a stall-recovery reconnect; reconnecting again while BirdNET remains active."

        error_diagnostics_history.record(
            source="mqtt",
            component="mqtt_service",
            reason_code=reason_code,
            message=message,
            severity="error" if self._stall_recovery_consecutive_no_frigate_reconnects >= 2 else "warning",
            context={
                "consecutive_reconnects_without_frigate": self._stall_recovery_consecutive_no_frigate_reconnects,
                "max_consecutive_reconnects": MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS,
                "connection_uptime_seconds": round(
                    max(0.0, now - self._connection_started_monotonic),
                    1,
                ) if self._connection_started_monotonic is not None else None,
                "birdnet_messages_seen": self._topic_message_counts.get(birdnet_topic, 0),
                "frigate_messages_seen": self._topic_message_counts.get(frigate_topic, 0),
                "last_reconnect_reason": reason,
                "recovery_abandoned": at_cap,
            },
            correlation_key="mqtt:frigate_recovery_no_resume",
        )
        if at_cap:
            log.error(
                "MQTT stall recovery abandoned: Frigate topic absent after maximum consecutive reconnects",
                consecutive_reconnects_without_frigate=self._stall_recovery_consecutive_no_frigate_reconnects,
                max_allowed=MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS,
            )
            return False
        return True

    def _topic_age_seconds(self, topic: str, now: float | None = None) -> float | None:
        last = self._topic_last_message_monotonic.get(topic)
        if last is None:
            return None
        ts = now if now is not None else self._now_monotonic()
        return max(0.0, ts - last)

    def _should_reconnect_independent(
        self,
        frigate_topic: str,
        now: float | None = None,
    ) -> bool:
        """Check whether the Frigate topic appears stalled without requiring BirdNET traffic.

        Works for users who don't have BirdNET-Go configured. Only fires when at
        least one Frigate message has been seen this session, so a legitimately
        quiet feeder (zero motion) does not trigger spurious reconnects.
        """
        if not self.running or self.paused:
            return False

        # If Frigate has explicitly confirmed it is online, the feeder is simply
        # quiet — do not treat silence as a stall.
        if self._frigate_confirmed_online():
            return False

        ts = now if now is not None else self._now_monotonic()
        if self._connection_started_monotonic is None:
            return False
        if ts - self._connection_started_monotonic < MQTT_TOPIC_STALL_GRACE_SECONDS:
            return False

        # Require at least one Frigate message; avoids churning when Frigate is quiet
        # or the topic subscription has never delivered a message.
        if self._topic_message_counts.get(frigate_topic, 0) <= 0:
            return False

        frigate_age = self._topic_age_seconds(frigate_topic, ts)
        if frigate_age is None:
            return False
        return frigate_age >= MQTT_FRIGATE_TOPIC_STALE_SECONDS

    def _should_reconnect_for_stalled_frigate_topic(
        self,
        frigate_topic: str,
        birdnet_topic: str,
        now: float | None = None,
    ) -> bool:
        """BirdNET-assisted stall check (higher confidence; used in the message loop)."""
        if not self.running or self.paused:
            return False

        # Availability-gated: if Frigate says it's online, silence = quiet feeder.
        if self._frigate_confirmed_online():
            return False

        ts = now if now is not None else self._now_monotonic()
        if self._connection_started_monotonic is None:
            return False
        if ts - self._connection_started_monotonic < MQTT_TOPIC_STALL_GRACE_SECONDS:
            return False

        # Only evaluate while BirdNET traffic is healthy — guards against false positives
        # when the feeder is genuinely quiet.
        birdnet_age = self._topic_age_seconds(birdnet_topic, ts)
        if birdnet_age is None or birdnet_age > max(10.0, MQTT_FRIGATE_TOPIC_STALE_SECONDS / 2.0):
            return False
        if self._topic_message_counts.get(birdnet_topic, 0) < MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES:
            return False

        # After a stall-triggered reconnect, the next MQTT session can come up
        # without any Frigate traffic at all. If BirdNET remains healthy and we
        # know Frigate traffic has existed earlier in this process, keep the
        # assisted recovery path armed across the reconnect boundary.
        #
        # Cap the number of consecutive no-Frigate reconnects to avoid an
        # endless reconnect loop when Frigate is permanently misconfigured or
        # the topic has genuinely changed.
        if (
            self._topic_message_counts.get(frigate_topic, 0) <= 0
            and self._topic_count_lifetime(frigate_topic) > 0
            and self._last_reconnect_reason in {"frigate_topic_stalled", "frigate_topic_stalled_watchdog"}
            and ts - self._connection_started_monotonic >= MQTT_FRIGATE_TOPIC_STALE_SECONDS
            and self._stall_recovery_consecutive_no_frigate_reconnects < MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS
        ):
            return True

        return self._should_reconnect_independent(frigate_topic, ts)

    async def _wait_for_handler_slot(self):
        wait_started: float | None = None
        try:
            while len(self._in_flight_tasks) >= MQTT_MAX_IN_FLIGHT_MESSAGES and self.running:
                loop = asyncio.get_running_loop()
                if wait_started is None:
                    wait_started = loop.time()
                    self._backlog_wait_started_monotonic = wait_started
                waited = loop.time() - wait_started
                remaining = MAX_HANDLER_WAIT_SECONDS - waited
                if remaining <= 0:
                    self._handler_slot_wait_exhaustions += 1
                    self._last_handler_slot_wait_exhausted_monotonic = loop.time()
                    log.error(
                        "MQTT handler slot wait exceeded maximum; unblocking message loop to prevent stall",
                        waited_seconds=round(waited, 1),
                        in_flight=len(self._in_flight_tasks),
                        limit=MQTT_MAX_IN_FLIGHT_MESSAGES,
                        exhaustion_count=self._handler_slot_wait_exhaustions,
                    )
                    break
                done, _pending = await asyncio.wait(
                    self._in_flight_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=min(5.0, remaining),
                )
                if not done:
                    log.warning(
                        "MQTT handler backlog saturated; waiting for in-flight tasks to drain",
                        in_flight=len(self._in_flight_tasks),
                        limit=MQTT_MAX_IN_FLIGHT_MESSAGES,
                        waited_seconds=round(loop.time() - wait_started, 1),
                    )
                for task in done:
                    self._in_flight_tasks.discard(task)
        finally:
            self._backlog_wait_started_monotonic = None

    def _parse_frigate_payload_meta(self, payload: bytes) -> dict | None:
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            after = data.get("after")
            if not isinstance(after, dict):
                return {
                    "event_id": None,
                    "should_process": False,
                }
            event_type = str(data.get("type") or "new").strip().lower()
            label = str(after.get("label") or "").strip().lower()
            false_positive = bool(after.get("false_positive", False))
            event_id = str(after.get("id") or "").strip()
            should_process = bool(
                label == "bird" and (false_positive or event_type in {"new", "end"})
            )
            return {
                "event_id": event_id or None,
                "should_process": should_process,
            }
        except Exception:
            return None

    async def _dispatch_frigate_message(self, event_processor, payload: bytes):
        async with self._handler_semaphore:
            try:
                await asyncio.wait_for(
                    event_processor.process_mqtt_message(payload),
                    timeout=MQTT_FRIGATE_HANDLER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                meta = self._parse_frigate_payload_meta(payload)
                log.warning(
                    "Frigate MQTT handler timed out",
                    event_id=(meta or {}).get("event_id"),
                    timeout_seconds=MQTT_FRIGATE_HANDLER_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                meta = self._parse_frigate_payload_meta(payload)
                log.error(
                    "Frigate MQTT handler failed",
                    event_id=(meta or {}).get("event_id"),
                    error=str(e),
                )

    async def _dispatch_audio_message(self, event_processor, payload: bytes):
        async with self._handler_semaphore:
            try:
                await asyncio.wait_for(
                    event_processor.process_audio_message(payload),
                    timeout=MQTT_AUDIO_HANDLER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                log.warning(
                    "BirdNET MQTT handler timed out",
                    timeout_seconds=MQTT_AUDIO_HANDLER_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("BirdNET MQTT handler failed", error=str(e))

    def _schedule_frigate_message(
        self,
        event_processor,
        payload: bytes,
        event_id: str | None = None,
    ) -> asyncio.Task:
        if event_id is None:
            meta = self._parse_frigate_payload_meta(payload)
            event_id = (meta or {}).get("event_id")
        event_key = event_id or ""
        previous_task = self._event_task_tails.get(event_key)

        if event_key and previous_task is not None and not previous_task.done():
            if event_key in self._event_pending_payloads:
                self._frigate_messages_superseded += 1
            self._event_pending_payloads[event_key] = payload
            existing_pending = self._event_pending_tasks.get(event_key)
            if existing_pending is not None and not existing_pending.done():
                self._event_tail_depths[event_key] = 2
                self._max_event_tail_depth = max(self._max_event_tail_depth, 2)
                return existing_pending

            async def _run_pending() -> None:
                try:
                    while self.running:
                        current_active = self._event_task_tails.get(event_key)
                        if current_active is not None and not current_active.done():
                            try:
                                await current_active
                            except asyncio.CancelledError:
                                return
                            except Exception:
                                pass

                        next_payload = self._event_pending_payloads.pop(event_key, None)
                        if next_payload is None or not self.running:
                            return

                        followup = create_background_task(
                            self._dispatch_frigate_message(event_processor, next_payload),
                            name=f"mqtt_dispatch_frigate:{event_key or 'unknown'}",
                        )
                        self._frigate_dispatch_count += 1
                        self._track_handler_task(followup, "frigate")
                        self._event_task_tails[event_key] = followup
                        self._event_tail_depths[event_key] = 2
                        self._max_event_tail_depth = max(self._max_event_tail_depth, 2)
                        await followup
                        if event_key not in self._event_pending_payloads:
                            return
                finally:
                    self._event_pending_tasks.pop(event_key, None)
                    if self._event_task_tails.get(event_key) is None or self._event_task_tails.get(event_key).done():
                        self._event_task_tails.pop(event_key, None)
                        self._event_tail_depths.pop(event_key, None)

            pending_task = create_background_task(
                _run_pending(),
                name=f"mqtt_dispatch_frigate_pending:{event_key or 'unknown'}",
            )
            self._event_pending_tasks[event_key] = pending_task
            self._event_tail_depths[event_key] = 2
            self._max_event_tail_depth = max(self._max_event_tail_depth, 2)
            return pending_task

        async def _run():
            if previous_task is not None:
                try:
                    await previous_task
                except asyncio.CancelledError:
                    return
                except Exception:
                    # Prior failures are already logged by task wrapper; continue processing newer state.
                    pass
            if not self.running:
                return
            await self._dispatch_frigate_message(event_processor, payload)

        task_name = f"mqtt_dispatch_frigate:{event_id or 'unknown'}"
        task = create_background_task(_run(), name=task_name)
        self._frigate_dispatch_count += 1
        self._track_handler_task(task, "frigate")

        if event_key:
            depth = 1
            self._event_tail_depths[event_key] = depth
            self._max_event_tail_depth = max(self._max_event_tail_depth, depth)
            self._event_task_tails[event_key] = task

            def _cleanup(done: asyncio.Task, eid: str = event_key) -> None:
                if self._event_task_tails.get(eid) is done and eid not in self._event_pending_tasks:
                    self._event_task_tails.pop(eid, None)
                    self._event_tail_depths.pop(eid, None)

            task.add_done_callback(_cleanup)
        return task

    def _schedule_audio_message(self, event_processor, payload: bytes) -> asyncio.Task:
        active_task = self._audio_active_task
        if active_task is not None and not active_task.done():
            if self._audio_pending_payload is not None:
                self._audio_messages_superseded += 1
            self._audio_pending_payload = payload
            if self._audio_pending_task is not None and not self._audio_pending_task.done():
                return self._audio_pending_task

            async def _run_pending() -> None:
                try:
                    while self.running:
                        current_active = self._audio_active_task
                        if current_active is not None and not current_active.done():
                            try:
                                await current_active
                            except asyncio.CancelledError:
                                return
                            except Exception:
                                pass

                        next_payload = self._audio_pending_payload
                        self._audio_pending_payload = None
                        if next_payload is None or not self.running:
                            return

                        followup = create_background_task(
                            self._dispatch_audio_message(event_processor, next_payload),
                            name="mqtt_dispatch_birdnet",
                        )
                        self._audio_active_task = followup
                        self._audio_dispatch_count += 1
                        self._track_handler_task(followup, "birdnet")
                        await followup
                        if self._audio_pending_payload is None:
                            return
                finally:
                    self._audio_pending_task = None

            self._audio_pending_task = create_background_task(
                _run_pending(),
                name="mqtt_dispatch_birdnet_pending",
            )
            return self._audio_pending_task

        task = create_background_task(
            self._dispatch_audio_message(event_processor, payload),
            name="mqtt_dispatch_birdnet",
        )
        self._audio_active_task = task
        self._audio_dispatch_count += 1
        self._track_handler_task(task, "birdnet")
        return task

    def _sweep_stale_event_task_entries(self) -> None:
        """Remove entries from the in-flight event task dicts whose tasks have
        completed and have no associated pending task.

        The primary cleanup paths (done callbacks and _run_pending finally blocks)
        handle the normal case. This sweep is a safety net for the edge case where
        a followup task created inside _run_pending completes but _run_pending
        itself was cancelled before it could clean up the tail entry.
        """
        stale_keys = [
            eid for eid, task in list(self._event_task_tails.items())
            if task.done() and eid not in self._event_pending_tasks
        ]
        for eid in stale_keys:
            self._event_task_tails.pop(eid, None)
            self._event_tail_depths.pop(eid, None)

    async def _connection_watchdog(self, client, frigate_topic: str) -> None:
        """Periodic watchdog that forces reconnection when the Frigate topic stalls.

        Runs independently of BirdNET, so visual-only deployments also get
        self-healing behaviour when Frigate stops publishing events.
        """
        while self.running:
            await asyncio.sleep(MQTT_WATCHDOG_INTERVAL_SECONDS)
            self._sweep_stale_event_task_entries()
            now = self._now_monotonic()
            # _should_reconnect_independent returns False when Frigate is confirmed
            # online via frigate/available — no explicit guard needed here.
            if self._should_reconnect_independent(frigate_topic, now):
                self._note_stall_reconnect(
                    reason="frigate_topic_stalled_watchdog",
                    now=now,
                    frigate_topic=frigate_topic,
                    birdnet_topic=settings.frigate.audio_topic,
                    no_frigate_after_previous_reconnect=False,
                )
                log.warning(
                    "Watchdog: Frigate topic stalled; forcing MQTT reconnection",
                    frigate_silence_seconds=round(
                        self._topic_age_seconds(frigate_topic, now) or 0.0, 1
                    ),
                    frigate_messages_seen=self._topic_message_counts.get(frigate_topic, 0),
                    stale_threshold_seconds=MQTT_FRIGATE_TOPIC_STALE_SECONDS,
                )
                self._intentional_reconnect = True
                with contextlib.suppress(Exception):
                    await client.disconnect()
                return

    def _cancel_in_flight_tasks(self):
        for task in list(self._in_flight_tasks):
            task.cancel()
        self._in_flight_tasks.clear()
        self._task_kind_by_id.clear()
        self._event_task_tails.clear()
        self._event_tail_depths.clear()
        for task in list(self._event_pending_tasks.values()):
            task.cancel()
        self._event_pending_tasks.clear()
        self._event_pending_payloads.clear()
        self._audio_active_task = None
        self._audio_pending_payload = None
        if self._audio_pending_task is not None:
            self._audio_pending_task.cancel()
        self._audio_pending_task = None

    async def start(self, event_processor):
        self.running = True

        # Validate MQTT settings
        if not settings.frigate.mqtt_server:
            log.error("MQTT server not configured. Set FRIGATE__MQTT_SERVER environment variable.")
            return
            
        log.info("Starting MQTT Service", client_id=self.client_id)

        while self.running:
            try:
                # Only pass credentials if auth is enabled and credentials are provided
                client_kwargs = {
                    "hostname": settings.frigate.mqtt_server,
                    "port": settings.frigate.mqtt_port,
                    "identifier": self.client_id
                }
                if settings.frigate.mqtt_auth and settings.frigate.mqtt_username:
                    client_kwargs["username"] = settings.frigate.mqtt_username
                    client_kwargs["password"] = settings.frigate.mqtt_password

                async with Client(**client_kwargs) as client:
                    self.client = client

                    # Frigate Topic
                    frigate_topic = f"{settings.frigate.main_topic}/events"
                    await client.subscribe(frigate_topic)

                    # BirdNET Topic (BirdNET-Go default)
                    birdnet_topic = settings.frigate.audio_topic
                    await client.subscribe(birdnet_topic)

                    # Frigate Availability Topic (liveness heartbeat — retained, online/offline)
                    availability_topic = f"{settings.frigate.main_topic}/available"
                    await client.subscribe(availability_topic)

                    self._connection_started_monotonic = self._now_monotonic()
                    self._topic_last_message_monotonic = {}
                    self._topic_message_counts = {
                        frigate_topic: 0,
                        birdnet_topic: 0,
                    }
                    self._backlog_wait_started_monotonic = None
                    self._audio_active_task = None
                    self._audio_pending_payload = None
                    self._audio_pending_task = None
                    self._frigate_availability = None
                    self._frigate_availability_monotonic = None

                    log.info("Connected to MQTT", topics=[frigate_topic, birdnet_topic, availability_topic])

                    # Reset backoff on successful connection
                    self._reset_backoff()

                    watchdog_task = create_background_task(
                        self._connection_watchdog(client, frigate_topic),
                        name="mqtt_connection_watchdog",
                    )
                    try:
                        async for message in client.messages:
                            # Watchdog requested a reconnect; bail out of the loop cleanly.
                            if self._intentional_reconnect:
                                break
                            if self.paused:
                                continue
                            # Check for topic changes in settings
                            if settings.frigate.audio_topic != birdnet_topic:
                                log.info("MQTT Audio topic changed in settings, reconnecting...",
                                         old=birdnet_topic, new=settings.frigate.audio_topic)
                                self._last_reconnect_reason = "audio_topic_changed"
                                break  # This breaks the 'async for', causing a reconnection with new settings

                            topic = message.topic.value
                            if topic == availability_topic:
                                self._handle_frigate_availability(message.payload)
                                continue
                            self._record_topic_message(topic)
                            if topic == frigate_topic:
                                log.info("Received MQTT message on frigate topic", payload_len=len(message.payload))
                                meta = self._parse_frigate_payload_meta(message.payload)
                                if meta is not None and not meta.get("should_process", False):
                                    continue
                                await self._wait_for_handler_slot()
                                self._schedule_frigate_message(
                                    event_processor,
                                    message.payload,
                                    event_id=(meta or {}).get("event_id"),
                                )
                            elif topic == birdnet_topic:
                                log.info("Received MQTT message on birdnet topic", payload_len=len(message.payload))
                                await self._wait_for_handler_slot()
                                self._schedule_audio_message(event_processor, message.payload)
                                now = self._now_monotonic()
                                no_frigate_after_previous_reconnect = bool(
                                    self._topic_message_counts.get(frigate_topic, 0) <= 0
                                    and self._topic_count_lifetime(frigate_topic) > 0
                                    and self._last_reconnect_reason in {"frigate_topic_stalled", "frigate_topic_stalled_watchdog"}
                                    and self._connection_started_monotonic is not None
                                    and now - self._connection_started_monotonic >= MQTT_FRIGATE_TOPIC_STALE_SECONDS
                                )
                                if self._should_reconnect_for_stalled_frigate_topic(
                                    frigate_topic=frigate_topic,
                                    birdnet_topic=birdnet_topic,
                                    now=now,
                                ):
                                    should_reconnect = self._note_stall_reconnect(
                                        reason="frigate_topic_stalled",
                                        now=now,
                                        frigate_topic=frigate_topic,
                                        birdnet_topic=birdnet_topic,
                                        no_frigate_after_previous_reconnect=no_frigate_after_previous_reconnect,
                                    )
                                    if not should_reconnect:
                                        log.warning(
                                            "Frigate topic recovery reached the configured reconnect cap; remaining connected without further forced reconnects",
                                            consecutive_reconnects_without_frigate=self._stall_recovery_consecutive_no_frigate_reconnects,
                                            max_consecutive_reconnects=MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS,
                                        )
                                        continue
                                    if no_frigate_after_previous_reconnect:
                                        log.warning(
                                            "Frigate topic still absent after prior stall recovery; reconnecting MQTT session again",
                                            frigate_silence_seconds=round(MQTT_FRIGATE_TOPIC_STALE_SECONDS, 1),
                                            birdnet_last_message_seconds_ago=round(
                                                self._topic_age_seconds(birdnet_topic, now) or 0.0, 1
                                            ),
                                            birdnet_messages_seen=self._topic_message_counts.get(birdnet_topic, 0),
                                            consecutive_reconnects_without_frigate=self._stall_recovery_consecutive_no_frigate_reconnects,
                                            stale_threshold_seconds=MQTT_FRIGATE_TOPIC_STALE_SECONDS,
                                        )
                                    else:
                                        log.warning(
                                            "Frigate topic appears stalled while BirdNET remains active; reconnecting MQTT session",
                                            frigate_silence_seconds=round(
                                                self._topic_age_seconds(frigate_topic, now) or 0.0, 1
                                            ),
                                            birdnet_last_message_seconds_ago=round(
                                                self._topic_age_seconds(birdnet_topic, now) or 0.0, 1
                                            ),
                                            birdnet_messages_seen=self._topic_message_counts.get(birdnet_topic, 0),
                                            frigate_messages_seen=self._topic_message_counts.get(frigate_topic, 0),
                                            stale_threshold_seconds=MQTT_FRIGATE_TOPIC_STALE_SECONDS,
                                        )
                                    break
                        self.client = None
                    finally:
                        watchdog_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await watchdog_task
                    if self._intentional_reconnect:
                        self._intentional_reconnect = False
                        log.info("MQTT session ended by stall-recovery watchdog; reconnecting immediately")
                        continue
                            
            except MqttError as e:
                self.client = None
                if self._intentional_reconnect:
                    self._intentional_reconnect = False
                    log.info("MQTT session ended by stall-recovery watchdog; reconnecting immediately")
                    continue
                delay = self._calculate_backoff()
                log.error("MQTT connection lost, retrying...",
                         error=str(e),
                         retry_delay=f"{delay:.1f}s",
                         backoff_level=self.reconnect_delay)
                await asyncio.sleep(delay)
                self._increase_backoff()
            except Exception as e:
                self.client = None
                self._intentional_reconnect = False
                delay = self._calculate_backoff()
                log.error("Unexpected error in MQTT service, retrying...",
                         error=str(e),
                         retry_delay=f"{delay:.1f}s",
                         backoff_level=self.reconnect_delay)
                await asyncio.sleep(delay)
                self._increase_backoff()

    async def publish(self, topic: str, payload: dict | str) -> bool:
        """Publish a message to a specific topic."""
        if not self.client:
            log.warning("Cannot publish - MQTT client not connected")
            return False
            
        try:
            import json
            if isinstance(payload, dict):
                payload = json.dumps(payload)
                
            await self.client.publish(topic, payload)
            log.info("Published MQTT message", topic=topic)
            return True
        except Exception as e:
            log.error("Failed to publish message", topic=topic, error=str(e))
            return False

    async def stop(self):
        self.running = False
        self._cancel_in_flight_tasks()
        self.client = None
        self._connection_started_monotonic = None
        self._topic_last_message_monotonic = {}
        self._topic_message_counts = {}
        self._topic_message_counts_lifetime = {}
        self._stall_recovery_consecutive_no_frigate_reconnects = 0
        self._backlog_wait_started_monotonic = None
        self._frigate_availability = None
        self._frigate_availability_monotonic = None

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

mqtt_service = MQTTService()
