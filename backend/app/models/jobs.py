"""Background work as the owner's jobs view and the live status snapshot report it."""

from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "completed", "failed", "stale", "retrying"]
JobVisibility = Literal["prominent", "routine"]


class JobSnapshotItem(BaseModel):
    id: str
    event_id: str | None = None
    kind: str
    source: str
    status: JobStatus
    phase: str
    current: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    unit: str = "items"
    route: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    visibility: JobVisibility = "prominent"


class JobLaneSnapshot(BaseModel):
    kind: str
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    capacity: int | None = None
    max_concurrent_configured: int | None = None
    max_concurrent_effective: int | None = None
    state: str = "idle"
    blocker: str | None = None


class JobsSnapshotResponse(BaseModel):
    captured_at: str
    items: list[JobSnapshotItem]
    lanes: list[JobLaneSnapshot]
