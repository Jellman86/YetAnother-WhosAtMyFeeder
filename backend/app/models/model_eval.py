"""Response shapes of the model evaluation API.

A run's files on disk hold more than the page reads. These models are the contract: a field
that is not declared here is not part of an answer, so text an exception raised cannot reach
a client through a summary that happened to record it.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModelEvalWarning(BaseModel):
    code: str
    message: str = ""
    severity: str = "info"


class ModelEvalTestSet(BaseModel):
    shared_core_species: int = 0
    regional_species: int = 0
    total_species: int = 0
    images_per_species: int = 0
    total_images: int = 0
    region: Optional[str] = None
    image_sources: dict[str, int] = Field(default_factory=dict)


class ModelEvalModelSummary(BaseModel):
    model_id: str
    active_provider: Optional[str] = None
    requested_provider: Optional[str] = None
    device: Optional[str] = None
    ready: bool = True
    ready_reason: Optional[str] = None
    validated_providers: list[str] = Field(default_factory=list)
    failed_providers: list[str] = Field(default_factory=list)
    images_evaluated: int = 0
    top1_accuracy: float = 0.0
    top3_accuracy: float = 0.0
    top5_accuracy: float = 0.0
    abstention_rate: float = 0.0
    high_confidence_unknown_rate: float = 0.0
    mean_latency_ms: Optional[float] = None
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    startup_benchmark_ms: Optional[float] = None
    latency_drift_ratio: Optional[float] = None
    shared_core_top1: float = 0.0
    regional_top1: float = 0.0
    # Runs before 2.22 carry none of the vocabulary fields.
    vocabulary_known: bool = False
    panel_species: Optional[int] = None
    species_outside_vocabulary: Optional[int] = None
    images_in_vocabulary: Optional[int] = None
    top1_accuracy_in_vocabulary: Optional[float] = None
    top3_accuracy_in_vocabulary: Optional[float] = None
    top5_accuracy_in_vocabulary: Optional[float] = None
    shared_core_top1_in_vocabulary: Optional[float] = None
    regional_top1_in_vocabulary: Optional[float] = None
    inference_health_verdict: Optional[str] = None
    warnings: list[ModelEvalWarning] = Field(default_factory=list)


class ModelEvalSkippedModel(BaseModel):
    model_id: str
    # A stable code (`activation_failed`, `reload_failed`); what was raised is logged, not answered.
    reason: str


class ModelEvalRunResponse(BaseModel):
    run_id: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    test_set: Optional[ModelEvalTestSet] = None
    models: list[ModelEvalModelSummary] = Field(default_factory=list)
    skipped_models: list[ModelEvalSkippedModel] = Field(default_factory=list)
    # Why the run stopped early, as a stable code; null for a run that finished or is running.
    error_code: Optional[str] = None
    # The result files this run wrote, which are the ones a client may offer for download.
    available_artifacts: list[str] = Field(default_factory=list)
    # True until the run has written its first summary.
    in_progress: bool = False


class ModelEvalProgress(BaseModel):
    done: int
    total: int
    label: str


class ModelEvalActiveStatus(BaseModel):
    run_id: str
    phase: str
    started_at: str
    progress: ModelEvalProgress


class ModelEvalRunRow(BaseModel):
    run_id: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    model_count: Optional[int] = None
    total_species: Optional[int] = None
    total_images: Optional[int] = None
    region: Optional[str] = None
    error_code: Optional[str] = None


class ModelEvalListResponse(BaseModel):
    active: Optional[ModelEvalActiveStatus] = None
    runs: list[ModelEvalRunRow] = Field(default_factory=list)
