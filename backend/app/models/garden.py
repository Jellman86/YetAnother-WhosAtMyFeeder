"""Private garden model contracts, distinct from bird classification DTOs."""

from typing import Literal
from pydantic import BaseModel, Field

GardenVariant = Literal["4.0.3a", "4.0.3b"]
GardenProvider = Literal["cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"]


class GardenIdentifyRequest(BaseModel):
    variant: GardenVariant = "4.0.3b"
    provider: GardenProvider = "cpu"


class GardenIdentification(BaseModel):
    outcome: Literal["suggestion", "unknown"]
    reason: str
    review: Literal["unreviewed", "accepted", "dismissed"] = "unreviewed"
    taxon_id: str | None = None
    species_id: int | None = None
    name: str | None = None
    rank: str | None = None
    score: float | None = Field(None, ge=0, le=1)
    geofenced: bool = False
    country: str
    variant: GardenVariant
    provider: GardenProvider
    devices: list[str]
    model_sha256: str
    package_sha256: str
    image_sha256: str
    output_index: int = Field(ge=0)
    input_kind: Literal["tracked_crop", "whole_image"]
    box_xywh: tuple[float, float, float, float] | None = None
    frame_size: tuple[int, int]
    identified_at: str


class GardenModelStatus(BaseModel):
    variant: GardenVariant
    installed: bool
    size_bytes: int


class GardenIdentificationStatus(BaseModel):
    country: str | None
    catalogue_ready: bool
    busy: bool
    error: str | None = None
    models: list[GardenModelStatus]
