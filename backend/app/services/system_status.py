"""One status snapshot for every owner screen, pushed over the live stream when it changes.

The derivation is a pure function of the readings passed in (`derive_system_status`), so what a
verdict says for a given state is tested without a broker, Frigate or a model. The service around
it collects those readings while someone is connected, publishes a `status` event when anything
material changes, and refreshes the snapshot's figures (telemetry, camera rates) at a slow cadence
otherwise. Pages read this instead of polling the endpoints it summarises.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from app.utils.diagnostic_redaction import redact_connection_error

from app.models.analysis_status import AnalysisStatusResponse
from app.models.jobs import JobsSnapshotResponse
from app.models.service_connections import ServiceConnectionsResponse
from app.models.system_status import (
    CameraHealthReading,
    JobsProgress,
    JobsSummary,
    ModelState,
    OverallVerdict,
    SubsystemKey,
    SubsystemVerdict,
    SystemStatusSnapshot,
    TelemetrySummary,
)

log = structlog.get_logger()

STATUS_EVENT_TYPE = "status"

# Kinds the jobs view files under routine work: they run all day and are not announced in the banner.
ROUTINE_JOB_KINDS = frozenset({"auto_video", "high_quality_snapshot", "full_visit", "favorite_archive"})
_RUNNING_JOB_STATUSES = frozenset({"running", "stale"})
_QUEUED_JOB_STATUSES = frozenset({"queued", "retrying"})

# The order an owner should fix things in: nothing arrives without the broker, nothing is saved
# without Frigate or a writable media folder, nothing is named without the model.
_FIX_ORDER: tuple[SubsystemKey, ...] = (
    "mqtt",
    "frigate",
    "storage",
    "classifier",
    "finder",
    "notifications",
    "audio",
)


@dataclass(frozen=True)
class SystemStatusInputs:
    """Every reading the snapshot is derived from, already taken."""

    startup_instance_id: str
    connections: ServiceConnectionsResponse
    jobs: JobsSnapshotResponse
    analysis: AnalysisStatusResponse
    mqtt_health: dict[str, Any] = field(default_factory=dict)
    classifier_health: dict[str, Any] = field(default_factory=dict)
    classifier_status: dict[str, Any] = field(default_factory=dict)
    provider_validation_state: str = "idle"
    media_storage_available: bool = True
    notification_channels_enabled: int = 0
    notification_dropped_jobs: int = 0
    birdnet_enabled: bool = False
    event_pipeline: dict[str, Any] | None = None
    db_pool_degraded: bool = False
    startup_warning_count: int = 0
    cameras: CameraHealthReading | None = None
    telemetry: TelemetrySummary | None = None
    diagnostics_revision: int = 0
    version: str = "unknown"
    # The health the incident workspace judges stateful incidents from (`ml`, as `/health` reports it).
    incident_health: dict[str, Any] = field(default_factory=dict)
    # Configured secret values; free text in the snapshot is cleaned of them and of credential forms.
    secrets: tuple[str, ...] = ()


def _mqtt_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    state = inputs.connections.mqtt.state
    if state == "connecting":
        return SubsystemVerdict(key="mqtt", state="unknown", cause="connecting")
    if state != "connected":
        return SubsystemVerdict(key="mqtt", state="error", cause=state)
    health = inputs.mqtt_health
    pressure = str(health.get("pressure_level") or "").lower()
    if pressure in {"high", "critical"}:
        return SubsystemVerdict(key="mqtt", state="degraded", cause=f"pressure_{pressure}")
    if health.get("backlog_wait_active") or health.get("recent_handler_slot_wait_exhaustion"):
        return SubsystemVerdict(key="mqtt", state="degraded", cause="backlog")
    if health.get("stall_recovery_warning_active"):
        return SubsystemVerdict(key="mqtt", state="degraded", cause="frigate_topic_silent")
    return SubsystemVerdict(key="mqtt", state="ok", cause="connected")


def _frigate_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    state = inputs.connections.frigate.state
    if state == "unreachable":
        return SubsystemVerdict(key="frigate", state="error", cause="unreachable")
    if state == "unchecked":
        return SubsystemVerdict(key="frigate", state="unknown", cause="unchecked")
    cameras = inputs.cameras.cameras if inputs.cameras else []
    if any(camera.status == "offline" for camera in cameras):
        return SubsystemVerdict(key="frigate", state="degraded", cause="cameras_offline")
    return SubsystemVerdict(key="frigate", state="ok", cause="reachable")


def _finder_health(inputs: SystemStatusInputs) -> dict[str, Any]:
    finder = inputs.classifier_health.get("bird_finder")
    return finder if isinstance(finder, dict) else {}


def _classifier_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    health = inputs.classifier_health
    if not health:
        return SubsystemVerdict(key="classifier", state="unknown", cause="unmeasured")
    status = str(health.get("status") or "").lower()
    live = health.get("live_image") if isinstance(health.get("live_image"), dict) else {}
    if status == "error":
        bird = (health.get("models") or {}).get("bird") if isinstance(health.get("models"), dict) else None
        if isinstance(bird, dict) and bird.get("loaded") is False:
            return SubsystemVerdict(key="classifier", state="error", cause="model_not_loaded")
        return SubsystemVerdict(key="classifier", state="error", cause="runtime_failed")
    if live.get("recovery_active"):
        return SubsystemVerdict(key="classifier", state="degraded", cause="recovering")
    live_status = str(live.get("status") or "").lower()
    if live_status not in {"", "ok", "healthy"}:
        return SubsystemVerdict(key="classifier", state="degraded", cause="live_degraded")
    # A finder on the CPU degrades the classifier's own status; that is the finder's verdict.
    if status == "degraded" and not _finder_health(inputs).get("active"):
        return SubsystemVerdict(key="classifier", state="degraded", cause="degraded")
    return SubsystemVerdict(key="classifier", state="ok", cause="ready")


def _finder_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    finder = _finder_health(inputs)
    if not inputs.classifier_health:
        return SubsystemVerdict(key="finder", state="unknown", cause="unmeasured")
    if finder.get("active"):
        return SubsystemVerdict(key="finder", state="degraded", cause="cpu_fallback")
    if not str(finder.get("model_id") or ""):
        return SubsystemVerdict(key="finder", state="off", cause="none_selected")
    return SubsystemVerdict(key="finder", state="ok", cause="ready")


def _audio_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    if not inputs.birdnet_enabled:
        return SubsystemVerdict(key="audio", state="off", cause="disabled")
    if inputs.connections.mqtt.state != "connected":
        return SubsystemVerdict(key="audio", state="unknown", cause="broker_down")
    counts = inputs.mqtt_health.get("topic_message_counts")
    heard = int(counts.get("birdnet") or 0) if isinstance(counts, dict) else 0
    if heard > 0:
        return SubsystemVerdict(key="audio", state="ok", cause="hearing")
    # Silence since start is not a fault: BirdNET-Go may simply have heard nothing yet.
    return SubsystemVerdict(key="audio", state="unknown", cause="nothing_heard")


def _storage_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    if not inputs.media_storage_available:
        return SubsystemVerdict(key="storage", state="error", cause="not_writable")
    return SubsystemVerdict(key="storage", state="ok", cause="writable")


def _notifications_verdict(inputs: SystemStatusInputs) -> SubsystemVerdict:
    if inputs.notification_channels_enabled <= 0:
        return SubsystemVerdict(key="notifications", state="off", cause="none_enabled")
    if inputs.notification_dropped_jobs > 0:
        return SubsystemVerdict(key="notifications", state="degraded", cause="dropped")
    return SubsystemVerdict(key="notifications", state="ok", cause="ready")


def _overall_verdict(inputs: SystemStatusInputs, subsystems: list[SubsystemVerdict]) -> OverallVerdict:
    """The same judgement `/health` makes, with the first thing to fix named."""
    by_key = {verdict.key: verdict for verdict in subsystems}
    for key in _FIX_ORDER:
        verdict = by_key[key]
        if verdict.state == "error":
            return OverallVerdict(state="degraded", cause=verdict.cause, subsystem=key)
    pipeline = inputs.event_pipeline or {}
    if pipeline.get("critical_failure_active"):
        return OverallVerdict(state="degraded", cause="pipeline_critical")
    for key in _FIX_ORDER:
        verdict = by_key[key]
        if verdict.state == "degraded":
            return OverallVerdict(state="degraded", cause=verdict.cause, subsystem=key)
    if inputs.event_pipeline is not None and str(pipeline.get("status") or "") != "ok":
        return OverallVerdict(state="degraded", cause="pipeline_degraded")
    if inputs.db_pool_degraded:
        return OverallVerdict(state="degraded", cause="database_slow")
    if inputs.startup_warning_count > 0:
        return OverallVerdict(state="degraded", cause="startup_warnings")
    # A connection nobody has measured is not counted as fine.
    for key in ("mqtt", "frigate"):
        if by_key[key].state == "unknown":
            return OverallVerdict(state="unknown", cause=by_key[key].cause, subsystem=key)
    return OverallVerdict(state="ok", cause="ok")


def summarise_jobs(jobs: JobsSnapshotResponse) -> JobsSummary:
    """One count of prominent work. The lanes count every item, the items carry the progress."""
    prominent_lanes = [lane for lane in jobs.lanes if lane.kind not in ROUTINE_JOB_KINDS]
    running = sum(lane.running for lane in prominent_lanes)
    queued = sum(lane.queued for lane in prominent_lanes)
    running_items = [
        item for item in jobs.items if item.visibility == "prominent" and item.status in _RUNNING_JOB_STATUSES
    ]
    progress: JobsProgress | None = None
    # A bar over different kinds or units would add unlike things, so none is drawn for them.
    if running_items and len(running_items) == running:
        kinds = {item.kind for item in running_items}
        units = {item.unit for item in running_items}
        if len(kinds) == 1 and len(units) == 1 and all(item.total > 0 for item in running_items):
            total = sum(item.total for item in running_items)
            current = sum(min(item.current, item.total) for item in running_items)
            progress = JobsProgress(current=current, total=total, unit=running_items[0].unit)
    return JobsSummary(running=running, queued=queued, progress=progress)


def _normalised_provider(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return "cpu" if text == "tflite" else text


def _model_state(inputs: SystemStatusInputs, classifier: SubsystemVerdict) -> ModelState:
    status = inputs.classifier_status
    selected = _normalised_provider(status.get("selected_provider"))
    active = _normalised_provider(status.get("active_provider"))
    fallback_reason = _clean(str(status.get("fallback_reason") or "").strip() or None, inputs.secrets)
    enabled = bool(status.get("enabled", False))
    # The Dashboard's warning rule: only a resident model reports `enabled`, and only then is a
    # mismatch between the chosen and the running provider worth saying.
    provider_fallback = enabled and (
        fallback_reason is not None or bool(selected and selected != "auto" and active and active != selected)
    )
    quarantine = status.get("native_runtime_quarantine")
    quarantine = quarantine if isinstance(quarantine, dict) else {}
    model_id = str(status.get("effective_model_id") or status.get("active_model_id") or "").strip() or None
    model_name = str(status.get("effective_model_name") or "").strip() or None
    fingerprint = json.dumps(
        [
            model_id,
            status.get("active_model_id"),
            model_name,
            selected,
            active,
            status.get("inference_backend"),
            status.get("image_execution_mode"),
            status.get("runtime_source"),
            fallback_reason,
            quarantine.get("status"),
            quarantine.get("restart_recommended"),
            status.get("resolved_live_workers"),
            status.get("resolved_background_workers"),
            inputs.provider_validation_state,
            classifier.state,
            classifier.cause,
        ],
        sort_keys=True,
        default=str,
    )
    return ModelState(
        state=classifier.state,
        cause=classifier.cause,
        model_id=model_id,
        model_name=model_name,
        enabled=enabled,
        selected_provider=selected,
        active_provider=active,
        provider_fallback=provider_fallback,
        fallback_reason=fallback_reason,
        validation_state=inputs.provider_validation_state,
        revision=hashlib.sha256(fingerprint.encode()).hexdigest()[:16],
    )


def _clean(text: str | None, secrets: tuple[str, ...]) -> str | None:
    return redact_connection_error(text, secrets)[:2048] if text else text


def _redacted_jobs(jobs: JobsSnapshotResponse, secrets: tuple[str, ...]) -> JobsSnapshotResponse:
    items = [
        item.model_copy(update={"phase": _clean(item.phase, secrets) or "", "error": _clean(item.error, secrets)})
        for item in jobs.items
    ]
    return jobs.model_copy(update={"items": items})


def _redacted_analysis(analysis: AnalysisStatusResponse, secrets: tuple[str, ...]) -> AnalysisStatusResponse:
    # The model allows fields it does not declare, so every text value is cleaned, not a known few.
    values = analysis.model_dump()
    return AnalysisStatusResponse.model_validate(
        {name: _clean(value, secrets) if isinstance(value, str) else value for name, value in values.items()}
    )


# The pipeline's running totals: Health shows them, an incident never depends on them.
_PIPELINE_COUNTERS = (
    "started_events",
    "completed_events",
    "dropped_events",
    "incomplete_events",
    "critical_failures",
)
# The health values the incident workspace resolves a stateful incident from
# (`apps/ui/src/lib/stores/incident-signals.ts` holds the same list, and a test keeps the two
# equal). A breaker closing or a queue draining records no new fault, so these, not the fault
# history, are what lets an incident close: each one is part of the incident revision.
INCIDENT_SIGNAL_PATHS: tuple[str, ...] = (
    "video_classifier.circuit_open",
    "ml.bird_finder.active",
    "ml.live_image.recovery_active",
    "ml.background_image.background_throttled",
    "ml.background_image.queued",
    "ml.worker_pools.live.circuit_open",
    "ml.worker_pools.background.circuit_open",
)


def _read_path(tree: object, path: str) -> object:
    for part in path.split("."):
        if not isinstance(tree, dict):
            return None
        tree = tree.get(part)
    return tree if isinstance(tree, (bool, int, float, str)) or tree is None else str(tree)


def incident_signals(inputs: SystemStatusInputs) -> dict[str, object]:
    """Each incident signal's current value, read from the same health the workspace reports."""
    health = {"video_classifier": inputs.analysis.model_dump(), **inputs.incident_health}
    return {path: _read_path(health, path) for path in INCIDENT_SIGNAL_PATHS}


def _fingerprint(parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _incident_revision(inputs: SystemStatusInputs, overall: OverallVerdict, subsystems: list[SubsystemVerdict]) -> str:
    """Moves whenever an incident can open or close: a verdict, a recorded fault, a stateful signal."""
    pipeline = inputs.event_pipeline or {}
    return _fingerprint(
        [
            overall.model_dump(),
            [verdict.model_dump() for verdict in subsystems],
            incident_signals(inputs),
            pipeline.get("status"),
            bool(pipeline.get("critical_failure_active")),
            inputs.diagnostics_revision,
            inputs.startup_warning_count,
            inputs.db_pool_degraded,
            inputs.notification_dropped_jobs,
        ]
    )


def _health_revision(inputs: SystemStatusInputs, incident_revision: str) -> str:
    """Everything Health shows that moves: the incidents, and the pipeline's running totals."""
    pipeline = inputs.event_pipeline or {}
    return _fingerprint([incident_revision, {name: pipeline.get(name) for name in _PIPELINE_COUNTERS}])


def derive_system_status(inputs: SystemStatusInputs, *, revision: int, now: datetime) -> SystemStatusSnapshot:
    """The snapshot every owner screen reads, from readings already taken.

    Every free-text field (a job's phase and error, the queue's status message, the provider's
    fallback reason) is redacted here, so nothing a client raised reaches a page with a credential in it.
    """
    subsystems = [
        _mqtt_verdict(inputs),
        _frigate_verdict(inputs),
        _classifier_verdict(inputs),
        _finder_verdict(inputs),
        _audio_verdict(inputs),
        _storage_verdict(inputs),
        _notifications_verdict(inputs),
    ]
    classifier = next(verdict for verdict in subsystems if verdict.key == "classifier")
    overall = _overall_verdict(inputs, subsystems)
    incident_revision = _incident_revision(inputs, overall, subsystems)
    return SystemStatusSnapshot(
        revision=revision,
        generated_at=now.astimezone(timezone.utc).isoformat(),
        startup_instance_id=inputs.startup_instance_id,
        version=inputs.version,
        overall=overall,
        subsystems=subsystems,
        jobs_summary=summarise_jobs(inputs.jobs),
        jobs=_redacted_jobs(inputs.jobs, inputs.secrets),
        analysis=_redacted_analysis(inputs.analysis, inputs.secrets),
        model=_model_state(inputs, classifier),
        connections=inputs.connections,
        cameras=inputs.cameras,
        telemetry=inputs.telemetry,
        diagnostics_revision=inputs.diagnostics_revision,
        incident_revision=incident_revision,
        health_revision=_health_revision(inputs, incident_revision),
    )


_ANALYSIS_MATERIAL_FIELDS = (
    "status",
    "pending",
    "active",
    "circuit_open",
    "open_until",
    "pending_maintenance",
    "active_maintenance",
    "maintenance_state",
    "throttled_for_live_pressure",
    "throttled_for_mqtt_pressure",
    "live_pressure_active",
    "mqtt_pressure_level",
)


def material_key(snapshot: SystemStatusSnapshot) -> str:
    """What a change worth pushing at once is measured against.

    Timestamps, ages, frame rates and telemetry move every few seconds without anything an owner
    would act on; they travel with the next push instead of causing one.
    """
    connections = snapshot.connections
    analysis = snapshot.analysis.model_dump()
    material = {
        "instance": snapshot.startup_instance_id,
        "version": snapshot.version,
        "overall": snapshot.overall.model_dump(),
        "subsystems": [verdict.model_dump() for verdict in snapshot.subsystems],
        "jobs_summary": snapshot.jobs_summary.model_dump(),
        "jobs": [(item.id, item.status, item.phase, item.current, item.total) for item in snapshot.jobs.items],
        "lanes": [lane.model_dump() for lane in snapshot.jobs.lanes],
        "analysis": {name: analysis.get(name) for name in _ANALYSIS_MATERIAL_FIELDS},
        "model": snapshot.model.model_dump(),
        "mqtt": (connections.mqtt.state, connections.mqtt.last_error_cause),
        "frigate": (connections.frigate.state, connections.frigate.last_failure, connections.frigate.availability),
        "cameras": [(camera.camera, camera.status) for camera in snapshot.cameras.cameras]
        if snapshot.cameras
        else None,
        "diagnostics": snapshot.diagnostics_revision,
        "incident": snapshot.incident_revision,
    }
    return json.dumps(material, sort_keys=True, default=str)


def should_publish(
    *,
    previous_key: str | None,
    key: str,
    seconds_since_publish: float | None,
    refresh_after_seconds: float,
) -> bool:
    """Push a material change at once, and otherwise refresh the figures at a slow cadence."""
    if previous_key is None or seconds_since_publish is None:
        return True
    if key != previous_key:
        return True
    return seconds_since_publish >= refresh_after_seconds


def status_event(snapshot: SystemStatusSnapshot) -> dict[str, Any]:
    return {"type": STATUS_EVENT_TYPE, "data": snapshot.model_dump(mode="json")}


class SystemStatusService:
    """Collects the readings while anyone is connected and publishes the snapshot when it changes."""

    def __init__(
        self,
        *,
        collect: Callable[[], Awaitable[SystemStatusInputs]],
        publish: Callable[[dict[str, Any]], Awaitable[None]],
        has_subscribers: Callable[[], bool],
        interval_seconds: float = 5.0,
        min_gap_seconds: float = 1.0,
        refresh_after_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._collect = collect
        self._publish = publish
        self._has_subscribers = has_subscribers
        self._interval = interval_seconds
        self._min_gap = min_gap_seconds
        self._refresh_after = refresh_after_seconds
        self._clock = clock
        self._wall_clock = wall_clock
        self._revision = 0
        self._latest: SystemStatusSnapshot | None = None
        self._latest_at: float | None = None
        self._published_key: str | None = None
        self._published_at: float | None = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def latest(self) -> SystemStatusSnapshot | None:
        return self._latest

    async def _snapshot_now(self) -> SystemStatusSnapshot:
        inputs = await self._collect()
        candidate = derive_system_status(inputs, revision=self._revision + 1, now=self._wall_clock())
        if self._latest is None or material_key(candidate) != material_key(self._latest):
            self._revision += 1
        else:
            candidate = candidate.model_copy(update={"revision": self._revision})
        self._latest = candidate
        self._latest_at = self._clock()
        return candidate

    async def current(self, *, max_age_seconds: float = 5.0) -> SystemStatusSnapshot:
        """The latest snapshot, read again when it is older than `max_age_seconds`."""
        async with self._lock:
            if self._latest is not None and self._latest_at is not None:
                if self._clock() - self._latest_at <= max_age_seconds:
                    return self._latest
            return await self._snapshot_now()

    async def refresh_once(self) -> SystemStatusSnapshot | None:
        """Take a reading and publish it if it changed or the figures are due; returns what was published."""
        async with self._lock:
            snapshot = await self._snapshot_now()
            key = material_key(snapshot)
            since = None if self._published_at is None else self._clock() - self._published_at
            if not should_publish(
                previous_key=self._published_key,
                key=key,
                seconds_since_publish=since,
                refresh_after_seconds=self._refresh_after,
            ):
                return None
            self._published_key = key
            self._published_at = self._clock()
        await self._publish(status_event(snapshot))
        return snapshot

    def request_refresh(self, message: dict[str, Any] | None = None) -> None:
        """Something changed elsewhere; read again soon rather than at the next tick."""
        if message is not None and message.get("type") in {STATUS_EVENT_TYPE, "heartbeat"}:
            return
        self._wake.set()

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            if not self._running:
                return
            if not self._has_subscribers():
                continue
            try:
                await self.refresh_once()
            except Exception as exc:  # noqa: BLE001 - a failed reading must not stop the next one
                log.warning("system_status_refresh_failed", error=str(exc))
            # Bursts of announcements are folded into one reading.
            await asyncio.sleep(self._min_gap)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="system_status")

    async def stop(self) -> None:
        self._running = False
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
