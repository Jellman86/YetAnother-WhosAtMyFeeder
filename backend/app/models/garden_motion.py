"""Checksum-bound private recording evidence, independent of Frigate event IDs."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self
from typing import Literal

MOTION_PADDING_SECONDS = 5
MOTION_INTERVAL_SECONDS = 10
MOTION_CATCHUP_INTERVAL_SECONDS = 5
MOTION_CATCHUP_SECONDS = 1800
MOTION_QUEUE_LIMIT = 24


class MotionSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    camera: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    clip_start: float = Field(gt=0, strict=True, description="Requested Frigate recording start, Unix UTC")
    clip_end: float = Field(gt=0, strict=True, description="Requested Frigate recording end, Unix UTC")
    frame_index: int = Field(ge=0, le=1200, strict=True)
    frame_offset: float = Field(
        ge=0,
        strict=True,
        description="Decoded frame offset from the returned clip start; Frigate may include bounded keyframe padding",
    )
    clip_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector_input_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sampled_frame_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    detector_score: float = Field(ge=0, le=1, strict=True)
    animal_confidence: float = Field(default=0.5, ge=0.5, le=0.95, strict=True)
    box_xywh: tuple[float, float, float, float]

    @property
    def key(self) -> str:
        value = ["motion", self.camera, f"{self.clip_start:.6f}", f"{self.clip_end:.6f}"]
        return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()

    @model_validator(mode="after")
    def bound_recording(self) -> Self:
        duration = self.clip_end - self.clip_start
        x, y, width, height = self.box_xywh
        if not 0 < duration <= 10 or self.frame_offset > duration:
            raise ValueError(
                "Motion evidence requires a request of at most ten seconds and a sample within that duration"
            )
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > 1 or y + height > 1:
            raise ValueError("Motion evidence crop must be inside its photo")
        return self


class GardenMotionStatus(BaseModel):
    cameras: list[str]
    installed: bool
    model_bytes: int = 101228666
    catalogue_ready: bool
    busy: bool
    state: Literal["disabled", "waiting", "scanning", "unavailable"]
    message: str
    last_scan_at: str | None = None
    last_outcome: str | None = None
    interval_seconds: int = MOTION_INTERVAL_SECONDS
    catchup_seconds: int = MOTION_CATCHUP_SECONDS
    queue_limit: int = MOTION_QUEUE_LIMIT
    queued_windows: int = Field(default=0, ge=0, le=MOTION_QUEUE_LIMIT)
    queue_camera: str | None = None
    queue_checked_at: str | None = None
    photo_retention_days: int = 3
    photo_limit: int = 128
    animal_confidence: float = Field(default=0.5, ge=0.5, le=0.95)
