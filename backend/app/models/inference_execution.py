"""Completed model execution evidence, distinct from device recommendations."""

from typing import Literal
from pydantic import BaseModel, Field

InferenceProvider = Literal["cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"]


class InferenceExecution(BaseModel):
    model_id: str = Field(max_length=128)
    provider: InferenceProvider
    requested_provider: InferenceProvider | None = None
    devices: list[str] = Field(min_length=1, max_length=8)
    checked_at: str
    fallback_reason: Literal["runtime_failed", "accelerator_unavailable"] | None = None
