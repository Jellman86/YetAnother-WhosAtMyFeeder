"""Durable evidence about the input that supplied a species name."""

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClassificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=64)
    is_cropped: bool | None = None
    box: tuple[float, float, float, float] | None = None
    frame_size: tuple[int, int] | None = None
    frame_time: float | None = Field(default=None, allow_inf_nan=False, ge=0)
    frame_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    supporting_frames: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_geometry(self) -> "ClassificationEvidence":
        if self.frame_size is not None and any(value <= 0 for value in self.frame_size):
            raise ValueError("Frame dimensions must be positive")
        if self.box is not None:
            if self.frame_size is None or not all(math.isfinite(value) for value in self.box):
                raise ValueError("A box needs finite coordinates and its source frame dimensions")
            left, top, right, bottom = self.box
            width, height = self.frame_size
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError("Box lies outside its source frame")
            if self.is_cropped is not True:
                raise ValueError("A whole-view input cannot claim a classifier crop")
        return self

    @property
    def is_whole_view(self) -> bool:
        return self.is_cropped is False and self.source not in {"frigate_sublabel", "owner_species_choice"}

    @property
    def can_personalize(self) -> bool:
        return self.is_cropped is True
