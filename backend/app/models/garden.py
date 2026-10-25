"""Private garden model contracts, distinct from bird classification DTOs."""

from app.models.inference_execution import InferenceExecution, InferenceProvider
from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator

GardenVariant = Literal["4.0.3a", "4.0.3b"]
GardenProvider = Literal["cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"]


class GardenPresenceMass(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    bird: float = Field(ge=0, le=1, strict=True)
    animal: float = Field(ge=0, le=1, strict=True)
    human: float = Field(ge=0, le=1, strict=True)
    non_animal: float = Field(ge=0, le=1, strict=True)
    other: float = Field(ge=0, le=1, strict=True)

    @model_validator(mode="after")
    def complete_mass(self) -> "GardenPresenceMass":
        if not math.isclose(math.fsum(self.model_dump().values()), 1, rel_tol=0, abs_tol=0.000001):
            raise ValueError("Automatic checks require complete probability mass")
        return self


class GardenAutomaticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["animal", "bird", "non_animal", "uncertain", "unavailable"]
    checked_at: str
    policy_version: int = Field(0, ge=0)
    decision_reason: (
        Literal["below_threshold", "naming_disabled", "location_required", "identity_unavailable"] | None
    ) = None
    naming_score: float | None = Field(None, ge=0, le=1)
    naming_threshold: float | None = Field(None, ge=0.7, le=0.99)
    execution: InferenceExecution | None = None
    image_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    variant: GardenVariant | None = None
    model_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    package_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    mass: GardenPresenceMass | None = None
    box_xywh: tuple[float, float, float, float] | None = None
    devices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_required(self) -> "GardenAutomaticCheck":
        if self.outcome != "unavailable" and not all(
            [
                self.mass is not None,
                self.image_sha256,
                self.variant,
                self.model_sha256,
                self.package_sha256,
                self.devices,
            ]
        ):
            raise ValueError("Automatic decisions require model and photo evidence")
        return self


class GardenPhotoCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: GardenProvider = "cpu"


class GardenPhotoMass(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    bird: float = Field(ge=0, le=1, strict=True)
    mammal: float = Field(ge=0, le=1, strict=True)
    human: float = Field(ge=0, le=1, strict=True)
    blank: float = Field(ge=0, le=1, strict=True)
    other: float = Field(ge=0, le=1, strict=True)

    @model_validator(mode="after")
    def complete_mass(self) -> "GardenPhotoMass":
        if not math.isclose(math.fsum(self.model_dump().values()), 1, rel_tol=0, abs_tol=0.000001):
            raise ValueError("Photo checks require complete probability mass")
        return self


class GardenPhotoCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capture_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    suggestion: Literal["bird", "mammal", "uncertain", "unavailable"]
    mass: GardenPhotoMass | None
    variant: Literal["4.0.3a"] = "4.0.3a"
    provider: GardenProvider
    devices: list[str] = Field(min_length=1, max_length=8)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    box_xywh: tuple[float, float, float, float]
    frame_size: tuple[int, int]


class GardenIdentifyRequest(BaseModel):
    variant: GardenVariant = "4.0.3b"
    provider: GardenProvider = "cpu"


class GardenIdentification(BaseModel):
    outcome: Literal["suggestion", "unknown"]
    reason: str
    review: Literal["unreviewed", "accepted", "dismissed"] = "unreviewed"
    # True when the automatic check confirmed and named the capture without an owner action.
    automatic: bool = False
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
    preferred_provider: InferenceProvider = "cpu"
    last_execution: InferenceExecution | None = None
    automatic_message: str = "Automatic checks wait for an enabled Garden camera and idle bird inference."


class GardenNotificationStatus(BaseModel):
    enabled: bool
    channels: list[Literal["discord", "telegram", "pushover", "email"]]
    configured: dict[str, bool]
    attempts: dict[str, int]
