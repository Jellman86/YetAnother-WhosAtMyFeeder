"""The shapes of the classifier's health and status reports, as the service builds them.

These are the plain dictionaries `check_health`/`get_status` return and their async
`collect_*` forms hand on. `/api/classifier/status` validates the status into
`ClassifierStatusResponse`; these describe the report before that, for in-process callers.
"""

from typing import Any, Literal, NotRequired, TypedDict


class ClassifierHealthReport(TypedDict):
    status: Literal["ok", "degraded", "error"]
    bird_finder: dict[str, Any]
    execution_mode: str
    runtimes: dict[str, dict[str, Any]]
    models: dict[str, dict[str, Any]]
    live_image: dict[str, Any]
    background_image: dict[str, Any]
    background_throttled: bool
    runtime_recovery: dict[str, Any]
    inference_health: dict[str, Any]
    runtime_benchmarks: dict[str, Any]
    # Present when classification runs in supervised worker processes.
    worker_pools: NotRequired[dict[str, Any]]
    # Present while a native crash keeps a worker pool on CPU recovery.
    native_cpu_recovery: NotRequired[dict[str, dict[str, Any]]]


class ClassifierStatusReport(TypedDict):
    image_execution_mode: Literal["in_process", "subprocess"]
    worker_in_process_fallback: dict[str, Any]
    native_runtime_quarantine: dict[str, Any] | None
    runtime_source: Literal["worker", "planned", "in_process", "in_process_fallback", "default"] | None
    resolved_live_workers: int
    resolved_background_workers: int
    active_model_estimated_ram_mb: int | None
    labels_count: int | None
    accel_caps_age_seconds: float | None
    accel_caps_stale: bool
    image_flavor: str
    packaged_inference_providers: list[str]
    image_flavor_warning: str | None
    runtime: str
    runtime_installed: bool
    onnx_available: bool
    active_model_id: str | None
    effective_model_id: str | None
    effective_model_name: str | None
    active_model_installed: bool | None
    openvino_available: bool
    openvino_version: str | None
    openvino_import_path: str | None
    openvino_import_error: str | None
    openvino_probe_error: str | None
    openvino_gpu_probe_error: str | None
    openvino_model_compile_ok: bool | None
    openvino_model_compile_device: str | None
    openvino_model_compile_error: str | None
    openvino_model_compile_unsupported_ops: list[str]
    openvino_devices: list[str]
    cuda_provider_installed: bool
    cuda_hardware_available: bool
    cuda_available: bool
    cuda_probe_error: str | None
    intel_gpu_available: bool
    intel_cpu_available: bool
    intel_npu_available: bool
    host_device_eligibility: dict[str, Any]
    active_model_candidate_providers: list[str]
    active_model_validated_providers: list[str]
    validated_provider_preference_order: list[str]
    dev_dri_present: bool
    dev_dri_entries: list[str]
    dev_accel_present: bool
    process_uid: int | None
    process_gid: int | None
    process_groups: list[int]
    selected_provider: str
    active_provider: str
    inference_backend: str
    fallback_reason: str | None
    model_config_warnings: list[str]
    image_max_concurrent: int
    image_admission_timeout_seconds: float
    image_admission_timeouts: int
    runtime_invalid_output_failures: int
    runtime_fallback_recoveries: int
    runtime_gpu_retries: int
    runtime_gpu_restore_attempts: int
    runtime_gpu_restore_successes: int
    runtime_gpu_restore_failures: int
    gpu_restore_not_before_monotonic: float | None
    strict_non_finite_output: bool
    inference_health: dict[str, Any]
    runtime_benchmarks: dict[str, Any]
    openvino_runtime: dict[str, Any]
    live_image_max_concurrent: int
    live_image_admission_timeout_seconds: float
    live_image_admission_timeouts: int
    live_image_in_flight: int
    live_image_queued: int
    live_image_abandoned: int
    live_image: dict[str, Any]
    background_image_in_flight: int
    background_image_queued: int
    background_image_abandoned: int
    late_completions_ignored: int
    admission_recent_outcomes: list[dict[str, Any]]
    background_throttled: bool
    host_available_providers: list[str]
    available_providers: list[str]
    provider_preference_order: list[str]
    cuda_enabled: bool
    models: dict[str, dict[str, Any]]
    crop_detector: dict[str, Any]
    # Present when classification runs in supervised worker processes.
    worker_pools: NotRequired[dict[str, Any]]
    # A model resident in this process merges its own status in; workers hold none here.
    loaded: NotRequired[bool]
    error: NotRequired[str | None]
    enabled: NotRequired[bool]
    grouped_labels_count: NotRequired[int]
    model_path: NotRequired[str | None]
    input_size: NotRequired[int]
    device: NotRequired[str]
    compile_properties: NotRequired[dict[str, Any]]
    startup_self_test: NotRequired[dict[str, Any]]
