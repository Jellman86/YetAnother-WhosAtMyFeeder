"""Fresh status state for every test: no reading, cache or publication carries over between tests."""

import asyncio

from app.services import system_status_runtime
from app.services.system_status_readings import SystemStatusReadings


def fresh_system_status_state(monkeypatch) -> SystemStatusReadings:
    """Give the process-wide status service a new collector and forget everything it published.

    The service object is imported by name elsewhere, so it is reset in place; the collector is
    replaced outright, which drops its camera reading, saved photograph jobs and their read times.
    """
    current = system_status_runtime._readings
    readings = SystemStatusReadings(
        startup_instance_id=current._startup_instance_id if current else lambda: "test-instance",
        version=current._version if current else "test",
        startup_warning_count=current._startup_warning_count if current else lambda: 0,
        event_pipeline_status=current._event_pipeline_status if current else lambda: None,
        db_pool_degraded=current._db_pool_degraded if current else lambda: False,
    )
    monkeypatch.setattr(system_status_runtime, "_readings", readings)
    service = system_status_runtime.system_status_service
    monkeypatch.setattr(service, "_revision", 0)
    monkeypatch.setattr(service, "_latest", None)
    monkeypatch.setattr(service, "_latest_at", None)
    monkeypatch.setattr(service, "_published_key", None)
    monkeypatch.setattr(service, "_published_at", None)
    monkeypatch.setattr(service, "_wake", asyncio.Event())
    return readings
