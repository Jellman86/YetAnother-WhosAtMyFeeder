"""Pure inference-provider policy: which runtime runs, and what it falls back to.

Every input is explicit: host capabilities, the active model's provider contract,
host validation evidence and the operator's request. Nothing here reads settings,
files or devices, so each decision is directly unit-testable. The classifier
facade gathers those inputs and acts on the plan.
"""

from dataclasses import dataclass
from typing import Any, Optional

SUPPORTED_INFERENCE_PROVIDERS = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu", "intel_npu"}


@dataclass(frozen=True)
class InferenceSelection:
    """The concrete runtime chosen for a requested provider, and why it differs."""

    requested_provider: str
    active_provider: str
    backend: str
    ort_providers: tuple[str, ...] = ()
    openvino_device: Optional[str] = None
    fallback_reason: Optional[str] = None


def normalize_inference_provider(value: Optional[str]) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_INFERENCE_PROVIDERS else "auto"


def unique_provider_names(values: Any) -> list[str]:
    providers: list[str] = []
    for value in values or []:
        provider = normalize_inference_provider(str(value or ""))
        if provider == "auto" or provider in providers:
            continue
        providers.append(provider)
    return providers


def provider_supported_for_spec(spec: Optional[dict[str, Any]], provider: str) -> bool:
    normalized = normalize_inference_provider(provider)
    allowed = {normalize_inference_provider(item) for item in (spec or {}).get("supported_inference_providers") or []}
    allowed.discard("auto")
    return not allowed or normalized in allowed


def is_gpu_provider_name(provider: str) -> bool:
    name = str(provider or "").strip().lower()
    return name in {"gpu", "intel_gpu"} or name.startswith("gpu.")


def cuda_unavailable_reason(caps: dict) -> str:
    probe_error = str(caps.get("cuda_probe_error") or "").strip()
    if probe_error:
        return f"CUDA provider detected but failed runtime probe: {probe_error}"
    if caps.get("cuda_provider_installed") and not caps.get("cuda_hardware_available"):
        return "CUDAExecutionProvider is installed but no NVIDIA GPU is accessible in this runtime"
    return "CUDAExecutionProvider is not available"


def runtime_fallback_targets_for(
    *,
    active_backend: str,
    active_provider: str,
    caps: dict[str, Any],
    provider_order: list[str] | tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    """Return the concrete recovery order for the active inference runtime."""
    targets: list[tuple[str, str]] = []

    def _append(target_backend: str, target_provider: str) -> None:
        target = (target_backend, target_provider)
        if target not in targets and target != (active_backend, active_provider):
            targets.append(target)

    provider_backends = {
        "intel_npu": ("openvino", "intel_npu"),
        "intel_gpu": ("openvino", "intel_gpu"),
        "cuda": ("onnxruntime", "cuda"),
        "intel_cpu": ("openvino", "intel_cpu"),
        "cpu": ("onnxruntime", "cpu"),
    }
    available = {
        "intel_npu": bool(caps.get("openvino_available") and caps.get("intel_npu_available")),
        "intel_gpu": bool(caps.get("openvino_available") and caps.get("intel_gpu_available")),
        "cuda": bool(caps.get("ort_available") and caps.get("cuda_available")),
        "intel_cpu": bool(caps.get("openvino_available") and caps.get("intel_cpu_available")),
        "cpu": bool(caps.get("ort_available")),
    }
    for provider in unique_provider_names(provider_order):
        if available.get(provider) and provider in provider_backends:
            backend, normalized_provider = provider_backends[provider]
            _append(backend, normalized_provider)

    if active_backend == "openvino":
        if active_provider in {"intel_gpu", "intel_npu"} and caps.get("intel_cpu_available"):
            _append("openvino", "intel_cpu")
        if caps.get("ort_available"):
            _append("onnxruntime", "cpu")
        _append("tflite", "tflite")
        return targets

    if active_backend == "onnxruntime":
        if active_provider != "cpu" and caps.get("ort_available"):
            _append("onnxruntime", "cpu")
        if caps.get("openvino_available") and caps.get("intel_cpu_available"):
            _append("openvino", "intel_cpu")
        _append("tflite", "tflite")
        return targets

    if active_backend == "tflite":
        return targets

    if caps.get("ort_available"):
        _append("onnxruntime", "cpu")
    _append("tflite", "tflite")
    return targets


def provider_capability_contract(
    *,
    caps: dict[str, Any],
    packaged_providers: tuple[str, ...] | list[str],
    supported_providers: list[str] | tuple[str, ...] | None,
    active_backend: str,
    active_provider: str,
    provider_order: list[str] | tuple[str, ...] | None = None,
) -> dict[str, list[str]]:
    """Build the provider list exposed to configuration clients.

    A selectable provider must be packaged by the running image, usable on this
    host, and supported by the active model when that model declares a provider
    allow-list. The active runtime and its real recovery targets come first;
    other valid manual alternatives follow without pretending they are automatic
    fallbacks.
    """
    packaged = {
        normalize_inference_provider(provider)
        for provider in packaged_providers
        if normalize_inference_provider(provider) != "auto"
    }
    supported = {
        normalize_inference_provider(provider)
        for provider in (supported_providers or [])
        if normalize_inference_provider(provider) != "auto"
    }
    host_available = {
        "cpu": bool(caps.get("ort_available")),
        "cuda": bool(caps.get("cuda_available")),
        "intel_cpu": bool(caps.get("openvino_available") and caps.get("intel_cpu_available")),
        "intel_gpu": bool(caps.get("openvino_available") and caps.get("intel_gpu_available")),
        "intel_npu": bool(caps.get("openvino_available") and caps.get("intel_npu_available")),
    }

    def _host_selectable(provider: str) -> bool:
        return bool(host_available.get(provider) and (not packaged or provider in packaged))

    def _selectable(provider: str) -> bool:
        return bool(_host_selectable(provider) and (not supported or provider in supported))

    fallback_candidates = [active_provider]
    fallback_candidates.extend(unique_provider_names(provider_order))
    fallback_candidates.extend(
        provider
        for _backend, provider in runtime_fallback_targets_for(
            active_backend=active_backend,
            active_provider=active_provider,
            caps=caps,
            provider_order=provider_order,
        )
    )

    provider_preference_order: list[str] = []
    for provider in fallback_candidates:
        if _selectable(provider) and provider not in provider_preference_order:
            provider_preference_order.append(provider)

    host_available_providers: list[str] = []
    for provider in fallback_candidates:
        if _host_selectable(provider) and provider not in host_available_providers:
            host_available_providers.append(provider)

    available_providers = list(provider_preference_order)
    manual_candidates = unique_provider_names(provider_order)
    manual_candidates.extend(
        provider
        for provider in ("intel_npu", "intel_gpu", "cuda", "intel_cpu", "cpu")
        if provider not in manual_candidates
    )
    for provider in manual_candidates:
        if _host_selectable(provider) and provider not in host_available_providers:
            host_available_providers.append(provider)
        if _selectable(provider) and provider not in available_providers:
            available_providers.append(provider)

    return {
        "host_available_providers": host_available_providers,
        "available_providers": available_providers,
        "provider_preference_order": provider_preference_order,
    }


def resolve_inference_selection(
    requested_provider: Optional[str],
    caps: dict,
    supported_providers: Optional[list[str]] = None,
    preferred_providers: Optional[list[str]] = None,
) -> InferenceSelection:
    """Resolve desired inference provider to a concrete backend/device with fallback."""
    requested = normalize_inference_provider(requested_provider)
    allowed = {
        normalize_inference_provider(provider)
        for provider in (supported_providers or [])
        if normalize_inference_provider(provider) != "auto"
    }

    def _provider_allowed(provider: str) -> bool:
        return not allowed or provider in allowed

    def _reason_with_constraint(base_reason: Optional[str], provider: str, fallback_target: str) -> str:
        if _provider_allowed(provider):
            return base_reason or ""
        constraint_reason = f"Active model artifact does not support {fallback_target}"
        if base_reason:
            return f"{constraint_reason}; {base_reason}"
        return constraint_reason

    def _ort_cpu(reason: Optional[str] = None) -> InferenceSelection:
        if caps.get("ort_available") and _provider_allowed("cpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="cpu",
                backend="onnxruntime",
                ort_providers=("CPUExecutionProvider",),
                openvino_device=None,
                fallback_reason=reason,
            )
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            fallback_reason = reason or "ONNX Runtime unavailable or unsupported; using OpenVINO CPU"
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_cpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="CPU",
                fallback_reason=fallback_reason,
            )
        return InferenceSelection(
            requested_provider=requested,
            active_provider="unavailable",
            backend="unavailable",
            ort_providers=(),
            openvino_device=None,
            fallback_reason=reason or "No ONNX-capable runtime available (onnxruntime/OpenVINO)",
        )

    if requested == "cpu":
        return _ort_cpu()

    if requested == "cuda":
        if caps.get("ort_available") and caps.get("cuda_available") and _provider_allowed("cuda"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="cuda",
                backend="onnxruntime",
                ort_providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
                openvino_device=None,
                fallback_reason=None,
            )
        cuda_fallback_reason = _reason_with_constraint(
            f"CUDA requested but {cuda_unavailable_reason(caps)}",
            "cuda",
            "CUDA",
        )
        if caps.get("openvino_available") and caps.get("intel_gpu_available") and _provider_allowed("intel_gpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_gpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="GPU",
                fallback_reason=f"{cuda_fallback_reason}; using OpenVINO GPU",
            )
        return _ort_cpu(cuda_fallback_reason)

    if requested == "intel_cpu":
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_cpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="CPU",
                fallback_reason=None,
            )
        return _ort_cpu(
            _reason_with_constraint(
                "OpenVINO CPU requested but OpenVINO CPU device is not available",
                "intel_cpu",
                "OpenVINO CPU",
            )
        )

    if requested == "intel_gpu":
        if caps.get("openvino_available") and caps.get("intel_gpu_available") and _provider_allowed("intel_gpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_gpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="GPU",
                fallback_reason=None,
            )
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_cpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="CPU",
                fallback_reason=_reason_with_constraint(
                    "Intel GPU requested but not available; falling back to OpenVINO CPU",
                    "intel_gpu",
                    "Intel GPU",
                ),
            )
        return _ort_cpu(
            _reason_with_constraint(
                "Intel GPU requested but OpenVINO GPU is not available",
                "intel_gpu",
                "Intel GPU",
            )
        )

    if requested == "intel_npu":
        if caps.get("openvino_available") and caps.get("intel_npu_available") and _provider_allowed("intel_npu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_npu",
                backend="openvino",
                ort_providers=(),
                openvino_device="NPU",
                fallback_reason=None,
            )
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_cpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="CPU",
                fallback_reason=_reason_with_constraint(
                    "Intel NPU requested but not available; falling back to OpenVINO CPU",
                    "intel_npu",
                    "Intel NPU",
                ),
            )
        return _ort_cpu(
            _reason_with_constraint(
                "Intel NPU requested but OpenVINO NPU is not available",
                "intel_npu",
                "Intel NPU",
            )
        )

    # ``auto`` follows this installation's measured order when available.
    # Without sweep evidence, use a conservative accelerator-first order; the
    # effective model contract still prevents unvalidated host-gated candidates
    # from appearing here.
    auto_order = unique_provider_names(preferred_providers)
    for provider in ("intel_npu", "intel_gpu", "cuda", "intel_cpu", "cpu"):
        if provider not in auto_order:
            auto_order.append(provider)

    for provider in auto_order:
        if not _provider_allowed(provider):
            continue
        if provider == "intel_npu" and caps.get("openvino_available") and caps.get("intel_npu_available"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_npu",
                backend="openvino",
                ort_providers=(),
                openvino_device="NPU",
                fallback_reason=None,
            )
        if provider == "intel_gpu" and caps.get("openvino_available") and caps.get("intel_gpu_available"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_gpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="GPU",
                fallback_reason=None,
            )
        if provider == "cuda" and caps.get("ort_available") and caps.get("cuda_available"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="cuda",
                backend="onnxruntime",
                ort_providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
                openvino_device=None,
                fallback_reason=None,
            )
        if provider == "intel_cpu" and caps.get("openvino_available") and caps.get("intel_cpu_available"):
            return InferenceSelection(
                requested_provider=requested,
                active_provider="intel_cpu",
                backend="openvino",
                ort_providers=(),
                openvino_device="CPU",
                fallback_reason=None,
            )
        if provider == "cpu" and caps.get("ort_available"):
            return _ort_cpu()

    return _ort_cpu("No validated provider for the active model is available on this host")


def reconcile_ort_active_provider(
    requested_active_provider: str,
    session_providers: list[str] | None,
) -> tuple[str, Optional[str]]:
    """Reconcile planned ORT provider with the session's actual enabled providers.

    ONNX Runtime can initialize a session with CPU only even when CUDA was requested,
    depending on runtime/library availability. Keep YA-WAMF status/fallback reporting honest.
    """
    actual = requested_active_provider
    providers = list(session_providers or [])

    if requested_active_provider == "cuda" and "CUDAExecutionProvider" not in providers:
        if "CPUExecutionProvider" in providers:
            return (
                "cpu",
                "CUDA requested but ONNX Runtime session initialized without CUDAExecutionProvider; using CPUExecutionProvider",
            )
        return (
            "cpu",
            "CUDA requested but ONNX Runtime session initialized without CUDAExecutionProvider",
        )

    return actual, None


def apply_host_validated_providers(
    spec: dict[str, Any],
    *,
    validated_providers: list[str],
    preference_order: list[str],
) -> dict[str, Any]:
    """Resolve the effective provider contract for this exact installation.

    ``supported_inference_providers`` is the globally safe baseline.
    ``candidate_inference_providers`` is the wider set an isolated host sweep may
    probe. Current-image validation evidence narrows the runtime to passing
    providers and may widen it only to reviewed candidates. Evidence from an
    older image flavor is already filtered out by its reader.
    """
    resolved = dict(spec)
    supported = unique_provider_names(spec.get("supported_inference_providers"))
    candidates = unique_provider_names(spec.get("candidate_inference_providers") or supported)
    candidate_set = set(candidates)
    validated = [provider for provider in validated_providers if provider in candidate_set]
    preference = [provider for provider in preference_order if provider in validated]
    for provider in validated:
        if provider not in preference:
            preference.append(provider)

    # Once a sweep exists it is authoritative: providers that were available
    # but failed must not remain selectable merely because they are globally
    # supported. Without a current sweep, retain the safe global baseline so
    # upgrades do not deactivate a previously working installation.
    effective = list(preference or supported)
    resolved["supported_inference_providers"] = effective
    resolved["candidate_inference_providers"] = candidates
    resolved["host_added_inference_providers"] = [provider for provider in effective if provider not in supported]
    resolved["host_validated_inference_providers"] = list(validated)
    resolved["host_provider_preference_order"] = list(preference)
    resolved["host_validation_applied"] = bool(validated)
    return resolved
