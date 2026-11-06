"""Immutable provenance for a saved, private animal preview."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CROP_BYTES_LIMIT = 128 * 1024
CROP_COUNT_LIMIT = 2000


class GardenCropEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source_kind: Literal["motion", "frigate_clean"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    crop_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frame_size: tuple[int, int]
    image_size: tuple[int, int]
    box_xywh: tuple[float, float, float, float]
    source_start: float
    source_end: float
    frame_time: float | None = None

    @model_validator(mode="after")
    def bounded(self) -> "GardenCropEvidence":
        x, y, width, height = self.box_xywh
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > 1 or y + height > 1:
            raise ValueError("Animal crop must be inside its source photo")
        if min(*self.frame_size, *self.image_size) <= 0 or max(self.image_size) > 512:
            raise ValueError("Animal crop dimensions are invalid")
        if not all(math.isfinite(value) for value in (self.source_start, self.source_end)):
            raise ValueError("Animal crop source window is invalid")
        if not 0 < self.source_start <= self.source_end:
            raise ValueError("Animal crop source window is invalid")
        if self.source_kind == "frigate_clean" and (
            self.frame_time is None or not self.source_start <= self.frame_time <= self.source_end
        ):
            raise ValueError("Frigate crops require the aligned frame timestamp")
        return self


class GardenCropStorage(BaseModel):
    count: int = Field(ge=0)
    bytes: int = Field(ge=0)
    limit: int = Field(ge=1)
    max_bytes_per_crop: int = Field(ge=1)
