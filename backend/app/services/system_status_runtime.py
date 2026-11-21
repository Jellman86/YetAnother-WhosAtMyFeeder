"""The process-wide status service, published on the live stream. `main` configures its readings."""

from app.services.broadcaster import broadcaster
from app.services.system_status import SystemStatusInputs, SystemStatusService
from app.services.system_status_readings import SystemStatusReadings

_readings: SystemStatusReadings | None = None


def configure_status_readings(readings: SystemStatusReadings) -> None:
    global _readings
    _readings = readings


async def _collect() -> SystemStatusInputs:
    if _readings is None:
        raise RuntimeError("System status readings are not configured")
    return await _readings.collect()


system_status_service = SystemStatusService(
    collect=_collect,
    publish=broadcaster.broadcast,
    has_subscribers=broadcaster.has_subscribers,
)
broadcaster.add_listener(system_status_service.request_refresh)
