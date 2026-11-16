"""The video analysis queue's reported state."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class AnalysisStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    pending: int
    active: int
    circuit_open: bool
    open_until: Optional[str] = None
    failure_count: Optional[int] = None
    pending_capacity: Optional[int] = None
    pending_available: Optional[int] = None
    max_concurrent_configured: Optional[int] = None
    max_concurrent_effective: Optional[int] = None
    mqtt_pressure_level: Optional[str] = None
    throttled_for_mqtt_pressure: Optional[bool] = None
    throttled_for_live_pressure: Optional[bool] = None
    maintenance_starvation_relief_active: Optional[bool] = None
    live_pressure_active: Optional[bool] = None
    live_in_flight: Optional[int] = None
    live_queued: Optional[int] = None
    mqtt_in_flight: Optional[int] = None
    mqtt_in_flight_capacity: Optional[int] = None
    oldest_maintenance_pending_age_seconds: Optional[float] = None
    pending_maintenance: Optional[int] = None
    active_maintenance: Optional[int] = None
    queue_limit: Optional[int] = None
    scan_limit: Optional[int] = None
    scan_truncated: Optional[bool] = None
    remaining_candidates: Optional[int] = None
    maintenance_state: Optional[str] = None
    maintenance_status_message: Optional[str] = None
    maintenance_seconds_since_progress: Optional[float] = None
