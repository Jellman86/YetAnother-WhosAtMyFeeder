"""Takes the readings the status snapshot is derived from.

Everything here is already measured elsewhere and cheap to read, except two things that are
cached: Frigate's camera stats (a request to Frigate) and the saved photograph jobs (a database
read). Those are taken at most once a minute and every half minute respectively, however often
the snapshot is refreshed.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import structlog

from app.config import settings
from app.models.system_status import CameraHealthReading, TelemetrySummary
from app.services.analysis_status import build_analysis_status
from app.services.error_diagnostics import error_diagnostics_history
from app.services.frigate_camera_health import read_camera_health
from app.services.jobs_snapshot import build_jobs_snapshot
from app.services.service_connections import collect_service_connections
from app.services.system_status import SystemStatusInputs
from app.services.system_telemetry import system_telemetry_history
from app.utils.diagnostic_redaction import configured_secrets, redact_connection_error

log = structlog.get_logger()

CAMERA_HEALTH_MAX_AGE_SECONDS = 60.0
SAVED_JOBS_MAX_AGE_SECONDS = 30.0
STATUS_JOBS_LIMIT = 100


def enabled_notification_channels() -> int:
    channels = settings.notifications
    return sum(
        1 for channel in (channels.discord, channels.pushover, channels.telegram, channels.email) if channel.enabled
    )


def latest_telemetry() -> TelemetrySummary | None:
    snapshot = system_telemetry_history.snapshot()
    if not snapshot.points:
        return None
    point = snapshot.points[-1]
    kind = snapshot.accelerator_kind if snapshot.accelerator_kind in ("npu", "gpu") else None
    return TelemetrySummary(
        sampled_at=point.at,
        cpu_percent=point.cpu_percent,
        accelerator_percent=point.accelerator_percent,
        accelerator_kind=kind,
        accelerator_label=snapshot.accelerator_label if kind else None,
    )


class SystemStatusReadings:
    """The collector the status service calls; app-level readings are passed in by `main`."""

    def __init__(
        self,
        *,
        startup_instance_id: Callable[[], str],
        version: str,
        startup_warning_count: Callable[[], int],
        event_pipeline_status: Callable[[], dict[str, Any] | None],
        db_pool_degraded: Callable[[], bool],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._startup_instance_id = startup_instance_id
        self._version = version
        self._startup_warning_count = startup_warning_count
        self._event_pipeline_status = event_pipeline_status
        self._db_pool_degraded = db_pool_degraded
        self._clock = clock
        self._cameras: CameraHealthReading | None = None
        self._cameras_read_at: float | None = None
        self._saved_jobs: list[dict[str, object]] | None = None
        self._saved_jobs_read_at: float | None = None

    def _due(self, read_at: float | None, max_age: float) -> bool:
        return read_at is None or self._clock() - read_at >= max_age

    async def _camera_health(self) -> CameraHealthReading | None:
        if not (settings.frigate.frigate_url or "").strip():
            self._cameras = None
            return None
        if self._due(self._cameras_read_at, CAMERA_HEALTH_MAX_AGE_SECONDS):
            self._cameras_read_at = self._clock()
            try:
                self._cameras = await read_camera_health()
            except Exception as exc:  # noqa: BLE001 - an unanswered request is Frigate's verdict, not ours
                # A reading that failed is not kept: cameras Frigate did not report are unmeasured.
                self._cameras = None
                log.debug(
                    "system_status_camera_health_failed",
                    error=redact_connection_error(str(exc), configured_secrets()),
                )
        return self._cameras

    async def _saved_high_quality_jobs(self) -> list[dict[str, object]]:
        if self._saved_jobs is None or self._due(self._saved_jobs_read_at, SAVED_JOBS_MAX_AGE_SECONDS):
            from app.services.high_quality_snapshot_service import high_quality_snapshot_service

            self._saved_jobs = await high_quality_snapshot_service.get_saved_jobs_snapshot()
            self._saved_jobs_read_at = self._clock()
        return self._saved_jobs

    async def collect(self) -> SystemStatusInputs:
        from app.services.classifier_service import get_classifier
        from app.services.media_cache import media_cache
        from app.services.mqtt_service import mqtt_service
        from app.services.notification_dispatcher import notification_dispatcher
        from app.services.provider_revalidation import provider_revalidation

        connections = await collect_service_connections(refresh_frigate=True)
        classifier = get_classifier()
        # Both build their answer from in-memory state, but they are not free; keep them off the loop.
        classifier_health, classifier_status = await asyncio.gather(
            asyncio.to_thread(classifier.check_health),
            asyncio.to_thread(classifier.get_status),
        )
        jobs = await build_jobs_snapshot(
            include_routine=True,
            limit=STATUS_JOBS_LIMIT,
            saved_high_quality_jobs=await self._saved_high_quality_jobs(),
        )
        dispatcher = notification_dispatcher.get_status()
        validation = provider_revalidation.status()
        return SystemStatusInputs(
            startup_instance_id=self._startup_instance_id(),
            connections=connections,
            jobs=jobs,
            analysis=build_analysis_status(),
            mqtt_health=mqtt_service.get_status(),
            classifier_health=classifier_health,
            classifier_status=classifier_status,
            provider_validation_state=str(validation.get("state") or "idle"),
            media_storage_available=bool(media_cache.available),
            notification_channels_enabled=enabled_notification_channels(),
            notification_dropped_jobs=int(dispatcher.get("dropped_jobs") or 0),
            birdnet_enabled=bool(settings.frigate.birdnet_enabled),
            event_pipeline=self._event_pipeline_status(),
            db_pool_degraded=self._db_pool_degraded(),
            startup_warning_count=self._startup_warning_count(),
            cameras=await self._camera_health(),
            telemetry=latest_telemetry(),
            diagnostics_revision=error_diagnostics_history.revision,
            version=self._version,
        )
