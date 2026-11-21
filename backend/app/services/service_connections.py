"""The measured state of the broker session and Frigate's API, for Health and the status tiles."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app.config import settings
from app.models.service_connections import FrigateAvailability, ServiceConnectionsResponse
from app.services.broadcaster import broadcaster
from app.services.connection_tracking import FrigateReachabilityTracker
from app.utils.api_datetime import serialize_api_datetime
from app.utils.diagnostic_redaction import configured_secrets, redact_address, redact_connection_error
from app.utils.tasks import create_background_task

log = structlog.get_logger()

SERVICE_CONNECTIONS_CHANGED = "service_connections_changed"

# A reading older than this is refreshed with one cheap request before it is shown, so a
# quiet feeder still gets a current answer rather than one from the last visit.
FRIGATE_READING_MAX_AGE_SECONDS = 60.0
FRIGATE_PROBE_TIMEOUT_SECONDS = 5.0


def announce_service_connections_changed() -> None:
    """Tell open owner pages that a connection changed state, so the tiles follow at once."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    create_background_task(
        broadcaster.broadcast({"type": SERVICE_CONNECTIONS_CHANGED}),
        name="service_connections_changed",
    )


frigate_reachability = FrigateReachabilityTracker(on_change=announce_service_connections_changed)
_frigate_probe_lock = asyncio.Lock()


async def _refresh_frigate_reading(now: datetime) -> None:
    from app.services.frigate_client import frigate_client

    age = frigate_reachability.age_seconds(now)
    if age is not None and age <= FRIGATE_READING_MAX_AGE_SECONDS:
        return
    async with _frigate_probe_lock:
        age = frigate_reachability.age_seconds(datetime.now(timezone.utc))
        if age is not None and age <= FRIGATE_READING_MAX_AGE_SECONDS:
            return
        try:
            # The client records the outcome; the answer itself is not needed.
            await frigate_client.get("api/version", timeout=FRIGATE_PROBE_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - every failure is already recorded as unreachable
            log.debug(
                "Frigate reachability check failed", error=redact_connection_error(str(exc), configured_secrets())
            )


async def collect_service_connections(*, refresh_frigate: bool) -> ServiceConnectionsResponse:
    from app.services.mqtt_service import mqtt_service

    now = datetime.now(timezone.utc)
    if refresh_frigate and (settings.frigate.frigate_url or "").strip():
        await _refresh_frigate_reading(now)
    availability: FrigateAvailability = mqtt_service.frigate_availability()
    # Addresses and errors are typed or produced from owner input and can carry credentials; this
    # reading is shown, exported in diagnostics bundles and logged, so none of it goes out raw.
    secrets = configured_secrets()
    mqtt = mqtt_service.connection.snapshot(
        server=redact_address(settings.frigate.mqtt_server or "", secrets),
        port=int(settings.frigate.mqtt_port),
    )
    if mqtt.last_error:
        mqtt = mqtt.model_copy(update={"last_error": redact_connection_error(mqtt.last_error, secrets)})
    return ServiceConnectionsResponse(
        mqtt=mqtt,
        frigate=frigate_reachability.snapshot(
            url=redact_address(settings.frigate.frigate_url or "", secrets), availability=availability
        ),
        generated_at=serialize_api_datetime(datetime.now(timezone.utc)) or "",
    )
