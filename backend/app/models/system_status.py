"""One reading of how this install is doing, shared by every owner screen.

The shell, Health, the Dashboard and Settings > Models all read this one snapshot, so a count or
a verdict can never differ between them. Every verdict carries a cause code the page words in its
own language; nothing here is a sentence, and nothing here is a secret.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.service_connections import ServiceConnectionsResponse
from app.models.analysis_status import AnalysisStatusResponse
from app.models.jobs import JobsSnapshotResponse

SubsystemKey = Literal["mqtt", "frigate", "classifier", "finder", "audio", "storage", "notifications"]
# The words `/health` already uses, so the pages' status tones read them unchanged. `off` is a
# part the owner switched off; `unknown` is one nobody has measured yet.
VerdictState = Literal["ok", "degraded", "error", "off", "unknown"]
# Mirrors `/health`, which reports degraded for any fault and never a harder word.
OverallState = Literal["ok", "degraded", "unknown"]


class SubsystemVerdict(BaseModel):
    key: SubsystemKey
    state: VerdictState
    cause: str = Field(description="Why it is in this state, as a code the page words: `status.cause.<key>.<cause>`.")


class OverallVerdict(BaseModel):
    state: OverallState
    cause: str = Field(description="The first thing to fix, as `status.cause.<subsystem>.<cause>` or an overall code.")
    subsystem: SubsystemKey | None = Field(
        default=None, description="Which part the cause belongs to; null for a cause of the whole install."
    )


class JobsProgress(BaseModel):
    current: int = Field(ge=0)
    total: int = Field(ge=1)
    unit: str


class JobsSummary(BaseModel):
    """The prominent work as one count, so the banner's headline and its detail can never disagree."""

    running: int = Field(ge=0)
    queued: int = Field(ge=0)
    progress: JobsProgress | None = Field(
        default=None,
        description="Set only when every running job counts the same thing towards a known total; otherwise null.",
    )


class ModelState(BaseModel):
    """The bird model in use and whether the inference provider the owner chose is the one running."""

    state: VerdictState
    cause: str
    model_id: str | None = None
    model_name: str | None = None
    enabled: bool = True
    selected_provider: str | None = None
    active_provider: str | None = None
    provider_fallback: bool = Field(
        default=False, description="The chosen provider is not the one running, or the runtime reported a fallback."
    )
    fallback_reason: str | None = None
    validation_state: str = Field(
        default="idle", description="The once-per-runtime accelerator check: idle, running, succeeded, failed, ..."
    )
    revision: str = Field(
        description="Changes whenever the model, its provider or its runtime changes, so a page reads details again."
    )


class TelemetrySummary(BaseModel):
    sampled_at: float = Field(description="Unix time of the latest host sample.")
    cpu_percent: float | None = None
    accelerator_percent: float | None = None
    accelerator_kind: Literal["npu", "gpu"] | None = None
    accelerator_label: str | None = None


class CameraHealth(BaseModel):
    camera: str
    status: Literal["online", "offline", "unknown"]
    camera_fps: float | None = None
    process_fps: float | None = None
    detection_fps: float | None = None


class CameraHealthReading(BaseModel):
    cameras: list[CameraHealth]
    checked_at: str


class SystemStatusSnapshot(BaseModel):
    revision: int = Field(ge=0, description="Rises with every published change; a client keeps the highest it saw.")
    generated_at: str
    startup_instance_id: str
    version: str = Field(description="The backend's version; a page built for another version reloads.")
    overall: OverallVerdict
    subsystems: list[SubsystemVerdict]
    jobs_summary: JobsSummary
    jobs: JobsSnapshotResponse
    analysis: AnalysisStatusResponse
    model: ModelState
    connections: ServiceConnectionsResponse
    cameras: CameraHealthReading | None = Field(
        default=None, description="Per-camera health from Frigate's stats; null until Frigate has answered."
    )
    telemetry: TelemetrySummary | None = None
    diagnostics_revision: int = Field(
        ge=0, description="Recorded fault occurrences; when it changes, the incident workspace has something new."
    )
