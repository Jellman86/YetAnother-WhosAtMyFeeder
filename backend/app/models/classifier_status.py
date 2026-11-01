"""Operational classifier status, preserving optional runtime-specific fields."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from app.models.inference_execution import InferenceExecution


class _StatusSection(BaseModel):
    # Runtime diagnostics are additive; retain existing extension fields while
    # giving operational consumers a generated, explicit contract.
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


class ClassifierInferenceHealth(_StatusSection):
    status: Literal["ok", "degraded", "unhealthy"]


class ClassifierNativeQuarantine(_StatusSection):
    status: Literal["recovering", "recovered"]
    restart_recommended: bool


class ClassifierWorkerFallback(_StatusSection):
    active: bool
    reason: str | None
    active_seconds: float | None
    classifications: int


class ClassifierHostEligibility(_StatusSection):
    verified_providers: list[str] = Field(default_factory=list)
    generated_at: str | None = None
    run_id: str | None = None
    model_count: int = 0


class ClassifierCropDeviceCheck(_StatusSection):
    state: Literal["idle", "waiting", "running", "succeeded", "failed", "superseded", "interrupted"]
    model_id: str | None
    providers: list[str]
    reason: str | None
    checked_at: str | None


class ClassifierCropStatus(_StatusSection):
    last_execution: InferenceExecution | None = None
    model_id: str = ""
    chosen_model_id: str = ""
    selected_tier: str = ""
    resolved_tier: str = ""
    installed: bool = False
    healthy: bool = False
    enabled_for_runtime: bool = False
    reason: str = ""
    model_path: str | None = None
    load_error: str | None = None
    device_check: ClassifierCropDeviceCheck | None = None


class ClassifierWorkerRuntime(_StatusSection):
    backend: str = ""
    provider: str = ""
    model_id: str | None = None
    crop_execution: InferenceExecution | None = None


class ClassifierWorkerPool(_StatusSection):
    workers: int = 0
    restarts: int = 0
    last_exit_reason: str | None = None
    last_stderr_excerpt: str = ""
    last_stderr_truncated_bytes: int = 0
    runtime: ClassifierWorkerRuntime | None = None
    circuit_open: bool = False
    circuit_open_until_monotonic: float | None = None
    crop_execution: InferenceExecution | None = None


class ClassifierWorkerPools(_StatusSection):
    live: ClassifierWorkerPool | None = None
    background: ClassifierWorkerPool | None = None
    video: ClassifierWorkerPool | None = None
    late_results_ignored: int = 0


class ClassifierStatusResponse(_StatusSection):
    """Loaded/error/enabled describe a resident model; workers may omit them."""

    image_execution_mode: Literal["in_process", "subprocess"] = "in_process"
    loaded: bool = False
    error: str | None = None
    labels_count: int | None = None
    enabled: bool = False
    active_model_id: str | None = None
    effective_model_id: str | None = None
    onnx_available: bool = False
    openvino_available: bool = False
    openvino_version: str | None = None
    openvino_import_path: str | None = None
    openvino_import_error: str | None = None
    openvino_probe_error: str | None = None
    openvino_gpu_probe_error: str | None = None
    resolved_live_workers: int = 0
    resolved_background_workers: int = 0
    runtime_source: Literal["worker", "planned", "in_process", "in_process_fallback", "default"] | None = None
    active_model_estimated_ram_mb: int | None = None
    openvino_model_compile_ok: bool | None = None
    openvino_model_compile_device: str | None = None
    openvino_model_compile_error: str | None = None
    openvino_model_compile_unsupported_ops: list[str] = Field(default_factory=list)
    openvino_devices: list[str] = Field(default_factory=list)
    cuda_provider_installed: bool = False
    cuda_hardware_available: bool = False
    cuda_available: bool = False
    cuda_probe_error: str | None = None
    intel_cpu_available: bool = False
    intel_gpu_available: bool = False
    intel_npu_available: bool = False
    dev_dri_present: bool = False
    dev_accel_present: bool = False
    dev_dri_entries: list[str] = Field(default_factory=list)
    process_uid: int | None = None
    process_gid: int | None = None
    process_groups: list[int] = Field(default_factory=list)
    image_flavor: str = ""
    packaged_inference_providers: list[str] = Field(default_factory=list)
    image_flavor_warning: str | None = None
    selected_provider: str = ""
    active_provider: str = ""
    inference_backend: str = ""
    fallback_reason: str | None = None
    model_config_warnings: list[str] = Field(default_factory=list)
    host_available_providers: list[str] = Field(default_factory=list)
    available_providers: list[str] = Field(default_factory=list)
    provider_preference_order: list[str] = Field(default_factory=list)
    active_model_candidate_providers: list[str] = Field(default_factory=list)
    active_model_validated_providers: list[str] = Field(default_factory=list)
    validated_provider_preference_order: list[str] = Field(default_factory=list)
    cuda_enabled: bool = False
    personalized_rerank_enabled: bool = False
    personalization_min_feedback_tags: int = 0
    personalization_feedback_rows: int = 0
    personalization_active_camera_models: int = 0
    native_runtime_quarantine: ClassifierNativeQuarantine | None = None
    worker_in_process_fallback: ClassifierWorkerFallback | None = None
    host_device_eligibility: ClassifierHostEligibility | None = None
    inference_health: ClassifierInferenceHealth | None = None
    crop_detector: ClassifierCropStatus | None = None
    worker_pools: ClassifierWorkerPools | None = None
