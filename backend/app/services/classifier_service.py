import structlog
import numpy as np
import os
import cv2
import asyncio
import contextlib
import inspect
import base64
import ctypes
import hashlib
import importlib
import io
import json
import math
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image
from typing import Optional, Any, Awaitable, Callable, Literal

from app.services.inference_health import InferenceHealth, Outcome, RuntimeKey
from app.services.startup_status import startup_status
from app.utils.canonical_species import should_hide_species_label
from app.utils.runtime_flavor import get_image_flavor, image_flavor_warning, packaged_inference_providers

# TFLite runtime
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import ai_edge_litert.interpreter as tflite
    except ImportError:
        try:
            import tensorflow.lite as tflite
        except ImportError:
            tflite = None


def _tflite_runtime_name() -> str:
    module_name = str(getattr(tflite, "__name__", "") or "")
    if module_name.startswith("ai_edge_litert"):
        return "litert"
    if module_name.startswith("tflite_runtime"):
        return "tflite-runtime"
    return "tensorflow" if tflite is not None else "unavailable"


# ONNX runtime (for high-accuracy models)
try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False


def _preload_onnxruntime_cuda_runtime_libraries() -> None:
    """Preload packaged CUDA/cuDNN runtime libraries for ONNX Runtime.

    ONNX Runtime supports shipping the CUDA/cuDNN userspace stack via pip.
    In that setup the shared libraries live under Python site-packages rather
    than a standard system library path, so we ask ORT to preload them
    explicitly before probing or creating CUDA sessions.
    """
    if ort is None:
        return
    preload_dlls = getattr(ort, "preload_dlls", None)
    if not callable(preload_dlls):
        return
    preload_dlls(directory="")


def _detect_openvino_support() -> dict:
    """Resolve OpenVINO Core import across package versions.

    OpenVINO 2025+ exposes the stable ``openvino.Core`` directly.
    The legacy ``openvino.runtime.Core`` path was deprecated in 2025.x and
    removed in 2026.0. We try the new path first and fall back for pre-2025
    installations.
    """
    attempts: list[str] = []

    for module_name, attr_name, import_path in (
        ("openvino", "Core", "openvino.Core"),
        ("openvino.runtime", "Core", "openvino.runtime.Core"),
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            attempts.append(f"{import_path}: {type(exc).__name__}: {exc}")
            continue

        core_class = getattr(module, attr_name, None)
        if core_class is None:
            attempts.append(f"{import_path}: missing attribute {attr_name}")
            continue

        version = getattr(module, "__version__", None)
        if not version and module_name != "openvino":
            try:
                top_level = importlib.import_module("openvino")
                version = getattr(top_level, "__version__", None)
            except Exception:
                version = None

        return {
            "available": True,
            "core_class": core_class,
            "version": version,
            "import_path": import_path,
            "import_error": None,
        }

    return {
        "available": False,
        "core_class": None,
        "version": None,
        "import_path": None,
        "import_error": "; ".join(attempts) if attempts else "OpenVINO not installed",
    }


# OpenVINO runtime (optional; single-image Intel acceleration path)
_OPENVINO_SUPPORT = _detect_openvino_support()
OpenVINOCore = _OPENVINO_SUPPORT["core_class"]
OPENVINO_AVAILABLE = bool(_OPENVINO_SUPPORT["available"])

from app.config import settings  # noqa: E402
from app.models.ai_models import ClassificationInputContext, CropGeneratorConfig  # noqa: E402
from app.services.bird_crop_service import bird_crop_service  # noqa: E402
from app.services.crop_source_resolver import crop_source_resolver  # noqa: E402
from app.services.classification_admission import (  # noqa: E402
    ClassificationAdmissionCoordinator,
    ClassificationAdmissionTimeoutError,
    ClassificationLeaseExpiredError,
)
from app.services.classifier_supervisor import (  # noqa: E402
    ClassifierSupervisor,
    ClassifierWorkerCircuitOpenError,
    ClassifierWorkerDeadlineExceededError,
    ClassifierWorkerExitedError,
    ClassifierWorkerHeartbeatTimeoutError,
    ClassifierWorkerStartupTimeoutError,
)
from app.services.personalization_service import personalization_service  # noqa: E402
from app.services.video_classification_policy import (  # noqa: E402
    SourceTemporalConsensus,
    VIDEO_MIN_FRAME_SEPARATION_SECONDS,
    VIDEO_SPARSE_POOL_MAX_FRAMES,
    assess_temporal_consensus,
    select_temporal_source_consensus,
)
from app.utils.classifier_labels import (  # noqa: E402
    build_grouped_classifier_labels,
    normalize_classifier_label,
    normalize_classifier_labels,
)

log = structlog.get_logger()

SUPPORTED_INFERENCE_PROVIDERS = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu", "intel_npu"}
CLASSIFIER_IMAGE_MAX_CONCURRENT = max(1, int(os.getenv("CLASSIFIER_IMAGE_MAX_CONCURRENT", "2")))
CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS = max(
    0.05,
    float(os.getenv("CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS", "0.5")),
)
CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS = max(
    0.05,
    float(os.getenv("CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS", "0.25")),
)
CLASSIFIER_IMAGE_LEASE_TIMEOUT_SECONDS = max(
    0.1,
    float(os.getenv("CLASSIFIER_IMAGE_LEASE_TIMEOUT_SECONDS", "15")),
)
CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS = max(
    0.1,
    float(os.getenv("CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS", "30")),
)
CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS = max(
    0.1,
    float(os.getenv("CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS", "45")),
)
CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_THRESHOLD = max(
    1,
    int(os.getenv("CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_THRESHOLD", "3")),
)
CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS = max(
    1.0,
    float(os.getenv("CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS", "600")),
)
LIVE_GPU_LEASE_EXPIRY_FALLBACK_REASON = "live_gpu_lease_expiry_fallback"
GPU_UNHEALTHY_FALLBACK_REASON = "gpu_unhealthy_fallback"
LIVE_GPU_LEASE_EXPIRY_FALLBACK_UNAVAILABLE_REASON = "live_gpu_lease_expiry_fallback_unavailable"
GPU_UNHEALTHY_FALLBACK_UNAVAILABLE_REASON = "gpu_unhealthy_fallback_unavailable"
CLASSIFIER_ADMISSION_RECOVERY_WINDOW_SECONDS = max(
    1.0,
    float(os.getenv("CLASSIFIER_ADMISSION_RECOVERY_WINDOW_SECONDS", "300")),
)
CLASSIFIER_ACCEL_PROBE_TTL_SECONDS = max(
    1.0,
    float(os.getenv("CLASSIFIER_ACCEL_PROBE_TTL_SECONDS", "60")),
)
CLASSIFIER_GPU_INVALID_RETRY_LIMIT = max(
    0,
    int(os.getenv("CLASSIFIER_GPU_INVALID_RETRY_LIMIT", "1")),
)
CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS = max(
    1.0,
    float(os.getenv("CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS", "120")),
)
CLASSIFIER_RUNTIME_BENCHMARK_MAX_GPU_CPU_RATIO = max(
    1.0,
    float(os.getenv("CLASSIFIER_RUNTIME_BENCHMARK_MAX_GPU_CPU_RATIO", "5.0")),
)
CLASSIFIER_VIDEO_UNIFORM_SCORE_MULTIPLIER = max(
    1.0,
    float(os.getenv("CLASSIFIER_VIDEO_UNIFORM_SCORE_MULTIPLIER", "1.25")),
)
LEGACY_CLASSIFIER_STRICT_NON_FINITE_OUTPUT = (
    os.getenv("CLASSIFIER_STRICT_NON_FINITE_OUTPUT", "true").strip().lower() != "false"
)


class LiveImageClassificationOverloadedError(RuntimeError):
    """Raised when live image classification cannot obtain bounded capacity promptly."""


class BackgroundImageClassificationUnavailableError(RuntimeError):
    """Raised when background image classification cannot complete due to capacity or worker availability."""

    def __init__(self, reason_code: str):
        self.reason_code = str(reason_code or "background_image_unavailable")
        super().__init__(self.reason_code)


class VideoClassificationWorkerError(RuntimeError):
    """Raised when supervised video classification fails with a specific worker/runtime reason."""

    def __init__(self, reason_code: str):
        self.reason_code = str(reason_code or "video_worker_unavailable")
        super().__init__(self.reason_code)


class InvalidInferenceOutputError(RuntimeError):
    """Raised when a runtime returns unusable model outputs after successful load."""

    def __init__(
        self,
        *,
        backend: str,
        provider: str,
        detail: str,
        diagnostics: Optional[dict[str, Any]] = None,
    ):
        self.backend = str(backend)
        self.provider = str(provider)
        self.detail = str(detail)
        self.diagnostics = dict(diagnostics or {})
        super().__init__(f"{self.backend}:{self.provider}: {self.detail}")


def _normalize_classification_input_context(input_context: Any | None) -> ClassificationInputContext:
    if isinstance(input_context, ClassificationInputContext):
        return input_context
    if input_context is None:
        return ClassificationInputContext()

    payload: dict[str, Any] = {}
    if isinstance(input_context, dict):
        payload = dict(input_context)
    else:
        model_dump = getattr(input_context, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
            except Exception:
                dumped = None
            if isinstance(dumped, dict):
                payload = dumped
        elif hasattr(input_context, "__dict__"):
            payload = {key: value for key, value in vars(input_context).items() if not key.startswith("_")}

    try:
        return ClassificationInputContext.model_validate(payload)
    except Exception:
        return ClassificationInputContext()


def _select_video_frame_indices(
    *,
    total_frames: int,
    sample_count: int,
    clip_variant: str = "event",
) -> np.ndarray:
    total_frames = max(0, int(total_frames))
    sample_count = max(0, int(sample_count))
    if total_frames <= 0 or sample_count <= 0:
        return np.array([], dtype=int)

    sample_count = min(sample_count, total_frames)
    if sample_count == 1:
        return np.array([max(0, (total_frames - 1) // 2)], dtype=int)

    max_index = total_frames - 1
    normalized_variant = str(clip_variant or "event").strip().lower()
    if normalized_variant not in {"event", "recording"}:
        normalized_variant = "event"

    # Quantiles of a symmetric power curve give deterministic, centre-weighted
    # coverage without merging two grids that can collide and then fill from
    # frame zero. Event clips get the stronger centre bias; recording/full-visit
    # clips retain broader edge coverage because their padding is meaningful.
    centre_bias = 1.65 if normalized_variant == "event" else 1.25
    quantiles = np.linspace(-1.0, 1.0, sample_count)
    normalized_targets = 0.5 + (0.5 * np.sign(quantiles) * np.power(np.abs(quantiles), centre_bias))
    targets = [int(round(float(value) * max_index)) for value in normalized_targets]

    selected: set[int] = set()
    for target in targets:
        target = max(0, min(max_index, target))
        if target not in selected:
            selected.add(target)
            continue
        # Rounding can collide only when the requested density approaches the
        # number of frames. Repair around the intended target, never from the
        # start of the clip, so the temporal distribution remains honest.
        for distance in range(1, max_index + 1):
            for candidate in (target - distance, target + distance):
                if 0 <= candidate <= max_index and candidate not in selected:
                    selected.add(candidate)
                    break
            else:
                continue
            break

    return np.array(sorted(selected), dtype=int)


def _invoke_model_classify(
    model: Any,
    image: Image.Image,
    *,
    input_context: ClassificationInputContext | None = None,
) -> list[dict]:
    classify_fn = getattr(model, "classify", None)
    if not callable(classify_fn):
        return []

    normalized_input_context = _normalize_classification_input_context(input_context)
    try:
        signature = inspect.signature(classify_fn)
        accepts_input_context = any(
            param.kind == inspect.Parameter.VAR_KEYWORD or param.name == "input_context"
            for param in signature.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_input_context = False

    if accepts_input_context:
        return classify_fn(image, input_context=normalized_input_context)

    try:
        return classify_fn(image, input_context=normalized_input_context)
    except TypeError as exc:
        error_text = str(exc)
        if (
            "unexpected keyword argument 'input_context'" not in error_text
            and 'unexpected keyword argument "input_context"' not in error_text
        ):
            raise
        return classify_fn(image)


def _strict_non_finite_output_enabled() -> bool:
    configured = getattr(getattr(settings, "classification", None), "strict_non_finite_output", None)
    if isinstance(configured, bool):
        return configured
    return LEGACY_CLASSIFIER_STRICT_NON_FINITE_OUTPUT


def _openvino_gpu_startup_self_test_enabled() -> bool:
    return os.getenv("OPENVINO_GPU_STARTUP_SELF_TEST", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _runtime_benchmark_enabled() -> bool:
    return os.getenv("CLASSIFIER_RUNTIME_BENCHMARK_ENABLED", "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _label_integrity_for(model: object) -> dict[str, object]:
    """Report whether a loaded model's label file still matches what was published."""
    from pathlib import Path

    from app.services.label_integrity import LabelVerdict, verify_model_labels

    labels_path = getattr(model, "labels_path", None)
    if not labels_path:
        return {"verdict": LabelVerdict.MISSING.value, "label_count": 0}
    directory = Path(str(labels_path)).parent
    # A region variant installs as `<parent>/<region>`, so the directory name is
    # the region and its parent is the model id.
    region = directory.name if directory.name in {"eu", "na"} else None
    model_id = directory.parent.name if region else directory.name
    try:
        return verify_model_labels(model_id, directory, region=region).as_dict()
    except Exception as error:  # pragma: no cover - status must never fail
        log.warning("Could not verify model labels", error=str(error))
        return {"verdict": "unverifiable", "label_count": 0}


def _safe_isinstance(value: Any, expected_type: Any) -> bool:
    return isinstance(expected_type, type) and isinstance(value, expected_type)


def _openvino_gpu_optional_compile_properties() -> dict[str, str]:
    properties: dict[str, str] = {}
    execution_mode = os.getenv("OPENVINO_GPU_EXECUTION_MODE_HINT", "").strip()
    activations_scale = os.getenv("OPENVINO_GPU_ACTIVATIONS_SCALE_FACTOR", "").strip()
    if execution_mode:
        properties["EXECUTION_MODE_HINT"] = execution_mode
    if activations_scale:
        properties["ACTIVATIONS_SCALE_FACTOR"] = activations_scale
    return properties


def _normalize_inference_provider(value: Optional[str]) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_INFERENCE_PROVIDERS else "auto"


def _host_validated_providers(
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> list[str]:
    """Providers validated for this model, host, and exact runtime image.

    The model-validation service owns the persisted schema and legacy migration
    rules. Keeping one reader prevents the live classifier and setup UI from
    disagreeing after an image-flavor switch.
    """
    if not model_id:
        return []
    try:
        from app.services.model_validation import host_eligible_providers

        return host_eligible_providers(model_id, artifact_sha256=artifact_sha256)
    except Exception:
        return []


def _apply_host_validated_provider_policy(spec: dict[str, Any], *, model_id: str) -> dict[str, Any]:
    """Resolve the effective provider contract for this exact installation.

    ``supported_inference_providers`` is the globally safe baseline.
    ``candidate_inference_providers`` is the wider set an isolated host sweep may
    probe. Current-image validation evidence narrows the runtime to passing
    providers and may widen it only to reviewed candidates. Evidence from an
    older image flavor is filtered by ``host_eligible_providers``.
    """
    resolved = dict(spec)
    supported = _unique_provider_names(spec.get("supported_inference_providers"))
    candidates = _unique_provider_names(spec.get("candidate_inference_providers") or supported)
    candidate_set = set(candidates)
    artifact_sha256 = str(spec.get("artifact_sha256") or "").strip().lower() or None
    validated = [
        provider
        for provider in _host_validated_providers(
            model_id,
            artifact_sha256=artifact_sha256,
        )
        if provider in candidate_set
    ]
    try:
        from app.services.model_validation import host_provider_preference_order

        preference = [
            provider
            for provider in host_provider_preference_order(
                model_id,
                artifact_sha256=artifact_sha256,
            )
            if provider in validated
        ]
    except Exception:
        preference = []
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


def _unique_provider_names(values: Any) -> list[str]:
    providers: list[str] = []
    for value in values or []:
        provider = _normalize_inference_provider(str(value or ""))
        if provider == "auto" or provider in providers:
            continue
        providers.append(provider)
    return providers


def _host_device_eligibility_summary() -> dict[str, Any]:
    """Summary of the per-host compatibility sweep for the UI: the union of
    providers validated across all models, plus when/what run produced it.
    Lets the Settings UI show iGPU/NPU as verified vs unverified per host."""
    try:
        from app.services.model_validation import host_eligibility_summary

        return host_eligibility_summary()
    except Exception:
        return {"verified_providers": [], "generated_at": None, "run_id": None, "model_count": 0}


def _normalize_probability_vector(values: np.ndarray, *, context: str) -> np.ndarray:
    probs = np.asarray(values, dtype=np.float32).reshape(-1)
    if probs.size == 0:
        return np.array([], dtype=np.float32)

    finite_mask = np.isfinite(probs)
    if not finite_mask.any():
        if not _strict_non_finite_output_enabled():
            log.warning(
                "Classifier produced all non-finite probabilities; coercing in non-strict mode",
                context=context,
            )
            probs = np.nan_to_num(probs, nan=1.0, posinf=1.0, neginf=0.0).astype(np.float32, copy=False)
            total = float(np.sum(np.maximum(probs, 0.0)))
            if total > 0.0 and np.isfinite(total):
                return (np.maximum(probs, 0.0) / total).astype(np.float32, copy=False)
            return np.full((probs.size,), 1.0 / float(probs.size), dtype=np.float32)
        log.warning("Classifier produced all non-finite probabilities", context=context)
        return np.array([], dtype=np.float32)

    if not finite_mask.all():
        probs = probs.copy()
        bad_count = int((~finite_mask).sum())
        probs[~finite_mask] = 0.0
        log.warning(
            "Classifier produced non-finite probabilities; zeroing invalid entries",
            context=context,
            invalid_count=bad_count,
        )

    probs = np.maximum(probs, 0.0)
    total = float(np.sum(probs))
    if not np.isfinite(total) or total <= 0.0:
        log.warning("Classifier probability normalization failed", context=context, total=total)
        return np.array([], dtype=np.float32)

    normalized = probs / total
    if not np.isfinite(normalized).all():
        log.warning("Classifier normalization still produced non-finite probabilities", context=context)
        return np.array([], dtype=np.float32)
    return normalized.astype(np.float32, copy=False)


def _safe_softmax(x: np.ndarray, *, context: str) -> np.ndarray:
    logits = np.asarray(x, dtype=np.float32).reshape(-1)
    if logits.size == 0:
        return np.array([], dtype=np.float32)

    finite_mask = np.isfinite(logits)
    if not finite_mask.any():
        nan_count = int(np.isnan(logits).sum())
        pos_inf_count = int((logits == np.inf).sum())
        neg_inf_count = int((logits == -np.inf).sum())
        log.warning(
            "Classifier produced ALL non-finite logits",
            context=context,
            nan_count=nan_count,
            pos_inf_count=pos_inf_count,
            neg_inf_count=neg_inf_count,
            total_elements=logits.size,
        )
        if not _strict_non_finite_output_enabled():
            log.warning(
                "Classifier produced all non-finite logits; coercing in non-strict mode",
                context=context,
            )
            logits = np.nan_to_num(logits, nan=0.0, posinf=80.0, neginf=-80.0).astype(np.float32, copy=False)
            shifted = logits - float(np.max(logits))
            exp_logits = np.exp(np.clip(shifted, -80.0, 80.0)).astype(np.float32, copy=False)
            return _normalize_probability_vector(exp_logits, context=context)
        log.warning("Classifier produced all non-finite logits", context=context)
        return np.array([], dtype=np.float32)

    if not finite_mask.all():
        logits = logits.copy()
        bad_count = int((~finite_mask).sum())
        logits[~finite_mask] = -np.inf
        log.warning(
            "Classifier produced non-finite logits; excluding invalid entries",
            context=context,
            invalid_count=bad_count,
        )

    max_logit = float(np.max(logits[finite_mask]))
    shifted = logits - max_logit
    exp_logits = np.zeros_like(logits, dtype=np.float32)
    exp_mask = np.isfinite(shifted)
    exp_logits[exp_mask] = np.exp(np.clip(shifted[exp_mask], -80.0, 80.0))
    return _normalize_probability_vector(exp_logits, context=context)


def _build_classification_results(
    probs: np.ndarray,
    labels: list[str],
    *,
    top_k: int,
    grouped_labels: Optional[list[str]] = None,
) -> list[dict]:
    probabilities = np.asarray(probs, dtype=np.float32).reshape(-1)
    if probabilities.size == 0:
        return []

    if grouped_labels and len(grouped_labels) == probabilities.size:
        aggregated: dict[str, dict[str, Any]] = {}
        for i, score in enumerate(probabilities):
            label = grouped_labels[i] or (labels[i] if i < len(labels) else f"Class {i}")
            entry = aggregated.get(label)
            score_value = float(score)
            if entry is None:
                aggregated[label] = {
                    "index": int(i),
                    "label": label,
                    "score": score_value,
                    "_best_member_score": score_value,
                }
                continue
            entry["score"] += score_value
            if score_value > float(entry["_best_member_score"]):
                entry["index"] = int(i)
                entry["_best_member_score"] = score_value

        ranked = sorted(aggregated.values(), key=lambda item: float(item["score"]), reverse=True)
        for item in ranked:
            item.pop("_best_member_score", None)
        return ranked[:top_k]

    top_indices = np.argsort(probabilities)[::-1][:top_k]
    return [
        {
            "index": int(i),
            "score": float(probabilities[i]),
            "label": normalize_classifier_label(labels[i]) if i < len(labels) else f"Class {i}",
        }
        for i in top_indices
    ]


def _resolve_model_labels(
    labels_path: str,
    label_grouping: dict,
    *,
    model_sha256: Optional[str] = None,
    context: str = "model",
) -> tuple[list[str], list[str], str]:
    """Labels and their grouping, preferring the catalogue over the label file.

    `labels.txt` is verified when a model is downloaded and never again, so every
    inference since has trusted whatever is on disk. The catalogue holds the same
    labels compiled from a file that was proven at install time.

    The catalogue is used only when it holds a complete, contiguous set matching
    the model's declared output width; anything short of that falls back to the
    file, so a model it does not know behaves exactly as it does today.

    Returns the labels, the grouped labels, and which source supplied them.
    """
    labels: list[str] = []
    source = "none"

    if model_sha256:
        try:
            from app.services.catalogue_labels import catalogue_labels_for_model

            from_catalogue = catalogue_labels_for_model(model_sha256)
        except Exception as error:  # pragma: no cover - defensive
            log.debug("Catalogue labels unavailable", context=context, error=str(error))
            from_catalogue = None
        if from_catalogue:
            labels = normalize_classifier_labels(from_catalogue)
            source = "catalogue"

    if not labels and os.path.exists(labels_path):
        try:
            with open(labels_path, "r", encoding="utf-8", errors="replace") as handle:
                labels = normalize_classifier_labels(line.strip() for line in handle.readlines() if line.strip())
            source = "label_file"
        except Exception as error:
            log.error("Failed to load labels", context=context, error=str(error))
            return [], [], "none"

    grouped: list[str] = []
    strategy = str((label_grouping or {}).get("strategy") or "").strip()
    if strategy and labels:
        grouped = build_grouped_classifier_labels(labels, strategy=strategy)
    return labels, grouped, source


def _resolve_grouped_labels(
    labels: list[str],
    *,
    label_grouping: Optional[dict[str, Any]] = None,
    existing_grouped_labels: Optional[list[str]] = None,
) -> list[str]:
    if existing_grouped_labels:
        return list(existing_grouped_labels)
    strategy = str((label_grouping or {}).get("strategy") or "").strip()
    if not strategy:
        return []
    return build_grouped_classifier_labels(labels, strategy=strategy)


def _provider_supported_for_spec(spec: Optional[dict[str, Any]], provider: str) -> bool:
    normalized = _normalize_inference_provider(provider)
    allowed = {_normalize_inference_provider(item) for item in (spec or {}).get("supported_inference_providers") or []}
    allowed.discard("auto")
    return not allowed or normalized in allowed


def _classifier_wants_bgr(preprocessing: Optional[dict[str, Any]]) -> bool:
    """True when a classifier model declares BGR tensor input.

    PIL decoding always gives RGB, so when a model was trained on BGR tensors
    (unusual for classifiers, but possible) we must reverse the channel axis
    before normalization. Previously `color_space: "BGR"` was silently dropped
    on the classifier path — only the crop-detector path honored it.
    """
    return str((preprocessing or {}).get("color_space") or "RGB").strip().upper() == "BGR"


def _resolve_color_space(preprocessing: Optional[dict[str, Any]]) -> str:
    color_space = str((preprocessing or {}).get("color_space") or "RGB").strip().upper() or "RGB"
    # Only "RGB" and "L" (grayscale) are valid for classification preprocessing.
    # RGBA is excluded: alpha channels are not used by any supported model and produce
    # 4-channel tensors that break 3-element mean/std normalisation.
    # BGR is not a PIL mode; models requiring BGR must be handled explicitly.
    return color_space if color_space in {"RGB", "L"} else "RGB"


def _resolve_resize_mode(preprocessing: Optional[dict[str, Any]], *, default: str = "letterbox") -> str:
    mode = str((preprocessing or {}).get("resize_mode") or default).strip().lower()
    if mode not in {"letterbox", "center_crop", "direct_resize"}:
        return default
    return mode


def _resolve_padding_color(preprocessing: Optional[dict[str, Any]], *, default: int = 128) -> tuple[int, int, int]:
    raw = (preprocessing or {}).get("padding_color", default)
    if isinstance(raw, int):
        value = max(0, min(255, int(raw)))
        return (value, value, value)
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        return tuple(max(0, min(255, int(v))) for v in raw)
    value = max(0, min(255, int(default)))
    return (value, value, value)


def _resolve_interpolation(preprocessing: Optional[dict[str, Any]]) -> Image.Resampling:
    interpolation = str((preprocessing or {}).get("interpolation") or "bicubic").strip().lower()
    return {
        "nearest": Image.Resampling.NEAREST,
        "bilinear": Image.Resampling.BILINEAR,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }.get(interpolation, Image.Resampling.BICUBIC)


def _resize_preserving_aspect_shortest_edge(
    image: Image.Image,
    shortest_edge: int,
    *,
    interpolation: Image.Resampling,
) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        return image
    if width <= height:
        new_width = shortest_edge
        new_height = max(1, int(round(height * (shortest_edge / width))))
    else:
        new_height = shortest_edge
        new_width = max(1, int(round(width * (shortest_edge / height))))
    return image.resize((new_width, new_height), interpolation)


def _center_crop_to_size(image: Image.Image, target_size: int) -> Image.Image:
    width, height = image.size
    left = max(0, int(round((width - target_size) / 2.0)))
    top = max(0, int(round((height - target_size) / 2.0)))
    right = left + target_size
    bottom = top + target_size
    return image.crop((left, top, right, bottom))


def _resize_with_preprocessing(
    image: Image.Image,
    target_size: int,
    *,
    preprocessing: Optional[dict[str, Any]],
    default_resize_mode: str = "letterbox",
    default_padding_color: int = 128,
) -> Image.Image:
    image = image.convert(_resolve_color_space(preprocessing))
    interpolation = _resolve_interpolation(preprocessing)
    resize_mode = _resolve_resize_mode(preprocessing, default=default_resize_mode)

    if resize_mode == "direct_resize":
        return image.resize((target_size, target_size), interpolation)

    if resize_mode == "center_crop":
        crop_pct = float((preprocessing or {}).get("crop_pct") or 1.0)
        if crop_pct <= 0.0:
            crop_pct = 1.0
        scale_size = max(target_size, int(round(target_size / crop_pct)))
        resized = _resize_preserving_aspect_shortest_edge(
            image,
            scale_size,
            interpolation=interpolation,
        )
        return _center_crop_to_size(resized, target_size)

    width, height = image.size
    scale = min(target_size / width, target_size / height)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = image.resize((new_width, new_height), interpolation)
    canvas = Image.new(
        "RGB",
        (target_size, target_size),
        _resolve_padding_color(preprocessing, default=default_padding_color),
    )
    canvas.paste(resized, ((target_size - new_width) // 2, (target_size - new_height) // 2))
    return canvas


def _summarize_numeric_array(values: np.ndarray, *, name: str) -> dict[str, Any]:
    arr = np.asarray(values)
    finite_mask = np.isfinite(arr)
    finite_values = arr[finite_mask]
    invalid_output_kind: str | None = None
    if arr.size == 0:
        invalid_output_kind = "empty"
    elif finite_values.size == 0:
        if np.isnan(arr).any():
            invalid_output_kind = "all_nan"
        elif np.isinf(arr).any():
            invalid_output_kind = "all_inf"
        else:
            invalid_output_kind = "no_finite"
    elif not finite_mask.all():
        invalid_output_kind = "mixed_non_finite"
    summary: dict[str, Any] = {
        "name": str(name),
        "shape": [int(dim) for dim in arr.shape],
        "dtype": str(arr.dtype),
        "element_count": int(arr.size),
        "finite_count": int(finite_mask.sum()),
        "nan_count": int(np.isnan(arr).sum()),
        "pos_inf_count": int(np.isposinf(arr).sum()),
        "neg_inf_count": int(np.isneginf(arr).sum()),
        "invalid_output_kind": invalid_output_kind,
    }
    if finite_values.size:
        summary["finite_min"] = float(finite_values.min())
        summary["finite_max"] = float(finite_values.max())
        summary["finite_mean"] = float(finite_values.mean())
    else:
        summary["finite_min"] = None
        summary["finite_max"] = None
        summary["finite_mean"] = None
    return summary


def _summarize_runtime_exception(exc: Exception, *, max_len: int = 280) -> str:
    message = f"{type(exc).__name__}: {exc}"
    message = " ".join(message.split())
    if len(message) > max_len:
        return f"{message[: max_len - 1]}…"
    return message


def _safe_sha256_file(path: str) -> str | None:
    file_path = Path(str(path or ""))
    if not file_path.exists() or not file_path.is_file():
        return None
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_model_artifact_metadata(model_path: str) -> dict[str, Any]:
    model_file = Path(str(model_path or ""))
    metadata: dict[str, Any] = {
        "model_sha256": _safe_sha256_file(str(model_file)),
        "weights_sha256": _safe_sha256_file(f"{model_file}.data"),
        "producer_name": None,
        "producer_version": None,
        "opset": [],
    }
    if model_file.suffix.lower() != ".onnx" or not model_file.exists():
        return metadata

    try:
        onnx = importlib.import_module("onnx")
        model = onnx.load(str(model_file), load_external_data=False)
    except Exception:
        return metadata

    metadata["producer_name"] = str(getattr(model, "producer_name", "") or "") or None
    metadata["producer_version"] = str(getattr(model, "producer_version", "") or "") or None
    opset_import = getattr(model, "opset_import", None) or []
    metadata["opset"] = [
        {
            "domain": str(getattr(entry, "domain", "") or "ai.onnx"),
            "version": int(getattr(entry, "version", 0) or 0),
        }
        for entry in opset_import
    ]
    return metadata


def _detect_acceleration_capabilities() -> dict:
    """Probe optional inference runtimes/providers without raising."""
    dev_dri_entries: list[str] = []
    try:
        if os.path.isdir("/dev/dri"):
            dev_dri_entries = sorted(os.listdir("/dev/dri"))
    except Exception:
        dev_dri_entries = []

    caps = {
        "ort_available": bool(ONNX_AVAILABLE and ort is not None),
        "cuda_provider_installed": False,
        "cuda_hardware_available": False,
        "cuda_available": False,
        "cuda_probe_error": None,
        "openvino_available": bool(OPENVINO_AVAILABLE and OpenVINOCore is not None),
        "openvino_version": _OPENVINO_SUPPORT.get("version"),
        "openvino_import_path": _OPENVINO_SUPPORT.get("import_path"),
        "openvino_import_error": _OPENVINO_SUPPORT.get("import_error"),
        "openvino_probe_error": None,
        "openvino_gpu_probe_error": None,
        "intel_gpu_available": False,
        "intel_cpu_available": False,
        "intel_npu_available": False,
        "openvino_devices": [],
        "dev_accel_present": os.path.isdir("/dev/accel"),
        "dev_dri_present": os.path.isdir("/dev/dri"),
        "dev_dri_entries": dev_dri_entries,
        "process_uid": None,
        "process_gid": None,
        "process_groups": [],
    }
    try:
        caps["process_uid"] = os.getuid()
        caps["process_gid"] = os.getgid()
        caps["process_groups"] = list(os.getgroups())
    except Exception:
        pass

    if caps["ort_available"]:
        try:
            _preload_onnxruntime_cuda_runtime_libraries()
            caps["cuda_provider_installed"] = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
            if caps["cuda_provider_installed"]:
                caps["cuda_hardware_available"] = _detect_cuda_hardware_available()
                if caps["cuda_hardware_available"]:
                    cuda_probe = _probe_onnxruntime_cuda_provider_safe()
                    if not cuda_probe.get("ok"):
                        caps["cuda_probe_error"] = cuda_probe.get("error") or "CUDA provider probe failed"
            caps["cuda_available"] = bool(
                caps["cuda_provider_installed"] and caps["cuda_hardware_available"] and not caps["cuda_probe_error"]
            )
        except Exception as e:
            log.warning("Failed to inspect ONNX Runtime providers", error=str(e))

    if caps["openvino_available"]:
        probe = _probe_openvino_devices_safe()
        if probe.get("ok"):
            devices = list(probe.get("devices") or [])
            caps["openvino_devices"] = devices
            caps["intel_gpu_available"] = any(d == "GPU" or str(d).startswith("GPU.") for d in devices)
            caps["intel_cpu_available"] = any(d == "CPU" or str(d).startswith("CPU.") for d in devices)
            caps["intel_npu_available"] = any(d == "NPU" or str(d).startswith("NPU.") for d in devices)
            caps["openvino_gpu_probe_error"] = probe.get("gpu_probe_error")
        else:
            caps["openvino_probe_error"] = probe.get("error") or "OpenVINO device probe failed"
            caps["openvino_gpu_probe_error"] = probe.get("gpu_probe_error")
            log.warning("Failed to inspect OpenVINO devices", error=caps["openvino_probe_error"])

    return caps


def _probe_onnxruntime_cuda_provider_safe() -> dict:
    """Probe whether ONNX Runtime can initialize a CUDA session and run inference."""
    script = (
        "import base64, json, pathlib, sys, tempfile\n"
        "import numpy as np\n"
        "try:\n"
        "    import onnxruntime as ort\n"
        "    preload_dlls = getattr(ort, 'preload_dlls', None)\n"
        "    if callable(preload_dlls):\n"
        "        preload_dlls(directory='')\n"
        "    providers = list(ort.get_available_providers() or [])\n"
        "    if 'CUDAExecutionProvider' not in providers:\n"
        "        print(json.dumps({'ok': False, 'error': 'CUDAExecutionProvider not advertised by onnxruntime'}))\n"
        "        sys.exit(2)\n"
        "    capi_dir = pathlib.Path(getattr(ort, '__file__', '')).resolve().parent / 'capi'\n"
        "    candidates = [\n"
        "        capi_dir / 'libonnxruntime_providers_cuda.so',\n"
        "        capi_dir / 'onnxruntime_providers_cuda.dll',\n"
        "        capi_dir / 'libonnxruntime_providers_cuda.dylib',\n"
        "    ]\n"
        "    provider_library = next((str(path) for path in candidates if path.exists()), None)\n"
        "    if provider_library is None:\n"
        "        print(json.dumps({'ok': False, 'error': 'CUDA provider library not found in onnxruntime package'}))\n"
        "        sys.exit(2)\n"
        "    model_bytes = base64.b64decode('CA06QwoQCgF4EgF5IghJZGVudGl0eRIFcHJvYmVaEwoBeBIOCgwIARIICgIIAQoCCAFiEwoBeRIOCgwIARIICgIIAQoCCAFCBAoAEAs=')\n"
        "    with tempfile.NamedTemporaryFile(suffix='.onnx', delete=False) as handle:\n"
        "        handle.write(model_bytes)\n"
        "        model_path = handle.name\n"
        "    try:\n"
        "        sess = ort.InferenceSession(model_path, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])\n"
        "        active_providers = list(sess.get_providers() or [])\n"
        "        if 'CUDAExecutionProvider' not in active_providers:\n"
        "            print(json.dumps({'ok': False, 'error': 'ONNX Runtime session initialized without CUDAExecutionProvider', 'provider_library': provider_library, 'active_providers': active_providers}))\n"
        "            sys.exit(2)\n"
        "        output = sess.run(None, {'x': np.ones((1, 1), dtype=np.float32)})\n"
        "        output_ok = bool(output) and getattr(output[0], 'shape', None) == (1, 1)\n"
        "        if not output_ok:\n"
        "            print(json.dumps({'ok': False, 'error': 'CUDA probe inference produced unexpected output', 'provider_library': provider_library, 'active_providers': active_providers}))\n"
        "            sys.exit(2)\n"
        "        print(json.dumps({'ok': True, 'error': None, 'provider_library': provider_library, 'active_providers': active_providers}))\n"
        "    finally:\n"
        "        pathlib.Path(model_path).unlink(missing_ok=True)\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': f'{type(e).__name__}: {e}'}))\n"
        "    sys.exit(2)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TimeoutExpired: ONNX Runtime CUDA probe timed out"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stdout:
        try:
            result = json.loads(stdout)
            if isinstance(result, dict):
                result.setdefault("ok", proc.returncode == 0)
                result.setdefault("error", None)
                if proc.returncode != 0 and not result.get("error"):
                    result["error"] = f"ONNX Runtime CUDA probe failed with exit code {proc.returncode}"
                return result
        except Exception:
            pass

    return {
        "ok": False,
        "error": stderr or f"ONNX Runtime CUDA probe failed with exit code {proc.returncode}",
    }


def _probe_openvino_devices_safe() -> dict:
    """Probe OpenVINO device availability in a subprocess so plugin crashes cannot kill the backend."""
    script = (
        "import json, sys\n"
        "try:\n"
        "    try:\n"
        "        from openvino import Core\n"
        "    except Exception:\n"
        "        from openvino.runtime import Core\n"
        "    core = Core()\n"
        "    devices = list(getattr(core, 'available_devices', []) or [])\n"
        "    gpu_probe_error = None\n"
        "    has_gpu = any(d == 'GPU' or str(d).startswith('GPU.') for d in devices)\n"
        "    if not has_gpu:\n"
        "        try:\n"
        "            core.get_property('GPU', 'FULL_DEVICE_NAME')\n"
        "        except Exception as e:\n"
        "            gpu_probe_error = f'{type(e).__name__}: {e}'\n"
        "    print(json.dumps({'ok': True, 'devices': devices, 'gpu_probe_error': gpu_probe_error}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'ok': False, 'error': f'{type(e).__name__}: {e}'}))\n"
        "    sys.exit(2)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "devices": [],
            "gpu_probe_error": None,
            "error": "TimeoutExpired: OpenVINO device probe timed out",
        }
    except Exception as e:
        return {
            "ok": False,
            "devices": [],
            "gpu_probe_error": None,
            "error": f"{type(e).__name__}: {e}",
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stdout:
        try:
            result = json.loads(stdout)
            if isinstance(result, dict):
                result.setdefault("devices", [])
                result.setdefault("gpu_probe_error", None)
                result.setdefault("error", None)
                result.setdefault("ok", proc.returncode == 0)
                if proc.returncode != 0 and not result.get("error"):
                    result["error"] = f"OpenVINO device probe failed with exit code {proc.returncode}"
                return result
        except Exception:
            pass

    if stderr:
        error = stderr
    else:
        error = f"OpenVINO device probe failed with exit code {proc.returncode}"

    return {
        "ok": False,
        "devices": [],
        "gpu_probe_error": None,
        "error": error,
    }


def _probe_openvino_gpu_plugin_error_safe() -> Optional[str]:
    """Probe OpenVINO GPU plugin in a subprocess so plugin crashes cannot kill the backend."""
    script = (
        "import sys\n"
        "try:\n"
        "    from openvino import Core\n"
        "except Exception:\n"
        "    from openvino.runtime import Core\n"
        "core = Core()\n"
        "try:\n"
        "    core.get_property('GPU', 'FULL_DEVICE_NAME')\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print(f'{type(e).__name__}: {e}')\n"
        "    sys.exit(2)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "TimeoutExpired: OpenVINO GPU plugin probe timed out"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 0:
        return None
    if stdout:
        return stdout
    if stderr:
        return stderr
    return f"OpenVINO GPU plugin probe failed with exit code {proc.returncode}"


def _detect_cuda_hardware_available() -> bool:
    """Detect whether an NVIDIA CUDA device is actually accessible in this runtime.

    ORT can report CUDAExecutionProvider when the wheel supports CUDA even if no NVIDIA
    GPU is passed through. Probe the CUDA driver API directly to avoid false positives.
    """
    for library_name in ("libcuda.so.1", "libcuda.so", "nvcuda.dll"):
        try:
            cuda = ctypes.CDLL(library_name)
        except OSError:
            continue

        try:
            cu_init = cuda.cuInit
            cu_init.argtypes = [ctypes.c_uint]
            cu_init.restype = ctypes.c_int

            cu_device_get_count = cuda.cuDeviceGetCount
            cu_device_get_count.argtypes = [ctypes.POINTER(ctypes.c_int)]
            cu_device_get_count.restype = ctypes.c_int

            if cu_init(0) != 0:
                return False

            count = ctypes.c_int(0)
            if cu_device_get_count(ctypes.byref(count)) != 0:
                return False

            return count.value > 0
        except Exception as e:
            log.warning("CUDA driver probe failed", library=library_name, error=str(e))
            return False

    return False


def _cuda_unavailable_reason(caps: dict) -> str:
    probe_error = str(caps.get("cuda_probe_error") or "").strip()
    if probe_error:
        return f"CUDA provider detected but failed runtime probe: {probe_error}"
    if caps.get("cuda_provider_installed") and not caps.get("cuda_hardware_available"):
        return "CUDAExecutionProvider is installed but no NVIDIA GPU is accessible in this runtime"
    return "CUDAExecutionProvider is not available"


def _runtime_fallback_targets_for(
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
    for provider in _unique_provider_names(provider_order):
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


def _provider_capability_contract(
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
        _normalize_inference_provider(provider)
        for provider in packaged_providers
        if _normalize_inference_provider(provider) != "auto"
    }
    supported = {
        _normalize_inference_provider(provider)
        for provider in (supported_providers or [])
        if _normalize_inference_provider(provider) != "auto"
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
    fallback_candidates.extend(_unique_provider_names(provider_order))
    fallback_candidates.extend(
        provider
        for _backend, provider in _runtime_fallback_targets_for(
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
    manual_candidates = _unique_provider_names(provider_order)
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


def _resolve_inference_selection(
    requested_provider: Optional[str],
    caps: dict,
    supported_providers: Optional[list[str]] = None,
    preferred_providers: Optional[list[str]] = None,
) -> dict:
    """Resolve desired inference provider to a concrete backend/device with fallback."""
    requested = _normalize_inference_provider(requested_provider)
    allowed = {
        _normalize_inference_provider(provider)
        for provider in (supported_providers or [])
        if _normalize_inference_provider(provider) != "auto"
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

    def _ort_cpu(reason: Optional[str] = None) -> dict:
        if caps.get("ort_available") and _provider_allowed("cpu"):
            return {
                "requested_provider": requested,
                "active_provider": "cpu",
                "backend": "onnxruntime",
                "ort_providers": ["CPUExecutionProvider"],
                "openvino_device": None,
                "fallback_reason": reason,
            }
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            fallback_reason = reason or "ONNX Runtime unavailable or unsupported; using OpenVINO CPU"
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": fallback_reason,
            }
        return {
            "requested_provider": requested,
            "active_provider": "unavailable",
            "backend": "unavailable",
            "ort_providers": [],
            "openvino_device": None,
            "fallback_reason": reason or "No ONNX-capable runtime available (onnxruntime/OpenVINO)",
        }

    if requested == "cpu":
        return _ort_cpu()

    if requested == "cuda":
        if caps.get("ort_available") and caps.get("cuda_available") and _provider_allowed("cuda"):
            return {
                "requested_provider": requested,
                "active_provider": "cuda",
                "backend": "onnxruntime",
                "ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "openvino_device": None,
                "fallback_reason": None,
            }
        cuda_fallback_reason = _reason_with_constraint(
            f"CUDA requested but {_cuda_unavailable_reason(caps)}",
            "cuda",
            "CUDA",
        )
        if caps.get("openvino_available") and caps.get("intel_gpu_available") and _provider_allowed("intel_gpu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_gpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "GPU",
                "fallback_reason": f"{cuda_fallback_reason}; using OpenVINO GPU",
            }
        return _ort_cpu(cuda_fallback_reason)

    if requested == "intel_cpu":
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": None,
            }
        return _ort_cpu(
            _reason_with_constraint(
                "OpenVINO CPU requested but OpenVINO CPU device is not available",
                "intel_cpu",
                "OpenVINO CPU",
            )
        )

    if requested == "intel_gpu":
        if caps.get("openvino_available") and caps.get("intel_gpu_available") and _provider_allowed("intel_gpu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_gpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "GPU",
                "fallback_reason": None,
            }
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": _reason_with_constraint(
                    "Intel GPU requested but not available; falling back to OpenVINO CPU",
                    "intel_gpu",
                    "Intel GPU",
                ),
            }
        return _ort_cpu(
            _reason_with_constraint(
                "Intel GPU requested but OpenVINO GPU is not available",
                "intel_gpu",
                "Intel GPU",
            )
        )

    if requested == "intel_npu":
        if caps.get("openvino_available") and caps.get("intel_npu_available") and _provider_allowed("intel_npu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_npu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "NPU",
                "fallback_reason": None,
            }
        if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": _reason_with_constraint(
                    "Intel NPU requested but not available; falling back to OpenVINO CPU",
                    "intel_npu",
                    "Intel NPU",
                ),
            }
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
    auto_order = _unique_provider_names(preferred_providers)
    for provider in ("intel_npu", "intel_gpu", "cuda", "intel_cpu", "cpu"):
        if provider not in auto_order:
            auto_order.append(provider)

    for provider in auto_order:
        if not _provider_allowed(provider):
            continue
        if provider == "intel_npu" and caps.get("openvino_available") and caps.get("intel_npu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_npu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "NPU",
                "fallback_reason": None,
            }
        if provider == "intel_gpu" and caps.get("openvino_available") and caps.get("intel_gpu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_gpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "GPU",
                "fallback_reason": None,
            }
        if provider == "cuda" and caps.get("ort_available") and caps.get("cuda_available"):
            return {
                "requested_provider": requested,
                "active_provider": "cuda",
                "backend": "onnxruntime",
                "ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "openvino_device": None,
                "fallback_reason": None,
            }
        if provider == "intel_cpu" and caps.get("openvino_available") and caps.get("intel_cpu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": None,
            }
        if provider == "cpu" and caps.get("ort_available"):
            return _ort_cpu()

    return _ort_cpu("No validated provider for the active model is available on this host")


def _reconcile_ort_active_provider(
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


def _extract_openvino_unsupported_ops(error_text: Optional[str]) -> list[str]:
    if not error_text:
        return []
    normalized = " ".join(str(error_text).split())
    match = re.search(
        r"OpenVINO does not support the following ONNX operations:\s*([^.;]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in match.group(1).split(","):
        op = raw.strip()
        if not op:
            continue
        if op in seen:
            continue
        seen.add(op)
        out.append(op)
    return out


def _summarize_openvino_load_error(
    error_text: Optional[str],
    device_name: Optional[str],
    fallback_target: str = "ONNX Runtime CPU",
) -> str:
    device = (device_name or "device").strip() or "device"
    prefix = f"OpenVINO {device} could not compile this model on this host"
    unsupported_ops = _extract_openvino_unsupported_ops(error_text)
    if unsupported_ops:
        return f"{prefix} (unsupported ONNX ops: {', '.join(unsupported_ops)}); using {fallback_target}."

    raw = (error_text or "").strip()
    if raw.lower().startswith("failed to load openvino model:"):
        raw = raw.split(":", 1)[1].strip()
    snippet = " ".join(raw.split()) if raw else "unknown compile error"
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."
    return f"{prefix}: {snippet}; using {fallback_target}."


# Global singleton instance
_classifier_instance: Optional["ClassifierService"] = None
_classifier_lock = threading.Lock()


def get_classifier() -> "ClassifierService":
    """Get the shared classifier service instance (thread-safe)."""
    global _classifier_instance
    if _classifier_instance is None:
        with _classifier_lock:
            # Double-check pattern to avoid race condition
            if _classifier_instance is None:
                _classifier_instance = ClassifierService()
    return _classifier_instance


async def shutdown_classifier() -> None:
    """Shut down the shared classifier service instance if it exists."""
    global _classifier_instance
    if _classifier_instance is not None:
        await _classifier_instance.shutdown()
        with _classifier_lock:
            _classifier_instance = None


async def reload_classifier_out_of_band(*, full_restart: bool) -> None:
    """Rebuild or reload the classifier away from the event loop.

    Constructing ClassifierService detects hardware — child processes with five
    second timeouts apiece — and may load the model, synchronously. A settings
    save runs its reload as a background task on the event loop, so the
    construction must happen in a worker thread or every concurrent request
    stalls behind it (#313).
    """
    if full_restart:
        await shutdown_classifier()
    service = await asyncio.to_thread(get_classifier)
    await service.reload_bird_model()


def resolve_live_classifier(stored: Any) -> "ClassifierService":
    """Return the current live ClassifierService, repairing a stale cached ref.

    Consumers that cached the classifier singleton at startup (EventProcessor,
    AutoVideoClassifierService, BackfillService, etc.) would otherwise keep
    using a closed instance after a settings-driven reload calls
    ``shutdown_classifier`` and then ``get_classifier()`` creates a fresh
    singleton (see GitHub issue #50).

    Behaviour:
      * ``stored is None``         -> create / fetch the singleton.
      * ``stored`` is a real classifier that has been superseded by a newer
        singleton -> return the newer singleton.
      * ``stored`` is a real classifier and still current -> return it.
      * ``stored`` is anything else (test double, SimpleNamespace, MagicMock)
        -> return it unchanged so direct ``service._classifier = mock``
        injection in tests keeps working.
    """
    global _classifier_instance
    if stored is None:
        return get_classifier()
    if not isinstance(stored, ClassifierService):
        return stored
    if _classifier_instance is not None and _classifier_instance is not stored:
        return _classifier_instance
    if _classifier_instance is None:
        return get_classifier()
    return stored


class ModelInstance:
    """Represents a loaded TFLite model with its labels."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
        model_sha256: Optional[str] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
        # None means "read the label file", which is what every caller that has
        # not been given a checksum should keep doing.
        self.model_sha256 = model_sha256
        self.interpreter = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self.input_details = None
        self.output_details = None
        self._lock = threading.Lock()

    def load(self) -> bool:
        """Load the model and labels. Returns True if successful."""
        with self._lock:
            if self.loaded:
                return True

            self.labels, self.grouped_labels, label_source = _resolve_model_labels(
                self.labels_path,
                self.label_grouping,
                model_sha256=self.model_sha256,
                context=self.name,
            )
            if self.labels:
                log.info(f"Loaded {len(self.labels)} labels for {self.name}", label_source=label_source)

            if not os.path.exists(self.model_path):
                self.error = f"Model file not found: {self.model_path}"
                log.warning(f"{self.name} model not found", path=self.model_path)
                return False

            if tflite is None:
                self.error = "TFLite runtime not installed"
                log.error("TFLite runtime not installed")
                return False

            try:
                self.interpreter = tflite.Interpreter(model_path=self.model_path)
                self.interpreter.allocate_tensors()
                self.input_details = self.interpreter.get_input_details()
                self.output_details = self.interpreter.get_output_details()
                self.loaded = True
                self.error = None
                log.info(f"{self.name} model loaded successfully")
                return True
            except Exception as e:
                self.error = f"Failed to load model: {str(e)}"
                log.error(f"Failed to load {self.name} model", error=str(e))
                return False

    def _preprocess_image(self, image: Image.Image, target_width: int, target_height: int) -> np.ndarray:
        processed = _resize_with_preprocessing(
            image,
            max(int(target_width), int(target_height)),
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=int(self.preprocessing.get("padding_color", 0) or 0),
        )
        if processed.size != (target_width, target_height):
            processed = processed.resize((target_width, target_height), _resolve_interpolation(self.preprocessing))
        return np.array(processed, dtype=np.float32)

    def _run_inference(self, image: Image.Image) -> np.ndarray:
        """Internal method to run inference and return probability vector.

        Args:
            image: PIL Image to classify

        Returns:
            Normalized probability vector as numpy array
        """
        # Get expected input size from model
        input_details = self.input_details[0]
        input_shape = input_details["shape"]

        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300  # Default fallback

        # Preprocess image
        input_data = self._preprocess_image(image, target_width, target_height)

        # Normalize based on model input type
        raw_input_dtype = input_details.get("dtype")
        input_dtype = (
            raw_input_dtype
            if isinstance(raw_input_dtype, np.dtype)
            else np.dtype(raw_input_dtype)
            if isinstance(raw_input_dtype, type) and issubclass(raw_input_dtype, np.generic)
            else None
        )
        if input_dtype == np.dtype(np.float32):
            spec_mean = self.preprocessing.get("mean")
            spec_std = self.preprocessing.get("std")
            if spec_mean is not None or spec_std is not None:
                # Use per-channel mean/std provided in the model spec (ImageNet-style)
                mean = np.array(spec_mean if spec_mean is not None else [0.485, 0.456, 0.406], dtype=np.float32)
                std = np.array(spec_std if spec_std is not None else [0.229, 0.224, 0.225], dtype=np.float32)
                input_data = (input_data / 255.0 - mean) / std
            else:
                # Legacy MobileNet-style: maps [0, 255] to [-1, 1] via (x / 127.5) - 1
                input_data = (input_data - 127.5) / 127.5
        elif input_dtype is not None and np.issubdtype(input_dtype, np.integer):
            normalization = str(self.preprocessing.get("normalization") or "uint8").strip().lower()
            real_input = input_data
            if normalization not in {"uint8", "none"}:
                spec_mean = self.preprocessing.get("mean")
                spec_std = self.preprocessing.get("std")
                if spec_mean is not None or spec_std is not None:
                    mean = np.array(
                        spec_mean if spec_mean is not None else [0.485, 0.456, 0.406],
                        dtype=np.float32,
                    )
                    std = np.array(
                        spec_std if spec_std is not None else [0.229, 0.224, 0.225],
                        dtype=np.float32,
                    )
                    real_input = (real_input / 255.0 - mean) / std
                elif normalization in {"float32_0_1", "0_1"}:
                    real_input = real_input / 255.0
                else:
                    real_input = (real_input - 127.5) / 127.5

            quant_params = input_details.get("quantization_parameters", {})
            scales = np.asarray(quant_params.get("scales", []), dtype=np.float32)
            zero_points = np.asarray(quant_params.get("zero_points", []), dtype=np.float32)
            if scales.size > 0 and float(scales[0]) > 0:
                zero_point = float(zero_points[0]) if zero_points.size > 0 else 0.0
                quantized = np.rint(real_input / float(scales[0]) + zero_point)
                limits = np.iinfo(input_dtype)
                input_data = np.clip(quantized, limits.min, limits.max).astype(input_dtype)
            elif input_dtype == np.dtype(np.uint8):
                # Compatibility for older uint8 models that omit quantization
                # metadata and directly consume raw RGB bytes.
                input_data = np.clip(real_input, 0, 255).astype(np.uint8)
            else:
                raise InvalidInferenceOutputError(
                    backend="tflite",
                    provider="tflite",
                    detail=f"{self.name} int8 input is missing valid quantization metadata",
                )

        # Add batch dimension
        input_data = np.expand_dims(input_data, axis=0)

        # Run inference protected by lock
        with self._lock:
            self.interpreter.set_tensor(input_details["index"], input_data)
            self.interpreter.invoke()

            # Get output
            output_details = self.output_details[0]
            output_data = self.interpreter.get_tensor(output_details["index"])

        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize if needed
        raw_output_dtype = output_details.get("dtype")
        output_dtype = (
            raw_output_dtype
            if isinstance(raw_output_dtype, np.dtype)
            else np.dtype(raw_output_dtype)
            if isinstance(raw_output_dtype, type) and issubclass(raw_output_dtype, np.generic)
            else None
        )
        if output_dtype is not None and np.issubdtype(output_dtype, np.integer):
            quant_params = output_details.get("quantization_parameters", {})
            scales = np.asarray(quant_params.get("scales", []), dtype=np.float32)
            zero_points = np.asarray(quant_params.get("zero_points", []), dtype=np.float32)

            if scales.size == results.size and results.ndim == 1:
                zero_values = zero_points if zero_points.size == results.size else np.zeros_like(scales)
                results = (results - zero_values) * scales
            elif scales.size > 0 and float(scales[0]) > 0:
                zero_point = float(zero_points[0]) if zero_points.size > 0 else 0.0
                results = (results - zero_point) * float(scales[0])
            elif output_dtype == np.dtype(np.uint8):
                results = results / 255.0
            else:
                raise InvalidInferenceOutputError(
                    backend="tflite",
                    provider="tflite",
                    detail=f"{self.name} int8 output is missing valid quantization metadata",
                )

        # Softmax if needed (logits vs probabilities)
        finite_results = results[np.isfinite(results)]
        if finite_results.size == 0:
            log.warning("TFLite inference produced no finite outputs", model=self.name)
            raise InvalidInferenceOutputError(
                backend="tflite",
                provider="tflite",
                detail=f"{self.name} inference produced no finite outputs",
            )

        output_min = float(finite_results.min())
        output_max = float(finite_results.max())
        is_probability = output_min >= 0 and output_max <= 1.0

        if is_probability:
            results = _normalize_probability_vector(results, context=f"{self.name}:tflite")
        else:
            results = _safe_softmax(results, context=f"{self.name}:tflite")

        return results

    def classify(self, image: Image.Image, input_context: Any | None = None) -> list[dict]:
        """Classify an image using this model.

        Args:
            image: PIL Image to classify

        Returns:
            List of top 5 classifications with score and label
        """
        if not self.loaded or not self.interpreter:
            log.warning(f"{self.name} model not loaded, cannot classify")
            return []

        # Run inference and get probability vector
        results = self._run_inference(image)

        max_results = settings.classification.max_classification_results
        grouped_labels = _resolve_grouped_labels(
            self.labels,
            label_grouping=self.label_grouping,
            existing_grouped_labels=self.grouped_labels,
        )
        return _build_classification_results(
            results,
            self.labels,
            top_k=max_results,
            grouped_labels=grouped_labels,
        )

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble).

        Args:
            image: PIL Image to classify

        Returns:
            Normalized probability vector as numpy array
        """
        if not self.loaded or not self.interpreter:
            return np.array([])

        return self._run_inference(image)

    def cleanup(self):
        """Clean up model resources."""
        with self._lock:
            if self.interpreter is not None:
                # TFLite interpreters don't have explicit cleanup,
                # but we can dereference it to allow garbage collection
                self.interpreter = None
            self.loaded = False
            log.info(f"{self.name} model resources cleaned up")

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.interpreter is not None,
            "model_path": self.model_path,
            "runtime": "tflite",
        }


class ONNXModelInstance:
    """Represents a loaded ONNX model with its labels (for high-accuracy models)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
        input_size: int = 384,
        ort_providers: Optional[list[str]] = None,
        model_sha256: Optional[str] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
        # None means "read the label file", which is what any caller without a
        # checksum should keep doing.
        self.model_sha256 = model_sha256
        self.input_size = input_size
        self.ort_providers = list(ort_providers or ["CPUExecutionProvider"])
        self.session = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self._lock = threading.Lock()

        # ImageNet normalization defaults (used by timm models)
        self.mean = np.array(self.preprocessing.get("mean", [0.485, 0.456, 0.406]))
        self.std = np.array(self.preprocessing.get("std", [0.229, 0.224, 0.225]))

    def load(self) -> bool:
        """Load the ONNX model and labels. Returns True if successful."""
        if self.loaded:
            return True

        if not ONNX_AVAILABLE:
            self.error = "ONNX Runtime not installed"
            log.error("ONNX Runtime not installed")
            return False

        self.labels, self.grouped_labels, label_source = _resolve_model_labels(
            self.labels_path,
            self.label_grouping,
            model_sha256=self.model_sha256,
            context=self.name,
        )
        if self.labels:
            log.info(f"Loaded {len(self.labels)} labels for ONNX model {self.name}", label_source=label_source)

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} ONNX model not found", path=self.model_path)
            return False

        try:
            # Configure ONNX Runtime session with CPU optimizations
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4  # Use multiple threads

            # Use providers resolved by ClassifierService (already validated/fallback-aware)
            providers = list(self.ort_providers or ["CPUExecutionProvider"])
            if "CUDAExecutionProvider" in providers:
                _preload_onnxruntime_cuda_runtime_libraries()
            self.session = ort.InferenceSession(self.model_path, sess_options, providers=providers)
            self.loaded = True
            self.error = None
            log.info(f"{self.name} ONNX model loaded successfully", input_size=self.input_size, providers=providers)
            return True
        except Exception as e:
            self.error = f"Failed to load ONNX model: {str(e)}"
            log.error(f"Failed to load {self.name} ONNX model", error=str(e))
            return False

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        """Preprocess image for ONNX inference."""
        processed = _resize_with_preprocessing(
            image,
            self.input_size,
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=128,
        )
        if self.preprocessing.get("normalization") == "uint8":
            # Quantized/SSD-style models expect raw uint8 NHWC input
            return np.array(processed, dtype=np.uint8)[np.newaxis, ...]
        arr = np.array(processed).astype(np.float32) / 255.0
        if _classifier_wants_bgr(self.preprocessing):
            arr = arr[:, :, ::-1]
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # HWC -> CHW (ONNX expects NCHW)
        return arr[np.newaxis, ...].astype(np.float32)  # Add batch dimension

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply softmax to convert logits to probabilities."""
        return _safe_softmax(x, context=f"{self.name}:onnx")

    def _run_inference(self, input_name: str, input_tensor: np.ndarray) -> list[Any]:
        """Run the provider and expose execution failures to recovery policy."""
        try:
            with self._lock:
                return self.session.run(None, {input_name: input_tensor})
        except Exception as exc:
            log.error(f"ONNX inference failed for {self.name}", error=str(exc))
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=(self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} inference execution failed: {exc}",
                diagnostics={"exception_type": type(exc).__name__},
            ) from exc

    def _probabilities_from_outputs(self, outputs: list[Any]) -> np.ndarray:
        """Validate provider output shape before converting logits to probabilities."""
        try:
            logits = np.asarray(outputs[0])[0]
            probs = self._softmax(logits)
        except InvalidInferenceOutputError:
            raise
        except Exception as exc:
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=(self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} returned an invalid output structure: {exc}",
                diagnostics={"exception_type": type(exc).__name__},
            ) from exc
        if probs.size == 0:
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=(self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} inference produced no finite probabilities",
            )
        return probs

    def classify(self, image: Image.Image, top_k: int = 5, input_context: Any | None = None) -> list[dict]:
        """Classify an image using this ONNX model."""
        if not self.loaded or not self.session:
            log.warning(f"{self.name} ONNX model not loaded, cannot classify")
            return []

        input_tensor = self._preprocess(image)
        input_name = self.session.get_inputs()[0].name
        outputs = self._run_inference(input_name, input_tensor)
        probs = self._probabilities_from_outputs(outputs)

        grouped_labels = _resolve_grouped_labels(
            self.labels,
            label_grouping=self.label_grouping,
            existing_grouped_labels=self.grouped_labels,
        )
        return _build_classification_results(
            probs,
            self.labels,
            top_k=top_k,
            grouped_labels=grouped_labels,
        )

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.session:
            return np.array([])

        input_tensor = self._preprocess(image)
        input_name = self.session.get_inputs()[0].name
        outputs = self._run_inference(input_name, input_tensor)
        return self._probabilities_from_outputs(outputs)

    def probe(self, image: Image.Image) -> dict[str, Any]:
        provider = self.ort_providers[0] if self.ort_providers else "CPUExecutionProvider"
        input_tensor = self._preprocess(image)
        report: dict[str, Any] = {
            "status": "ok",
            "provider": str(provider),
            "active_providers": [],
            "input_summary": _summarize_numeric_array(input_tensor, name="input_tensor"),
        }
        if not self.loaded or not self.session:
            report["status"] = "compile_failed"
            report["error"] = self.error or "ONNX Runtime model is not loaded"
            return report

        try:
            try:
                report["active_providers"] = list(self.session.get_providers() or [])
            except Exception:
                report["active_providers"] = []
            input_name = self.session.get_inputs()[0].name
            with self._lock:
                outputs = self.session.run(None, {input_name: input_tensor})
            logits = np.asarray(outputs[0])
            if logits.ndim > 0 and logits.shape[0] == 1:
                logits = logits[0]
            report["output_summary"] = _summarize_numeric_array(logits, name="output_logits")
            if logits.size == 0 or not np.isfinite(logits).any():
                report["status"] = "invalid_output"
            return report
        except Exception as exc:
            report["status"] = "runtime_error"
            report["error"] = _summarize_runtime_exception(exc, max_len=600)
            return report

    def cleanup(self):
        """Clean up ONNX model resources."""
        if self.session is not None:
            # ONNX sessions don't have explicit cleanup,
            # but we can dereference to allow garbage collection
            self.session = None
        self.loaded = False
        log.info(f"{self.name} ONNX model resources cleaned up")

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.session is not None,
            "model_path": self.model_path,
            "runtime": "onnx",
            "input_size": self.input_size,
        }


class OpenVINOModelInstance:
    """Represents a loaded ONNX model compiled with OpenVINO (Intel CPU/GPU)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
        input_size: int = 384,
        device_name: str = "CPU",
        startup_self_test_enabled: bool | None = None,
        model_sha256: Optional[str] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
        # None means "read the label file", which is what any caller without a
        # checksum should keep doing.
        self.model_sha256 = model_sha256
        self.input_size = input_size
        self.device_name = device_name
        self._startup_self_test_enabled = (
            _openvino_gpu_startup_self_test_enabled()
            if startup_self_test_enabled is None
            else bool(startup_self_test_enabled)
        )
        self.core = None
        self.compiled_model = None
        self.input_name: Optional[str] = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._last_startup_self_test_diagnostics: dict[str, Any] | None = None
        self._last_startup_self_test_error: str | None = None
        self._startup_self_test_ran = False

        self.mean = np.array(self.preprocessing.get("mean", [0.485, 0.456, 0.406]))
        self.std = np.array(self.preprocessing.get("std", [0.229, 0.224, 0.225]))

    def _collect_runtime_diagnostics(
        self,
        *,
        input_tensor: np.ndarray | None = None,
        logits: np.ndarray | None = None,
    ) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {
            "device_name": str(self.device_name),
            "model_path": self.model_path,
        }
        compiled_properties: dict[str, Any] = {}
        if self.compiled_model is not None:
            for name in ("INFERENCE_PRECISION_HINT", "NUM_STREAMS", "PERFORMANCE_HINT", "EXECUTION_DEVICES"):
                try:
                    value = self.compiled_model.get_property(name)
                    if isinstance(value, np.ndarray):
                        compiled_properties[name] = value.tolist()
                    elif isinstance(value, tuple):
                        compiled_properties[name] = list(value)
                    else:
                        compiled_properties[name] = str(value)
                except Exception as exc:
                    compiled_properties[name] = f"ERROR: {exc}"
        diagnostics["compile_properties"] = compiled_properties
        if input_tensor is not None:
            diagnostics["input_summary"] = _summarize_numeric_array(input_tensor, name="input_tensor")
        if logits is not None:
            diagnostics["output_summary"] = _summarize_numeric_array(logits, name="output_logits")
        return diagnostics

    def _build_startup_self_test_image(self) -> Image.Image:
        size = max(8, int(self.input_size))
        x = np.linspace(0, 255, size, dtype=np.uint8)
        y = np.linspace(255, 0, size, dtype=np.uint8)
        red = np.tile(x, (size, 1))
        green = np.tile(y[:, None], (1, size))
        blue = np.full((size, size), 127, dtype=np.uint8)
        return Image.fromarray(np.stack((red, green, blue), axis=2), mode="RGB")

    def _run_gpu_startup_self_test(self) -> None:
        if not self._startup_self_test_enabled:
            return
        self._startup_self_test_ran = True
        image = self._build_startup_self_test_image()
        input_tensor = self._preprocess(image)
        logits = self._infer_output_tensor(image)
        self._last_startup_self_test_diagnostics = self._collect_runtime_diagnostics(
            input_tensor=input_tensor,
            logits=logits,
        )
        self._last_startup_self_test_error = None
        if logits.size == 0 or not np.isfinite(logits).any():
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=self.device_name,
                detail=f"{self.name} inference produced no finite probabilities during startup self-test",
                diagnostics=dict(self._last_startup_self_test_diagnostics),
            )
        # Also detect near-uniform/degenerate output: if the logit range is
        # extremely small (<0.5), the softmax will be nearly uniform regardless
        # of the input — a sign that GPU inference is silently broken.
        finite_logits = logits[np.isfinite(logits)]
        if finite_logits.size > 1:
            logit_range = float(finite_logits.max() - finite_logits.min())
            if logit_range < 0.5:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=(
                        f"{self.name} inference produced near-uniform logits (range={logit_range:.4f}) "
                        "during startup self-test — GPU may be silently producing degenerate output"
                    ),
                    diagnostics=dict(self._last_startup_self_test_diagnostics),
                )

    def load(self) -> bool:
        if self.loaded:
            return True

        if not OPENVINO_AVAILABLE or OpenVINOCore is None:
            self.error = "OpenVINO runtime not installed"
            log.error("OpenVINO runtime not installed")
            return False

        self.labels, self.grouped_labels, label_source = _resolve_model_labels(
            self.labels_path,
            self.label_grouping,
            model_sha256=self.model_sha256,
            context=self.name,
        )
        if self.labels:
            log.info(f"Loaded {len(self.labels)} labels for OpenVINO model {self.name}", label_source=label_source)

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} OpenVINO model not found", path=self.model_path)
            return False

        try:
            self.core = OpenVINOCore()

            # Enable caching so GPU model compilation isn't repeated from scratch
            # on every worker process startup, avoiding readiness timeouts.
            cache_dir = os.getenv("OPENVINO_CACHE_DIR", "/tmp/openvino_cache")
            os.makedirs(cache_dir, exist_ok=True)
            self.core.set_property({"CACHE_DIR": cache_dir})

            model = self.core.read_model(self.model_path)

            # Intel GPUs default to f16 inference precision. Un-quantized ONNX models
            # often have intermediate activations >65504, which overflow f16, resulting
            # in non-finite logits (NaN/inf) and crashing the strict softmax pipeline.
            config = {"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1"}
            _is_gpu = self.device_name == "GPU" or str(self.device_name).startswith("GPU.")
            _is_npu = self.device_name == "NPU" or str(self.device_name).startswith("NPU.")
            if _is_gpu or _is_npu:
                # Both the iGPU and NPU need a static batch dimension (the NPU compiler
                # *requires* it; on the iGPU it avoids the clWaitForEvents -14 crash), so
                # the dynamic-batch reshape below applies to both accelerators.
                if _is_gpu:
                    # Intel GPU defaults to f16; un-quantized ONNX activations >65504
                    # overflow f16 → non-finite logits, so force f32 on the GPU only.
                    config["INFERENCE_PRECISION_HINT"] = "f32"
                    config.update(_openvino_gpu_optional_compile_properties())
                # NPU: only f16/i8 are valid for INFERENCE_PRECISION_HINT (f32 is rejected
                # at compile — "Wrong value f32 ... Supported values: f16, i8"), so leave
                # the NPU at its default precision. Validated to give finite, CPU-matching
                # output (rope_vit_b14: top-5 identical to CPU).
                try:
                    partial = model.inputs[0].get_partial_shape()
                    if partial.rank.is_static and partial[0].is_dynamic:
                        static_shape = [1] + [partial[d].get_length() for d in range(1, partial.rank.get_length())]
                        model.reshape(static_shape)
                except Exception:
                    pass  # Non-fatal; proceed with original dynamic shape

            self.compiled_model = self.core.compile_model(model, self.device_name, config=config)
            self.input_name = self.compiled_model.inputs[0].get_any_name()
            if self._startup_self_test_enabled and (_is_gpu or _is_npu):
                # Reused for the NPU as well — validates the compiled model isn't
                # producing degenerate / non-finite logits on this accelerator.
                self._run_gpu_startup_self_test()
            self.loaded = True
            self.error = None
            log.info(
                "OpenVINO model loaded successfully",
                model=self.name,
                device=self.device_name,
                input_size=self.input_size,
            )
            return True
        except InvalidInferenceOutputError as exc:
            self.error = f"Failed OpenVINO model startup self-test: {exc.detail}"
            self._last_startup_self_test_error = self.error
            log.warning(
                "OpenVINO model failed startup self-test",
                model=self.name,
                device=self.device_name,
                detail=exc.detail,
                diagnostics=exc.diagnostics,
            )
            self.compiled_model = None
            self.core = None
            self.loaded = False
            return False
        except Exception as e:
            self.error = f"Failed to load OpenVINO model: {str(e)}"
            log.error(f"Failed to load {self.name} OpenVINO model", error=str(e), device=self.device_name)
            return False

    def current_compile_properties(self) -> dict[str, Any]:
        return self._collect_runtime_diagnostics().get("compile_properties") or {}

    def startup_self_test_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._startup_self_test_enabled),
            "ran": bool(self._startup_self_test_ran),
            "error": self._last_startup_self_test_error,
            "diagnostics": dict(self._last_startup_self_test_diagnostics or {}),
        }

    def probe(self, image: Image.Image) -> dict[str, Any]:
        input_tensor = self._preprocess(image)
        report: dict[str, Any] = {
            "status": "ok",
            "device": str(self.device_name),
            "compile_properties": self.current_compile_properties(),
            "input_summary": _summarize_numeric_array(input_tensor, name="input_tensor"),
        }
        try:
            logits = self._infer_output_tensor(image)
            report["output_summary"] = _summarize_numeric_array(logits, name="output_logits")
            if logits.size == 0 or not np.isfinite(logits).any():
                report["status"] = "invalid_output"
            return report
        except Exception as exc:
            report["status"] = "runtime_error"
            report["error"] = _summarize_runtime_exception(exc, max_len=600)
            return report

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        processed = _resize_with_preprocessing(
            image,
            self.input_size,
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=128,
        )
        arr = np.array(processed).astype(np.float32) / 255.0
        if _classifier_wants_bgr(self.preprocessing):
            arr = arr[:, :, ::-1]
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # NCHW
        return arr[np.newaxis, ...].astype(np.float32)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        return _safe_softmax(x, context=f"{self.name}:openvino")

    def _infer_output_tensor(self, image: Image.Image) -> np.ndarray:
        if self.compiled_model is None or self.input_name is None:
            return np.array([])

        input_tensor = self._preprocess(image)
        # _preprocess emits NCHW [1,3,H,W]. Some exported models (e.g. MobileNet)
        # expect NHWC [1,H,W,3]; feed whatever the compiled model declares.
        try:
            dims = self.compiled_model.inputs[0].get_partial_shape()
            if dims.rank.is_static and dims.rank.get_length() == 4:
                last = dims[3]
                second = dims[1]
                if last.is_static and last.get_length() == 3 and not (second.is_static and second.get_length() == 3):
                    input_tensor = np.ascontiguousarray(np.transpose(input_tensor, (0, 2, 3, 1)))
        except Exception:
            pass
        with self._lock:
            infer_request = self.compiled_model.create_infer_request()
            outputs = infer_request.infer({self.input_name: input_tensor})
        try:
            raw = outputs[self.compiled_model.outputs[0]]
        except Exception:
            raw = next(iter(outputs.values()))
        return np.asarray(raw)

    def _infer_logits(self, image: Image.Image) -> np.ndarray:
        raw = self._infer_output_tensor(image)
        if raw.ndim > 0 and raw.shape[0] == 1:
            return raw[0]
        return raw

    def classify(self, image: Image.Image, top_k: int = 5, input_context: Any | None = None) -> list[dict]:
        if not self.loaded or self.compiled_model is None:
            log.warning(f"{self.name} OpenVINO model not loaded, cannot classify")
            return []
        try:
            input_tensor = self._preprocess(image)
            logits = self._infer_logits(image)
            if logits.size == 0:
                return []
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=f"{self.name} inference produced no finite probabilities",
                    diagnostics=self._collect_runtime_diagnostics(
                        input_tensor=input_tensor,
                        logits=logits,
                    ),
                )
            grouped_labels = _resolve_grouped_labels(
                self.labels,
                label_grouping=self.label_grouping,
                existing_grouped_labels=self.grouped_labels,
            )
            return _build_classification_results(
                probs,
                self.labels,
                top_k=top_k,
                grouped_labels=grouped_labels,
            )
        except InvalidInferenceOutputError:
            raise
        except Exception as e:
            log.error(f"OpenVINO inference failed for {self.name}", error=str(e), device=self.device_name)
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=str(self.device_name),
                detail=f"{self.name} runtime exception: {_summarize_runtime_exception(e)}",
            ) from e

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        if not self.loaded or self.compiled_model is None:
            return np.array([])
        try:
            input_tensor = self._preprocess(image)
            logits = self._infer_logits(image)
            if logits.size == 0:
                return np.array([])
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=f"{self.name} inference produced no finite probabilities",
                    diagnostics=self._collect_runtime_diagnostics(
                        input_tensor=input_tensor,
                        logits=logits,
                    ),
                )
            return probs
        except InvalidInferenceOutputError:
            raise
        except Exception as e:
            log.error("OpenVINO raw classification failed", error=str(e), device=self.device_name)
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=str(self.device_name),
                detail=f"{self.name} runtime exception: {_summarize_runtime_exception(e)}",
            ) from e

    def cleanup(self):
        self.compiled_model = None
        self.core = None
        self.loaded = False
        log.info(f"{self.name} OpenVINO model resources cleaned up", device=self.device_name)

    def get_status(self) -> dict:
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.compiled_model is not None,
            "model_path": self.model_path,
            "runtime": "openvino",
            "input_size": self.input_size,
            "device": self.device_name,
            "compile_properties": self.current_compile_properties(),
            "startup_self_test": self.startup_self_test_status(),
        }


class ClassifierService:
    """Service for managing multiple classification models (TFLite and ONNX)."""

    # Union type for model instances
    ModelType = ModelInstance | ONNXModelInstance | OpenVINOModelInstance

    def __init__(self, *, supervisor: Any | None = None, worker_process_mode: bool = False):
        self._models: dict[str, ClassifierService.ModelType] = {}
        self._models_lock = threading.Lock()
        self._worker_process_mode = bool(worker_process_mode)
        configured_mode = (
            str(getattr(settings.classification, "image_execution_mode", "in_process") or "in_process").strip().lower()
        )
        self._image_execution_mode = "in_process" if self._worker_process_mode else configured_mode
        self._classifier_supervisor = supervisor
        self._video_supervisor = supervisor
        self._bird_crop_service = bird_crop_service
        self._crop_source_resolver = crop_source_resolver
        # Use dedicated executors so long-running video analysis cannot starve
        # live snapshot/audio-adjacent classification work.
        video_workers = max(
            1,
            min(
                2,
                int(getattr(settings.classification, "video_classification_max_concurrent", 1) or 1),
            ),
        )
        image_workers = CLASSIFIER_IMAGE_MAX_CONCURRENT
        live_admission_capacity = image_workers
        background_admission_capacity = 1
        if self._image_execution_mode == "subprocess":
            live_admission_capacity = int(
                getattr(settings.classification, "live_worker_count", image_workers) or image_workers
            )
            background_admission_capacity = int(getattr(settings.classification, "background_worker_count", 1) or 1)
        self._image_executor = ThreadPoolExecutor(max_workers=image_workers, thread_name_prefix="ml_image_worker")
        self._live_image_executor = ThreadPoolExecutor(
            max_workers=image_workers, thread_name_prefix="ml_live_image_worker"
        )
        self._background_image_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml_background_worker")
        self._video_executor = ThreadPoolExecutor(max_workers=video_workers, thread_name_prefix="ml_video_worker")
        self._image_admission_timeouts = 0
        self._live_image_admission_timeouts = 0
        self._classification_admission = ClassificationAdmissionCoordinator(
            live_capacity=live_admission_capacity,
            background_capacity=background_admission_capacity,
            live_lease_timeout_seconds=CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS,
            background_lease_timeout_seconds=CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS,
            default_queue_timeout_seconds=CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS,
        )
        # Backward-compatible alias for any external references.
        self._executor = self._image_executor
        if not self._worker_process_mode and self._video_supervisor is None:
            video_timeout_seconds = float(
                getattr(settings.classification, "video_classification_timeout_seconds", 180) or 180.0
            )
            image_hard_deadline_seconds = float(
                getattr(settings.classification, "worker_hard_deadline_seconds", 35.0) or 35.0
            )
            background_hard_deadline_seconds = max(
                image_hard_deadline_seconds,
                float(
                    getattr(
                        settings.classification,
                        "background_worker_hard_deadline_seconds",
                        120.0,
                    )
                    or 120.0
                ),
            )
            isolated_supervisor = ClassifierSupervisor(
                live_worker_count=int(
                    getattr(settings.classification, "live_worker_count", image_workers) or image_workers
                ),
                background_worker_count=int(getattr(settings.classification, "background_worker_count", 1) or 1),
                video_worker_count=video_workers,
                heartbeat_timeout_seconds=float(
                    getattr(settings.classification, "worker_heartbeat_timeout_seconds", 5.0) or 5.0
                ),
                hard_deadline_seconds=image_hard_deadline_seconds,
                background_hard_deadline_seconds=background_hard_deadline_seconds,
                video_hard_deadline_seconds=max(image_hard_deadline_seconds, video_timeout_seconds + 15.0),
                worker_ready_timeout_seconds=float(
                    getattr(settings.classification, "worker_ready_timeout_seconds", 20.0) or 20.0
                ),
                video_worker_ready_timeout_seconds=max(
                    float(getattr(settings.classification, "worker_ready_timeout_seconds", 20.0) or 20.0),
                    min(60.0, max(30.0, video_timeout_seconds / 2.0)),
                ),
            )
            self._video_supervisor = isolated_supervisor
            if self._image_execution_mode == "subprocess":
                self._classifier_supervisor = isolated_supervisor
        self._selected_inference_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        self._active_inference_provider = "tflite"
        self._inference_backend = "tflite"
        self._inference_fallback_reason: Optional[str] = None
        self._openvino_model_compile_ok: Optional[bool] = None
        self._openvino_model_compile_device: Optional[str] = None
        self._openvino_model_compile_error: Optional[str] = None
        self._openvino_model_compile_unsupported_ops: list[str] = []
        self._runtime_benchmarks: dict[str, Any] = {}
        self._runtime_invalid_output_failures = 0
        self._runtime_fallback_recoveries = 0
        self._runtime_gpu_retries = 0
        self._runtime_gpu_restore_attempts = 0
        self._runtime_gpu_restore_successes = 0
        self._runtime_gpu_restore_failures = 0
        self._gpu_invalid_retry_remaining = CLASSIFIER_GPU_INVALID_RETRY_LIMIT
        self._gpu_restore_not_before_monotonic: float = 0.0
        self._inference_health = InferenceHealth(
            min_samples=CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_THRESHOLD,
            cooldown_seconds=CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS,
        )
        self._bird_model_artifact_metadata: dict[str, Any] = {}
        self._model_config_warnings: list[str] = []
        self._bird_model_compatibility: dict[str, Any] = {}
        self._accel_caps_ttl_seconds = CLASSIFIER_ACCEL_PROBE_TTL_SECONDS
        self._accel_caps_last_refreshed_monotonic: float | None = None
        startup_status.publish("detecting_hardware", 15)
        self._accel_caps = self._refresh_accel_caps(force=True)
        if self._worker_process_mode or self._image_execution_mode != "subprocess":
            startup_status.publish("loading_model", 30)
            try:
                self._init_bird_model()
            except Exception:
                startup_status.mark_failed("loading_model")
                raise
            startup_status.publish("model_ready" if self.model_loaded else "model_unavailable", 60)

    def _get_model_paths(self, model_file: str, labels_file: str) -> tuple[str, str]:
        """Get full paths for model and labels files."""
        persistent_dir = "/data/models"
        fallback_dir = os.path.join(os.path.dirname(__file__), "../assets")

        if os.path.exists(os.path.join(persistent_dir, model_file)):
            assets_dir = persistent_dir
            log.info("Using persistent model directory", path=persistent_dir)
        else:
            assets_dir = fallback_dir
            log.info("Using fallback model directory", path=fallback_dir)

        model_path = os.path.join(assets_dir, model_file)
        labels_path = os.path.join(assets_dir, labels_file)

        return model_path, labels_path

    def _resolve_active_bird_model_spec(self) -> dict[str, Any]:
        from app.services.catalogue_labels import published_model_sha256
        from app.services.model_manager import model_manager

        spec = dict(model_manager.get_active_model_spec() or {})
        model_id = str(spec.get("model_id") or self._resolve_active_model_id())
        spec = _apply_host_validated_provider_policy(spec, model_id=model_id)
        model_path = str(spec.get("model_path") or "")
        labels_path = str(spec.get("labels_path") or "")
        input_size = int(spec.get("input_size") or 224)
        preprocessing = spec.get("preprocessing")
        label_grouping = spec.get("label_grouping")
        supported_inference_providers = list(spec.get("supported_inference_providers") or [])
        candidate_inference_providers = list(spec.get("candidate_inference_providers") or supported_inference_providers)
        runtime = str(spec.get("runtime") or "tflite")
        crop_generator = dict(spec.get("crop_generator") or {})
        model_config_warnings = list(spec.get("model_config_warnings") or [])

        if not os.path.exists(model_path):
            model_path, labels_path = self._get_model_paths(
                "model.tflite",
                "labels.txt",
            )
            runtime = "tflite"
            crop_generator = CropGeneratorConfig().model_dump(exclude_none=True)

        return {
            "model_id": model_id,
            # The registry's published checksum for these weights, which is what
            # the catalogue keys its output mapping on. Resolved here so the
            # loaders can ask the catalogue for labels instead of the file.
            "model_sha256": published_model_sha256(model_id, region=spec.get("resolved_region")),
            "model_path": model_path,
            "labels_path": labels_path,
            "input_size": input_size,
            "preprocessing": preprocessing,
            "label_grouping": dict(label_grouping or {}),
            "runtime": runtime,
            "resolved_region": spec.get("resolved_region"),
            "supported_inference_providers": supported_inference_providers,
            "candidate_inference_providers": candidate_inference_providers,
            "model_config_warnings": model_config_warnings,
            "host_added_inference_providers": list(spec.get("host_added_inference_providers") or []),
            "host_validated_inference_providers": list(spec.get("host_validated_inference_providers") or []),
            "host_provider_preference_order": list(spec.get("host_provider_preference_order") or []),
            "host_validation_applied": bool(spec.get("host_validation_applied")),
            "crop_generator": crop_generator,
        }

    def _classify_model_artifact_type(self, model_path: str) -> str:
        suffix = Path(str(model_path or "")).suffix.lower()
        if suffix == ".onnx":
            return "onnx"
        if suffix == ".xml":
            return "openvino_ir_xml"
        if suffix == ".tflite":
            return "tflite"
        return suffix.lstrip(".") or "unknown"

    def _runtime_model_snapshot(self) -> dict[str, Any]:
        spec = self._resolve_active_bird_model_spec()
        snapshot = {
            "model_path": str(spec.get("model_path") or ""),
            "labels_path": str(spec.get("labels_path") or ""),
            "input_size": int(spec.get("input_size") or 0),
            "preprocessing": dict(spec.get("preprocessing") or {}),
            "label_grouping": dict(spec.get("label_grouping") or {}),
            "declared_runtime": str(spec.get("runtime") or ""),
            "model_type": self._classify_model_artifact_type(str(spec.get("model_path") or "")),
            "model_config_warnings": list(spec.get("model_config_warnings") or []),
        }
        snapshot.update(dict(self._bird_model_artifact_metadata or {}))
        return snapshot

    def active_model_sha256(self) -> Optional[str]:
        """The digest of the loaded classification model file, or None.

        Computed once when the model loads; this is the checksum the species
        catalogue keys its output mappings on.
        """
        value = str((self._bird_model_artifact_metadata or {}).get("model_sha256") or "").strip().lower()
        return value or None

    def _gpu_runtime_settings_snapshot(self) -> dict[str, Any]:
        startup_self_test_enabled = _openvino_gpu_startup_self_test_enabled() and not self._worker_process_mode
        return {
            "startup_self_test_enabled": startup_self_test_enabled,
            "cache_dir": os.getenv("OPENVINO_CACHE_DIR", "/tmp/openvino_cache"),
            "requested_compile_properties": {
                "PERFORMANCE_HINT": "LATENCY",
                "NUM_STREAMS": "1",
                "INFERENCE_PRECISION_HINT": "f32",
                **_openvino_gpu_optional_compile_properties(),
            },
            "invalid_retry_limit": CLASSIFIER_GPU_INVALID_RETRY_LIMIT,
            "restore_cooldown_seconds": CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS,
        }

    def _update_bird_model_compatibility(self, *, device: str, status: str) -> None:
        normalized_device = str(device or "").upper() or None
        normalized_status = str(status or "") or None
        trust_state = "trusted" if normalized_status == "ok" else "untrusted"
        devices = dict((self._bird_model_compatibility or {}).get("devices") or {})
        if normalized_device:
            devices[normalized_device] = {
                "artifact_trust_state": trust_state,
                "last_probe_status": normalized_status,
            }
        self._bird_model_compatibility = {"devices": devices}

    def _active_openvino_model(self) -> OpenVINOModelInstance | None:
        bird = self._models.get("bird")
        if _safe_isinstance(bird, OpenVINOModelInstance):
            return bird
        return None

    def _openvino_runtime_snapshot(
        self,
        *,
        active_backend: str,
        active_provider: str,
    ) -> dict[str, Any]:
        active_model = self._active_openvino_model()
        snapshot = {
            "selected_provider": _normalize_inference_provider(
                getattr(settings.classification, "inference_provider", "auto")
            ),
            "active_provider": active_provider,
            "inference_backend": active_backend,
            "model": self._runtime_model_snapshot(),
            "compatibility": dict(self._bird_model_compatibility or {}),
            "gpu_settings": self._gpu_runtime_settings_snapshot(),
            "compile_diagnostics": {
                "compile_ok": self._openvino_model_compile_ok,
                "compile_device": self._openvino_model_compile_device,
                "compile_error": self._openvino_model_compile_error,
                "compile_unsupported_ops": list(self._openvino_model_compile_unsupported_ops or []),
            },
            "active_model_compile_properties": {},
            "startup_self_test": None,
            "runtime_benchmarks": dict(self._runtime_benchmarks or {}),
        }
        if active_model is not None:
            snapshot["active_model_compile_properties"] = active_model.current_compile_properties()
            snapshot["startup_self_test"] = active_model.startup_self_test_status()
        return snapshot

    def _append_inference_fallback_reason(self, reason: str) -> None:
        reason = str(reason or "").strip()
        if not reason:
            return
        prev_reason = self._inference_fallback_reason
        self._inference_fallback_reason = f"{prev_reason}; {reason}" if prev_reason else reason

    def _refresh_accel_caps(self, *, force: bool = False) -> dict[str, Any]:
        """Detect capabilities. Expensive: spawns child processes.

        `_detect_acceleration_capabilities()` starts short-lived Python processes
        that import an inference runtime and enumerate devices, each with a five
        second timeout. Never call this from a request handler; use
        `_accel_caps_for_read()` there instead (#313).
        """
        now = time.monotonic()
        if (
            not force
            and self._accel_caps_last_refreshed_monotonic is not None
            and now - self._accel_caps_last_refreshed_monotonic < self._accel_caps_ttl_seconds
        ):
            return self._accel_caps
        self._accel_caps = _detect_acceleration_capabilities()
        self._accel_caps_last_refreshed_monotonic = now
        return self._accel_caps

    def _accel_caps_for_read(self) -> dict[str, Any]:
        """The last known capabilities, without going to find out.

        A status request used to refresh these inline, which spawned subprocesses
        on the event loop and stalled every concurrent request behind them. A
        reporter's capture showed `/api/version`, which returns a fixed string,
        waiting 22.5 seconds for its first byte (#313).
        """
        return self._accel_caps

    def _accel_caps_age_seconds(self) -> Optional[float]:
        """How old the reading is, or None if one has never been taken."""
        if self._accel_caps_last_refreshed_monotonic is None:
            return None
        return max(0.0, time.monotonic() - self._accel_caps_last_refreshed_monotonic)

    def accel_caps_are_stale(self) -> bool:
        age = self._accel_caps_age_seconds()
        return age is None or age > self._accel_caps_ttl_seconds

    async def refresh_accel_caps_off_request_path(self) -> None:
        """Re-detect capabilities in a worker thread, never on the event loop.

        Detection spawns child processes, so it is moved off the loop entirely
        rather than merely made less frequent (#313).
        """
        if not self.accel_caps_are_stale():
            return
        await asyncio.to_thread(self._refresh_accel_caps, force=True)

    def _build_bird_model_for_backend(
        self,
        spec: dict[str, Any],
        *,
        backend: str,
        provider: str,
    ) -> ModelType | None:
        if not _provider_supported_for_spec(spec, provider):
            return None

        model_path = str(spec.get("model_path") or "")
        labels_path = str(spec.get("labels_path") or "")
        input_size = int(spec.get("input_size") or 384)
        preprocessing = spec.get("preprocessing")
        label_grouping = spec.get("label_grouping")

        if backend == "openvino":
            device_name = {"intel_gpu": "GPU", "intel_npu": "NPU"}.get(provider, "CPU")
            model = OpenVINOModelInstance(
                "bird",
                model_path,
                labels_path,
                preprocessing=preprocessing,
                label_grouping=label_grouping,
                input_size=input_size,
                device_name=device_name,
                startup_self_test_enabled=not self._worker_process_mode,
            )
            return model if model.load() else None

        if backend == "onnxruntime":
            ort_providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"] if provider == "cuda" else ["CPUExecutionProvider"]
            )
            model = ONNXModelInstance(
                "bird",
                model_path,
                labels_path,
                preprocessing=preprocessing,
                label_grouping=label_grouping,
                input_size=input_size,
                ort_providers=ort_providers,
            )
            return model if model.load() else None

        if backend == "tflite":
            tflite_model_path, tflite_labels_path = self._get_model_paths(
                settings.classification.model,
                "labels.txt",
            )
            model = ModelInstance(
                "bird",
                tflite_model_path,
                tflite_labels_path,
                preprocessing=preprocessing,
                label_grouping=label_grouping,
            )
            return model if model.load() else None

        return None

    def _runtime_benchmark_key(self, *, backend: str, provider: str) -> str:
        return f"{str(backend or 'unknown').strip().lower()}/{str(provider or 'unknown').strip().lower()}"

    def _record_runtime_benchmark(self, benchmark: dict[str, Any]) -> dict[str, Any]:
        payload = dict(benchmark or {})
        key = str(payload.get("key") or "").strip()
        if not key:
            key = self._runtime_benchmark_key(
                backend=str(payload.get("backend") or "openvino"),
                provider=str(payload.get("provider") or "unknown"),
            )
            payload["key"] = key
        self._runtime_benchmarks[key] = payload
        if payload.get("status") == "passed":
            baseline_latency = payload.get("candidate_latency_seconds")
            if isinstance(baseline_latency, (int, float)) and baseline_latency > 0:
                self._inference_health.set_baseline(
                    RuntimeKey.from_values(
                        str(payload.get("backend") or "unknown"),
                        str(payload.get("provider") or "unknown"),
                        self._resolve_active_model_id(),
                    ),
                    p95_latency_seconds=float(baseline_latency),
                )
        return payload

    def _benchmark_model_probe(self, model: Any, image: Image.Image) -> tuple[float, dict[str, Any]]:
        started = time.perf_counter()
        report = model.probe(image)
        elapsed = max(0.0, time.perf_counter() - started)
        return elapsed, dict(report or {})

    def _runtime_benchmark_baseline(
        self,
        *,
        backend: str,
        provider: str,
    ) -> tuple[str, str] | None:
        normalized_backend = str(backend or "").strip().lower()
        normalized_provider = str(provider or "").strip().lower()
        if normalized_backend == "openvino" and normalized_provider in ("intel_gpu", "intel_npu"):
            return ("openvino", "intel_cpu")
        if normalized_backend == "onnxruntime" and normalized_provider == "cuda":
            return ("onnxruntime", "cpu")
        return None

    def _runtime_benchmark_refusal_reason(self, *, backend: str, provider: str, benchmark: dict[str, Any]) -> str:
        normalized_backend = str(backend or "").strip().lower()
        normalized_provider = str(provider or "").strip().lower()
        if normalized_backend == "openvino" and normalized_provider == "intel_gpu":
            label = "OpenVINO GPU"
        elif normalized_backend == "openvino" and normalized_provider == "intel_npu":
            label = "OpenVINO NPU"
        elif normalized_backend == "onnxruntime" and normalized_provider == "cuda":
            label = "ONNX Runtime CUDA"
        else:
            label = f"{backend}/{provider}".strip("/")

        reason = f"runtime benchmark refused {label}"
        ratio = benchmark.get("ratio")
        max_ratio = benchmark.get("max_ratio")
        if isinstance(ratio, (int, float)) and isinstance(max_ratio, (int, float)):
            reason = f"{reason}: latency ratio {ratio:.2f} exceeded {max_ratio:.2f}"
        return reason

    def _build_runtime_benchmark_model(
        self,
        spec: dict[str, Any],
        *,
        backend: str,
        provider: str,
    ) -> ModelType | None:
        if backend == "openvino":
            device_name = {"intel_gpu": "GPU", "intel_npu": "NPU"}.get(provider, "CPU")
            model = OpenVINOModelInstance(
                "bird",
                str(spec.get("model_path") or ""),
                str(spec.get("labels_path") or ""),
                preprocessing=spec.get("preprocessing"),
                label_grouping=spec.get("label_grouping"),
                input_size=int(spec.get("input_size") or 384),
                device_name=device_name,
                startup_self_test_enabled=False,
            )
            return model if model.load() else model

        if backend == "onnxruntime":
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"] if provider == "cuda" else ["CPUExecutionProvider"]
            )
            model = ONNXModelInstance(
                "bird",
                str(spec.get("model_path") or ""),
                str(spec.get("labels_path") or ""),
                preprocessing=spec.get("preprocessing"),
                label_grouping=spec.get("label_grouping"),
                input_size=int(spec.get("input_size") or 384),
                ort_providers=providers,
            )
            return model if model.load() else model

        return None

    def _build_runtime_benchmark_image(self, model: Any, spec: dict[str, Any]) -> Image.Image:
        builder = getattr(model, "_build_startup_self_test_image", None)
        if callable(builder):
            return builder()
        size = max(8, int(spec.get("input_size") or getattr(model, "input_size", 384) or 384))
        x = np.linspace(0, 255, size, dtype=np.uint8)
        y = np.linspace(255, 0, size, dtype=np.uint8)
        red = np.tile(x, (size, 1))
        green = np.tile(y[:, None], (1, size))
        blue = np.full((size, size), 127, dtype=np.uint8)
        return Image.fromarray(np.stack((red, green, blue), axis=2), mode="RGB")

    def _benchmark_runtime_candidate_against_cpu(
        self,
        spec: dict[str, Any],
        candidate_model: Any,
        *,
        backend: str,
        provider: str,
    ) -> dict[str, Any]:
        backend = str(backend or "").strip().lower()
        provider = str(provider or "").strip().lower()
        key = self._runtime_benchmark_key(backend=backend, provider=provider)
        baseline = self._runtime_benchmark_baseline(backend=backend, provider=provider)
        benchmark: dict[str, Any] = {
            "key": key,
            "backend": backend,
            "provider": provider,
            "status": "skipped",
            "should_mount": True,
            "enabled": _runtime_benchmark_enabled(),
            "max_ratio": CLASSIFIER_RUNTIME_BENCHMARK_MAX_GPU_CPU_RATIO,
        }
        if not benchmark["enabled"]:
            benchmark["reason"] = "disabled"
            return self._record_runtime_benchmark(benchmark)
        if self._worker_process_mode:
            benchmark["reason"] = "worker_process_mode"
            return self._record_runtime_benchmark(benchmark)
        if baseline is None:
            benchmark["reason"] = "no_comparable_cpu_baseline"
            return self._record_runtime_benchmark(benchmark)

        baseline_backend, baseline_provider = baseline
        benchmark["baseline_backend"] = baseline_backend
        benchmark["baseline_provider"] = baseline_provider

        cpu_model: Any | None = None
        try:
            image = self._build_runtime_benchmark_image(candidate_model, spec)
            cpu_model = self._build_runtime_benchmark_model(
                spec,
                backend=baseline_backend,
                provider=baseline_provider,
            )
            if cpu_model is None or not getattr(cpu_model, "loaded", False):
                benchmark["reason"] = "cpu_baseline_load_failed"
                benchmark["cpu_compile_error"] = getattr(cpu_model, "error", None)
                return self._record_runtime_benchmark(benchmark)

            gpu_latency, gpu_report = self._benchmark_model_probe(candidate_model, image)
            cpu_latency, cpu_report = self._benchmark_model_probe(cpu_model, image)
            benchmark.update(
                {
                    "candidate_latency_seconds": gpu_latency,
                    "baseline_latency_seconds": cpu_latency,
                    "gpu_latency_seconds": gpu_latency,
                    "cpu_latency_seconds": cpu_latency,
                    "candidate_status": gpu_report.get("status"),
                    "baseline_status": cpu_report.get("status"),
                    "gpu_status": gpu_report.get("status"),
                    "cpu_status": cpu_report.get("status"),
                    "candidate_probe": gpu_report,
                    "baseline_probe": cpu_report,
                    "gpu_probe": gpu_report,
                    "cpu_probe": cpu_report,
                }
            )
            if gpu_report.get("status") != "ok":
                benchmark.update(
                    {
                        "status": "failed",
                        "should_mount": False,
                        "reason": "candidate_probe_failed",
                    }
                )
                return self._record_runtime_benchmark(benchmark)
            if cpu_report.get("status") != "ok" or cpu_latency <= 0:
                benchmark.update(
                    {
                        "status": "skipped",
                        "should_mount": True,
                        "reason": "cpu_baseline_probe_unavailable",
                    }
                )
                return self._record_runtime_benchmark(benchmark)

            ratio = gpu_latency / cpu_latency
            benchmark["ratio"] = ratio
            if ratio > CLASSIFIER_RUNTIME_BENCHMARK_MAX_GPU_CPU_RATIO:
                benchmark.update(
                    {
                        "status": "failed",
                        "should_mount": False,
                        "reason": "accelerated_latency_ratio_exceeded",
                    }
                )
            else:
                benchmark.update(
                    {
                        "status": "passed",
                        "should_mount": True,
                    }
                )
            return self._record_runtime_benchmark(benchmark)
        except Exception as exc:
            benchmark.update(
                {
                    "status": "error",
                    "should_mount": True,
                    "reason": "benchmark_error",
                    "error": _summarize_runtime_exception(exc, max_len=600),
                }
            )
            return self._record_runtime_benchmark(benchmark)
        finally:
            if cpu_model is not None:
                try:
                    cpu_model.cleanup()
                except Exception:
                    pass

    def _runtime_fallback_targets(self) -> list[tuple[str, str]]:
        try:
            provider_order = list(self._resolve_active_bird_model_spec().get("host_provider_preference_order") or [])
        except Exception:
            provider_order = []
        return _runtime_fallback_targets_for(
            active_backend=self._inference_backend,
            active_provider=self._active_inference_provider,
            caps=self._accel_caps,
            provider_order=provider_order,
        )

    def _load_runtime_fallback_bird_model(
        self,
        *,
        failed_backend: str,
        failed_provider: str,
        failure_detail: str,
    ) -> tuple[ModelType | None, str | None, str | None, str | None]:
        spec = self._resolve_active_bird_model_spec()
        for backend, provider in self._runtime_fallback_targets():
            replacement = self._build_bird_model_for_backend(spec, backend=backend, provider=provider)
            if replacement is None:
                continue
            reason = (
                f"Runtime fallback after {failed_backend}/{failed_provider} failure: "
                f"{failure_detail}; using {backend}/{provider}"
            )
            return replacement, backend, provider, reason
        return None, None, None, None

    def _gpu_restore_eligible(self) -> bool:
        last_recovery = self._inference_health.most_recent_recovery()
        restoring_after_live_lease_fallback = (
            isinstance(last_recovery, dict)
            and last_recovery.get("reason")
            in {
                LIVE_GPU_LEASE_EXPIRY_FALLBACK_REASON,
                GPU_UNHEALTHY_FALLBACK_REASON,
            }
            and not (self._inference_backend == "openvino" and self._active_inference_provider == "intel_gpu")
        )
        restoring_after_cpu_fallback = (
            self._inference_backend == "openvino" and self._active_inference_provider == "intel_cpu"
        )
        if not restoring_after_live_lease_fallback and not restoring_after_cpu_fallback:
            return False
        if time.monotonic() < self._gpu_restore_not_before_monotonic:
            return False
        spec = self._resolve_active_bird_model_spec()
        if not _provider_supported_for_spec(spec, "intel_gpu"):
            return False
        requested_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        if requested_provider not in {"auto", "intel_gpu"}:
            return False
        if not self._accel_caps.get("openvino_available"):
            return False
        if not self._accel_caps.get("intel_gpu_available"):
            return False
        return True

    def _record_gpu_success(self) -> None:
        self._gpu_invalid_retry_remaining = CLASSIFIER_GPU_INVALID_RETRY_LIMIT

    def _live_gpu_fallback_health_key(self) -> RuntimeKey | None:
        if self._inference_backend == "openvino" and self._active_inference_provider == "intel_gpu":
            return None
        last_recovery = self._inference_health.most_recent_recovery()
        if not isinstance(last_recovery, dict):
            return None
        failed_backend = str(last_recovery.get("failed_backend") or "").strip().lower()
        failed_provider = str(last_recovery.get("failed_provider") or "").strip().lower()
        if failed_backend != "openvino" or failed_provider not in {"gpu", "intel_gpu"}:
            return None
        failed_runtime = last_recovery.get("failed_runtime")
        failed_model_id = None
        if isinstance(failed_runtime, dict):
            failed_model_id = str(failed_runtime.get("model_id") or "").strip() or None
        return RuntimeKey.from_values("openvino", "intel_gpu", failed_model_id or self._resolve_active_model_id())

    def _live_gpu_lease_fallback_cooldown_remaining(self) -> float:
        runtime_key = self._live_gpu_fallback_health_key()
        if runtime_key is None:
            return 0.0
        return self._inference_health.cooldown_remaining(runtime_key)

    def _live_gpu_lease_fallback_active(self) -> bool:
        return self._live_gpu_lease_fallback_cooldown_remaining() > 0

    def _record_live_lease_expiry_and_maybe_fallback(
        self,
        error: ClassificationLeaseExpiredError,
        *,
        runtime_key: RuntimeKey | None = None,
    ) -> None:
        if error.priority != "live":
            return
        self.register_gpu_unhealthy_signal("live_lease_expiry", runtime_key=runtime_key)

    def _active_inference_runtime_key(self) -> RuntimeKey:
        return RuntimeKey.from_values(
            self._inference_backend,
            self._active_inference_provider,
            self._resolve_active_model_id(),
        )

    def _gpu_unhealthy_signal_outcome(self, source: str) -> Outcome:
        normalized_source = str(source or "")
        if "lease_expir" in normalized_source:
            return "lease_expired"
        if "timeout" in normalized_source:
            return "timeout"
        return "exception"

    def _publish_runtime_recovery(self, recovery: dict[str, Any]) -> None:
        """Record a recovery/fallback payload in InferenceHealth.

        Routes the payload to the runtime described by ``failed_runtime`` (or
        the ``failed_backend``/``failed_provider`` pair, or the currently
        active runtime when neither is present). Consumers read recovery
        context from ``InferenceHealth.last_recovery`` / ``most_recent_recovery``.
        """
        if not isinstance(recovery, dict):
            return
        failed_runtime = recovery.get("failed_runtime")
        if isinstance(failed_runtime, dict):
            key = RuntimeKey.from_values(
                failed_runtime.get("backend"),
                failed_runtime.get("provider"),
                failed_runtime.get("model_id"),
            )
        else:
            failed_backend = recovery.get("failed_backend")
            failed_provider = recovery.get("failed_provider")
            try:
                active_key = self._active_inference_runtime_key()
            except Exception:
                active_key = RuntimeKey.from_values(None, None, None)
            key = RuntimeKey.from_values(
                failed_backend if failed_backend else active_key.backend,
                failed_provider if failed_provider else active_key.provider,
                active_key.model_id,
            )
        self._inference_health.record_recovery(key, recovery)

    def latest_runtime_recovery(self) -> dict[str, Any] | None:
        """Return the newest runtime recovery for worker telemetry.

        Runtime recovery state moved into ``InferenceHealth`` when health was
        made provider/model scoped.  Keep the worker protocol behind this
        method so child processes do not reach for a removed implementation
        attribute and turn an otherwise successful inference into a worker
        error while serialising its telemetry.
        """
        recovery = self._inference_health.most_recent_recovery()
        return dict(recovery) if isinstance(recovery, dict) else None

    def register_gpu_unhealthy_signal(
        self,
        source: str,
        *,
        event_id: str | None = None,
        runtime_key: RuntimeKey | None = None,
    ) -> None:
        """Record a signal that OpenVINO Intel GPU inference is unhealthy.

        Triggers the same model hot-swap as repeated live lease expiries when
        InferenceHealth marks the active GPU runtime unhealthy. Signals are
        merged across sources so maintenance video timeouts and snapshot
        fallback lease expiries count alongside live lease expiries — which
        matters at night or during batch analyze runs when there is no live
        traffic to surface the problem on its own.
        """
        runtime_key = runtime_key or self._active_inference_runtime_key()
        if (
            source != "live_lease_expiry"
            and self._inference_backend == "openvino"
            and self._active_inference_provider == "intel_gpu"
        ):
            self._inference_health.record(
                runtime_key,
                outcome=self._gpu_unhealthy_signal_outcome(source),
                latency_seconds=None,
            )

        if self._image_execution_mode != "in_process":
            return
        if self._inference_backend != "openvino" or self._active_inference_provider != "intel_gpu":
            return
        if self._inference_health.verdict(runtime_key) != "unhealthy":
            return
        if self._live_gpu_lease_fallback_active():
            return

        detail = (
            f"OpenVINO Intel GPU inference signalled unhealthy ({source}) repeatedly; "
            "using a safer CPU fallback during cooldown"
        )
        with self._models_lock:
            replacement, backend, provider, reason = self._load_runtime_fallback_bird_model(
                failed_backend="openvino",
                failed_provider="intel_gpu",
                failure_detail=detail,
            )
            if replacement is None or backend is None or provider is None or reason is None:
                recovery = {
                    "status": "failed",
                    "failed_backend": "openvino",
                    "failed_provider": "intel_gpu",
                    "failed_runtime": {
                        "backend": runtime_key.backend,
                        "provider": runtime_key.provider,
                        "model_id": runtime_key.model_id,
                        "key": runtime_key.display(),
                    },
                    "detail": detail,
                    "reason": (
                        LIVE_GPU_LEASE_EXPIRY_FALLBACK_UNAVAILABLE_REASON
                        if source == "live_lease_expiry"
                        else GPU_UNHEALTHY_FALLBACK_UNAVAILABLE_REASON
                    ),
                    "trigger_source": source,
                    "at": time.time(),
                }
                self._publish_runtime_recovery(recovery)
                return

            old_model = self._models.get("bird")
            self._models["bird"] = replacement
            self._inference_backend = backend
            self._active_inference_provider = provider
            now = time.monotonic()
            self._gpu_restore_not_before_monotonic = now + CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS
            self._append_inference_fallback_reason(reason)
            self._runtime_fallback_recoveries += 1
            recovery = {
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "intel_gpu",
                "failed_runtime": {
                    "backend": runtime_key.backend,
                    "provider": runtime_key.provider,
                    "model_id": runtime_key.model_id,
                    "key": runtime_key.display(),
                },
                "recovered_backend": backend,
                "recovered_provider": provider,
                "detail": detail,
                "reason": (
                    LIVE_GPU_LEASE_EXPIRY_FALLBACK_REASON
                    if source == "live_lease_expiry"
                    else GPU_UNHEALTHY_FALLBACK_REASON
                ),
                "trigger_source": source,
                "at": time.time(),
                "cooldown_seconds": CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS,
            }
            self._publish_runtime_recovery(recovery)
            log.warning(
                "OpenVINO Intel GPU fallback engaged after repeated unhealthy signals",
                trigger_source=source,
                event_id=event_id,
                recovered_backend=backend,
                recovered_provider=provider,
                cooldown_seconds=CLASSIFIER_LIVE_GPU_LEASE_FALLBACK_COOLDOWN_SECONDS,
            )
            if old_model is not None and old_model is not replacement and hasattr(old_model, "cleanup"):
                try:
                    old_model.cleanup()
                except Exception:
                    pass

    def _maybe_restore_gpu_provider(self) -> None:
        with self._models_lock:
            if not self._gpu_restore_eligible():
                return
            current = self._models.get("bird")
            if current is None:
                return
            self._runtime_gpu_restore_attempts += 1
            spec = self._resolve_active_bird_model_spec()
            replacement = self._build_bird_model_for_backend(
                spec,
                backend="openvino",
                provider="intel_gpu",
            )
            if replacement is None:
                self._runtime_gpu_restore_failures += 1
                self._gpu_restore_not_before_monotonic = time.monotonic() + CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS
                return
            self._models["bird"] = replacement
            self._inference_backend = "openvino"
            self._active_inference_provider = "intel_gpu"
            self._record_gpu_success()
            self._runtime_gpu_restore_successes += 1
            if hasattr(current, "cleanup"):
                try:
                    current.cleanup()
                except Exception:
                    pass
            self._publish_runtime_recovery(
                {
                    "status": "recovered",
                    "failed_backend": "openvino",
                    "failed_provider": "intel_cpu",
                    "recovered_backend": "openvino",
                    "recovered_provider": "intel_gpu",
                    "detail": "Auto-restored OpenVINO GPU provider after cooldown",
                    "at": time.time(),
                }
            )

    def _attempt_gpu_retry_after_invalid_output(
        self,
        failed_model: ModelType,
        error: InvalidInferenceOutputError,
    ) -> bool:
        if (
            self._inference_backend != "openvino"
            or self._active_inference_provider != "intel_gpu"
            or error.backend != "openvino"
            or error.provider.lower() not in {"gpu", "intel_gpu"}
            or self._gpu_invalid_retry_remaining <= 0
        ):
            return False

        spec = self._resolve_active_bird_model_spec()
        replacement = self._build_bird_model_for_backend(
            spec,
            backend="openvino",
            provider="intel_gpu",
        )
        if replacement is None:
            return False

        self._gpu_invalid_retry_remaining -= 1
        self._runtime_gpu_retries += 1
        self._models["bird"] = replacement
        recovery: dict[str, Any] = {
            "status": "recovered",
            "failed_backend": error.backend,
            "failed_provider": error.provider,
            "recovered_backend": "openvino",
            "recovered_provider": "intel_gpu",
            "detail": f"{error.detail}; reloaded GPU model and retrying once",
            "at": time.time(),
        }
        if error.diagnostics:
            recovery["diagnostics"] = dict(error.diagnostics)
        self._publish_runtime_recovery(recovery)
        if hasattr(failed_model, "cleanup"):
            try:
                failed_model.cleanup()
            except Exception:
                pass
        return True

    def _recover_from_invalid_bird_output(
        self,
        failed_model: ModelType,
        error: InvalidInferenceOutputError,
    ) -> bool:
        with self._models_lock:
            current = self._models.get("bird")
            if current is None:
                return False
            if current is not failed_model:
                return True

            self._runtime_invalid_output_failures += 1
            if self._attempt_gpu_retry_after_invalid_output(failed_model, error):
                return True
            replacement, backend, provider, reason = self._load_runtime_fallback_bird_model(
                failed_backend=error.backend,
                failed_provider=error.provider,
                failure_detail=error.detail,
            )
            if replacement is None or backend is None or provider is None or reason is None:
                recovery: dict[str, Any] = {
                    "status": "failed",
                    "failed_backend": error.backend,
                    "failed_provider": error.provider,
                    "detail": error.detail,
                    "at": time.time(),
                }
                if error.diagnostics:
                    recovery["diagnostics"] = dict(error.diagnostics)
                self._publish_runtime_recovery(recovery)
                log.error(
                    "Classifier produced invalid runtime output and no fallback succeeded",
                    failed_backend=error.backend,
                    failed_provider=error.provider,
                    detail=error.detail,
                )
                return False

            old_model = self._models["bird"]
            self._models["bird"] = replacement
            self._inference_backend = backend
            self._active_inference_provider = provider
            if backend == "openvino" and provider == "intel_cpu" and error.backend == "openvino":
                self._gpu_restore_not_before_monotonic = time.monotonic() + CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS
            self._append_inference_fallback_reason(reason)
            self._runtime_fallback_recoveries += 1
            recovery: dict[str, Any] = {
                "status": "recovered",
                "failed_backend": error.backend,
                "failed_provider": error.provider,
                "recovered_backend": backend,
                "recovered_provider": provider,
                "detail": error.detail,
                "at": time.time(),
            }
            if error.diagnostics:
                recovery["diagnostics"] = dict(error.diagnostics)
            self._publish_runtime_recovery(recovery)
            if hasattr(old_model, "cleanup"):
                try:
                    old_model.cleanup()
                except Exception as cleanup_error:
                    log.warning(
                        "Failed to cleanup previous classifier model after runtime fallback",
                        failed_backend=error.backend,
                        failed_provider=error.provider,
                        cleanup_error=str(cleanup_error),
                    )
            log.warning(
                "Classifier produced invalid runtime output; switched inference backend",
                failed_backend=error.backend,
                failed_provider=error.provider,
                recovered_backend=backend,
                recovered_provider=provider,
                detail=error.detail,
            )
            return True

    def _init_bird_model(self):
        """Initialize the bird classification model (loaded at startup)."""
        spec = self._resolve_active_bird_model_spec()
        model_path = str(spec["model_path"])
        labels_path = str(spec["labels_path"])
        # Lets the loaders take labels from the catalogue, which compiled them
        # from a label file proven at install time, rather than from whatever is
        # on disk now. Absent or unrecognised, they read the file as before.
        model_sha256 = spec.get("model_sha256")
        input_size = int(spec["input_size"])
        preprocessing = spec.get("preprocessing")
        runtime = str(spec["runtime"])
        supported_inference_providers = list(spec.get("supported_inference_providers") or [])
        host_provider_preference_order = list(spec.get("host_provider_preference_order") or [])
        host_added = list(spec.get("host_added_inference_providers") or [])
        if host_added:
            log.info(
                "Merged host-validated inference providers",
                model_id=self._resolve_active_model_id(),
                added=host_added,
            )
        model_config_warnings = [
            str(item).strip() for item in (spec.get("model_config_warnings") or []) if str(item).strip()
        ]

        log.info(
            "Initializing bird model",
            path=model_path,
            input_size=input_size,
            runtime=runtime,
            preprocessing=preprocessing,
        )

        self._selected_inference_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        self._refresh_accel_caps(force=True)
        self._inference_fallback_reason = None
        self._inference_backend = "tflite"
        self._active_inference_provider = "tflite"
        self._model_config_warnings = model_config_warnings
        self._bird_model_artifact_metadata = _extract_model_artifact_metadata(model_path)
        self._bird_model_compatibility = {
            "artifact_trust_state": "unknown",
            "last_probe_device": None,
            "last_probe_status": None,
        }
        self._openvino_model_compile_ok = None
        self._openvino_model_compile_device = None
        self._openvino_model_compile_error = None
        self._openvino_model_compile_unsupported_ops = []
        self._runtime_benchmarks = {}

        if not self._accel_caps.get("openvino_available"):
            if self._accel_caps.get("openvino_import_error"):
                log.warning(
                    "OpenVINO unavailable (import)",
                    error=self._accel_caps.get("openvino_import_error"),
                    version=self._accel_caps.get("openvino_version"),
                )
            elif self._accel_caps.get("openvino_probe_error"):
                log.warning(
                    "OpenVINO unavailable (probe)",
                    error=self._accel_caps.get("openvino_probe_error"),
                    dev_dri_present=self._accel_caps.get("dev_dri_present"),
                    dev_dri_entries=self._accel_caps.get("dev_dri_entries"),
                    process_groups=self._accel_caps.get("process_groups"),
                )
            elif self._accel_caps.get("openvino_gpu_probe_error"):
                log.warning(
                    "OpenVINO GPU plugin unavailable",
                    error=self._accel_caps.get("openvino_gpu_probe_error"),
                    dev_dri_present=self._accel_caps.get("dev_dri_present"),
                    dev_dri_entries=self._accel_caps.get("dev_dri_entries"),
                    process_groups=self._accel_caps.get("process_groups"),
                )

        if self._accel_caps.get("cuda_probe_error"):
            log.warning(
                "CUDA unavailable (probe)",
                error=self._accel_caps.get("cuda_probe_error"),
                provider_installed=self._accel_caps.get("cuda_provider_installed"),
                hardware_available=self._accel_caps.get("cuda_hardware_available"),
            )

        # Create appropriate model instance based on runtime
        if runtime == "onnx":
            selection = _resolve_inference_selection(
                self._selected_inference_provider,
                self._accel_caps,
                supported_providers=supported_inference_providers,
                preferred_providers=host_provider_preference_order,
            )
            self._inference_fallback_reason = selection.get("fallback_reason")
            self._active_inference_provider = selection.get("active_provider", "unavailable")
            self._inference_backend = selection.get("backend", "unavailable")

            if selection["backend"] == "openvino":
                openvino_device = selection["openvino_device"] or "CPU"
                self._openvino_model_compile_device = openvino_device
                bird_model = OpenVINOModelInstance(
                    "bird",
                    model_path,
                    labels_path,
                    preprocessing=preprocessing,
                    input_size=input_size,
                    device_name=openvino_device,
                    startup_self_test_enabled=not self._worker_process_mode,
                    model_sha256=model_sha256,
                )
                if bird_model.load():
                    if (
                        openvino_device == "GPU" or str(openvino_device).startswith("GPU.")
                    ) and self._active_inference_provider == "intel_gpu":
                        benchmark = self._benchmark_runtime_candidate_against_cpu(
                            spec,
                            bird_model,
                            backend="openvino",
                            provider="intel_gpu",
                        )
                        benchmark = self._record_runtime_benchmark(benchmark)
                        if not bool(benchmark.get("should_mount", True)):
                            reason = self._runtime_benchmark_refusal_reason(
                                backend="openvino",
                                provider="intel_gpu",
                                benchmark=benchmark,
                            )
                            self._openvino_model_compile_ok = False
                            self._openvino_model_compile_error = reason
                            self._openvino_model_compile_unsupported_ops = []
                            try:
                                bird_model.cleanup()
                            except Exception:
                                pass
                            if self._accel_caps.get("ort_available"):
                                log.warning(
                                    "OpenVINO GPU runtime benchmark failed; retrying with ONNX Runtime CPU fallback",
                                    requested=self._selected_inference_provider,
                                    device=selection.get("openvino_device"),
                                    benchmark=benchmark,
                                )
                                self._inference_backend = "onnxruntime"
                                self._active_inference_provider = "cpu"
                                prev_reason = self._inference_fallback_reason
                                self._inference_fallback_reason = f"{prev_reason}; {reason}" if prev_reason else reason
                                fallback_model = ONNXModelInstance(
                                    "bird",
                                    model_path,
                                    labels_path,
                                    preprocessing=preprocessing,
                                    input_size=input_size,
                                    ort_providers=["CPUExecutionProvider"],
                                )
                                if fallback_model.load():
                                    self._models["bird"] = fallback_model
                                    return
                                log.warning(
                                    "ONNX Runtime CPU fallback model load failed after GPU runtime benchmark; falling back to TFLite",
                                    error=fallback_model.error,
                                )
                                runtime = "tflite"
                            else:
                                prev_reason = self._inference_fallback_reason
                                self._inference_fallback_reason = f"{prev_reason}; {reason}" if prev_reason else reason
                                log.warning(
                                    "OpenVINO GPU runtime benchmark failed and no ORT fallback available; falling back to TFLite",
                                    benchmark=benchmark,
                                )
                                runtime = "tflite"
                            tflite_model = self._build_bird_model_for_backend(spec, backend="tflite", provider="tflite")
                            if tflite_model is None:
                                tflite_model = ModelInstance(
                                    "bird", model_path, labels_path, preprocessing=preprocessing
                                )
                                tflite_model.load()
                            self._models["bird"] = tflite_model
                            self._inference_backend = "tflite"
                            self._active_inference_provider = "tflite"
                            return
                    self._openvino_model_compile_ok = True
                    self._openvino_model_compile_error = None
                    self._openvino_model_compile_unsupported_ops = []
                    session_providers = []
                    if getattr(bird_model, "session", None):
                        try:
                            session_providers = list(bird_model.session.get_providers() or [])
                        except Exception:
                            session_providers = []
                    reconciled_provider, session_fallback_reason = _reconcile_ort_active_provider(
                        self._active_inference_provider,
                        session_providers,
                    )
                    if session_fallback_reason:
                        prev_reason = self._inference_fallback_reason
                        self._active_inference_provider = reconciled_provider
                        self._inference_fallback_reason = (
                            f"{prev_reason}; {session_fallback_reason}" if prev_reason else session_fallback_reason
                        )
                        log.warning(
                            "ONNX Runtime session provider mismatch; applying runtime fallback status",
                            requested=self._selected_inference_provider,
                            planned_active=selection.get("active_provider"),
                            actual_active=self._active_inference_provider,
                            session_providers=session_providers,
                            reason=session_fallback_reason,
                        )
                    self._models["bird"] = bird_model
                    if self._inference_fallback_reason:
                        log.warning(
                            "Inference provider fallback applied",
                            requested=self._selected_inference_provider,
                            active=self._active_inference_provider,
                            backend=self._inference_backend,
                            reason=self._inference_fallback_reason,
                        )
                    return
                self._openvino_model_compile_ok = False
                self._openvino_model_compile_error = bird_model.error or "OpenVINO model load failed"
                self._openvino_model_compile_unsupported_ops = _extract_openvino_unsupported_ops(
                    self._openvino_model_compile_error
                )
                # Device/plugin can still fail even if detection said "available" (e.g. /dev/dri permissions)
                if self._accel_caps.get("ort_available"):
                    log.warning(
                        "OpenVINO model load failed; retrying with ONNX Runtime CPU fallback",
                        requested=self._selected_inference_provider,
                        device=selection.get("openvino_device"),
                        error=bird_model.error,
                    )
                    self._inference_backend = "onnxruntime"
                    self._active_inference_provider = "cpu"
                    prev_reason = self._inference_fallback_reason
                    fallback_reason = _summarize_openvino_load_error(
                        self._openvino_model_compile_error,
                        self._openvino_model_compile_device,
                        fallback_target="ONNX Runtime CPU",
                    )
                    self._inference_fallback_reason = (
                        f"{prev_reason}; {fallback_reason}" if prev_reason else fallback_reason
                    )
                    fallback_model = ONNXModelInstance(
                        "bird",
                        model_path,
                        labels_path,
                        preprocessing=preprocessing,
                        input_size=input_size,
                        ort_providers=["CPUExecutionProvider"],
                    )
                    if fallback_model.load():
                        self._models["bird"] = fallback_model
                        return
                    log.warning(
                        "ONNX Runtime CPU fallback model load failed; falling back to TFLite",
                        error=fallback_model.error,
                    )
                    runtime = "tflite"
                prev_reason = self._inference_fallback_reason
                fallback_reason = _summarize_openvino_load_error(
                    self._openvino_model_compile_error,
                    self._openvino_model_compile_device,
                    fallback_target="TFLite",
                )
                self._inference_fallback_reason = (
                    f"{prev_reason}; {fallback_reason}" if prev_reason else fallback_reason
                )
                log.warning(
                    "OpenVINO model load failed and no ORT fallback available; falling back to TFLite",
                    error=bird_model.error,
                )
                runtime = "tflite"

            if selection["backend"] == "onnxruntime":
                bird_model = ONNXModelInstance(
                    "bird",
                    model_path,
                    labels_path,
                    preprocessing=preprocessing,
                    input_size=input_size,
                    ort_providers=selection.get("ort_providers") or ["CPUExecutionProvider"],
                )
                if bird_model.load():
                    session_providers = []
                    if getattr(bird_model, "session", None):
                        try:
                            session_providers = list(bird_model.session.get_providers() or [])
                        except Exception:
                            session_providers = []
                    reconciled_provider, session_fallback_reason = _reconcile_ort_active_provider(
                        self._active_inference_provider,
                        session_providers,
                    )
                    if session_fallback_reason:
                        prev_reason = self._inference_fallback_reason
                        self._active_inference_provider = reconciled_provider
                        self._inference_fallback_reason = (
                            f"{prev_reason}; {session_fallback_reason}" if prev_reason else session_fallback_reason
                        )
                        log.warning(
                            "ONNX Runtime session provider mismatch; applying runtime fallback status",
                            requested=self._selected_inference_provider,
                            planned_active=selection.get("active_provider"),
                            actual_active=self._active_inference_provider,
                            session_providers=session_providers,
                            reason=session_fallback_reason,
                        )
                    if self._active_inference_provider == "cuda":
                        benchmark = self._benchmark_runtime_candidate_against_cpu(
                            spec,
                            bird_model,
                            backend="onnxruntime",
                            provider="cuda",
                        )
                        benchmark = self._record_runtime_benchmark(benchmark)
                        if not bool(benchmark.get("should_mount", True)):
                            reason = self._runtime_benchmark_refusal_reason(
                                backend="onnxruntime",
                                provider="cuda",
                                benchmark=benchmark,
                            )
                            try:
                                bird_model.cleanup()
                            except Exception:
                                pass
                            log.warning(
                                "ONNX Runtime CUDA benchmark failed; retrying with ONNX Runtime CPU fallback",
                                requested=self._selected_inference_provider,
                                benchmark=benchmark,
                            )
                            self._inference_backend = "onnxruntime"
                            self._active_inference_provider = "cpu"
                            prev_reason = self._inference_fallback_reason
                            self._inference_fallback_reason = f"{prev_reason}; {reason}" if prev_reason else reason
                            fallback_model = ONNXModelInstance(
                                "bird",
                                model_path,
                                labels_path,
                                preprocessing=preprocessing,
                                input_size=input_size,
                                ort_providers=["CPUExecutionProvider"],
                            )
                            if fallback_model.load():
                                self._models["bird"] = fallback_model
                                return
                            log.warning(
                                "ONNX Runtime CPU fallback model load failed after CUDA runtime benchmark; falling back to TFLite",
                                error=fallback_model.error,
                            )
                            runtime = "tflite"
                            tflite_model = self._build_bird_model_for_backend(spec, backend="tflite", provider="tflite")
                            if tflite_model is None:
                                tflite_model = ModelInstance(
                                    "bird", model_path, labels_path, preprocessing=preprocessing
                                )
                                tflite_model.load()
                            self._models["bird"] = tflite_model
                            self._inference_backend = "tflite"
                            self._active_inference_provider = "tflite"
                            return
                        else:
                            self._models["bird"] = bird_model
                            if self._inference_fallback_reason:
                                log.warning(
                                    "Inference provider fallback applied",
                                    requested=self._selected_inference_provider,
                                    active=self._active_inference_provider,
                                    backend=self._inference_backend,
                                    reason=self._inference_fallback_reason,
                                )
                            return
                    self._models["bird"] = bird_model
                    if self._inference_fallback_reason:
                        log.warning(
                            "Inference provider fallback applied",
                            requested=self._selected_inference_provider,
                            active=self._active_inference_provider,
                            backend=self._inference_backend,
                            reason=self._inference_fallback_reason,
                        )
                    return
                if self._accel_caps.get("openvino_available") and self._accel_caps.get("intel_cpu_available"):
                    log.warning(
                        "ONNX Runtime model load failed; retrying with OpenVINO CPU fallback", error=bird_model.error
                    )
                    self._inference_backend = "openvino"
                    self._active_inference_provider = "intel_cpu"
                    prev_reason = self._inference_fallback_reason
                    self._inference_fallback_reason = (
                        f"{prev_reason}; ONNX Runtime load failed"
                        if prev_reason
                        else "ONNX Runtime load failed; using OpenVINO CPU"
                    )
                    fallback_model = OpenVINOModelInstance(
                        "bird",
                        model_path,
                        labels_path,
                        preprocessing=preprocessing,
                        input_size=input_size,
                        device_name="CPU",
                        startup_self_test_enabled=not self._worker_process_mode,
                    )
                    if fallback_model.load():
                        self._models["bird"] = fallback_model
                        return
                    log.warning(
                        "OpenVINO CPU fallback model load failed; falling back to TFLite",
                        error=fallback_model.error,
                    )
                    runtime = "tflite"
                log.warning("ONNX Runtime model load failed; falling back to TFLite", error=bird_model.error)
                runtime = "tflite"

            log.error(
                "ONNX model requested but no ONNX-capable runtime is available; falling back to TFLite",
                requested_provider=self._selected_inference_provider,
                reason=self._inference_fallback_reason,
            )
            runtime = "tflite"

        # Default: TFLite model
        bird_model = self._build_bird_model_for_backend(spec, backend="tflite", provider="tflite")
        if bird_model is None:
            bird_model = ModelInstance("bird", model_path, labels_path, preprocessing=preprocessing)
            bird_model.load()
        self._models["bird"] = bird_model
        self._inference_backend = "tflite"
        self._active_inference_provider = "tflite"

    async def reload_bird_model(self):
        """Reload the bird model (e.g., after switching models)."""

        def replace_bird_model_locked() -> None:
            with self._models_lock:
                if "bird" in self._models:
                    # Cleanup old model resources before replacing
                    old_model = self._models.pop("bird")
                    if hasattr(old_model, "cleanup"):
                        old_model.cleanup()
                    del old_model

                # 1. Initialize locally ONLY if we are a worker or NOT in subprocess mode.
                # This prevents the main process from loading large models into RAM when it
                # should be using supervisor workers instead.
                if self._worker_process_mode or self._image_execution_mode != "subprocess":
                    self._init_bird_model()

        # Model init loads weights and re-detects hardware, which spawns child
        # processes. A reload is triggered from request handlers' background
        # tasks, which run on the event loop, so the work leaves it (#313).
        await asyncio.to_thread(replace_bird_model_locked)

        # 2. If we have a supervisor (main process in subprocess mode),
        # tell it to restart all workers to pick up the new model.
        if self._classifier_supervisor is not None:
            log.info("Requesting supervisor worker restart for model change")
            await self._classifier_supervisor.restart_pool()
        elif self._video_supervisor is not None:
            # In-process live/image inference still uses an isolated, lazily
            # started video worker so native video hangs remain killable.
            await self._video_supervisor.restart_pool("video")

        log.info("Reloaded bird model")

    def _get_wildlife_model(self) -> ModelInstance:
        """Get or lazily load the wildlife model."""
        if "wildlife" not in self._models:
            model_path, labels_path = self._get_model_paths(
                settings.classification.wildlife_model, settings.classification.wildlife_labels
            )
            self._models["wildlife"] = ModelInstance("wildlife", model_path, labels_path)

        model = self._models["wildlife"]
        if not model.loaded:
            model.load()

        return model

    def _recent_admission_outcome_counts(self, admission_metrics: dict) -> dict[str, int]:
        threshold = time.time() - CLASSIFIER_ADMISSION_RECOVERY_WINDOW_SECONDS
        counts = {
            "recent_live_abandoned": 0,
            "recent_live_late_ignored": 0,
        }
        for outcome in admission_metrics.get("recent_outcomes", []):
            if float(outcome.get("timestamp") or 0.0) < threshold:
                continue
            if outcome.get("priority") != "live":
                continue
            if outcome.get("outcome") == "abandoned":
                counts["recent_live_abandoned"] += 1
            elif outcome.get("outcome") in {"late_completion_ignored", "late_failure_ignored"}:
                counts["recent_live_late_ignored"] += 1
        return counts

    def _get_supervisor_metrics(self) -> dict | None:
        supervisor = self._classifier_supervisor or self._video_supervisor
        if supervisor is None:
            return None
        try:
            metrics = supervisor.get_metrics()
            return metrics if isinstance(metrics, dict) else None
        except Exception:
            return None

    def _latest_worker_runtime_recovery(self, supervisor_metrics: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(supervisor_metrics, dict):
            return None
        recoveries: list[dict[str, Any]] = []
        for pool_name in ("live", "background", "video"):
            pool = supervisor_metrics.get(pool_name)
            if not isinstance(pool, dict):
                continue
            recovery = pool.get("last_runtime_recovery")
            if isinstance(recovery, dict):
                recoveries.append(dict(recovery))
        if not recoveries:
            return None
        recoveries.sort(key=lambda item: float(item.get("at") or 0.0), reverse=True)
        latest = recoveries[0]
        self._publish_runtime_recovery(latest)
        return latest

    def _effective_subprocess_runtime_fields(
        self,
        runtime_recovery: dict[str, Any] | None,
    ) -> tuple[str, str]:
        backend = self._inference_backend
        provider = self._active_inference_provider
        if not isinstance(runtime_recovery, dict):
            return backend, provider

        recovered_backend = str(runtime_recovery.get("recovered_backend") or "").strip()
        recovered_provider = str(runtime_recovery.get("recovered_provider") or "").strip()
        if recovered_backend:
            backend = recovered_backend
        if recovered_provider:
            provider = recovered_provider
        return backend, provider

    def _describe_live_image_health(self, admission_metrics: dict) -> dict:
        live_metrics = admission_metrics["live"]
        recent_counts = self._recent_admission_outcome_counts(admission_metrics)
        in_flight = int(live_metrics["running"])
        queued = int(live_metrics["queued"])
        capacity = int(live_metrics["capacity"])
        oldest_age = live_metrics.get("oldest_running_age_seconds")
        recovery_active = recent_counts["recent_live_abandoned"] > 0 or recent_counts["recent_live_late_ignored"] > 0
        supervisor_metrics = self._get_supervisor_metrics() or {}
        live_worker_pool = supervisor_metrics.get("live") if isinstance(supervisor_metrics, dict) else {}
        worker_circuit_open = bool((live_worker_pool or {}).get("circuit_open"))
        live_gpu_fallback_active = self._live_gpu_lease_fallback_active()

        pressure_level = "normal"
        if queued > 0 or in_flight >= capacity:
            pressure_level = "high"
        if (
            queued > 0
            and in_flight >= capacity
            and isinstance(oldest_age, (int, float))
            and oldest_age >= (CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS * 0.8)
        ):
            pressure_level = "critical"
        if worker_circuit_open:
            pressure_level = "critical"

        status = "ok"
        if recovery_active or live_gpu_fallback_active or pressure_level == "critical" or worker_circuit_open:
            status = "degraded"

        return {
            "status": status,
            "pressure_level": pressure_level,
            "max_concurrent": capacity,
            "in_flight": in_flight,
            "queued": queued,
            "admission_timeout_seconds": CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS,
            "admission_timeouts": self._live_image_admission_timeouts,
            "abandoned": int(live_metrics["abandoned"]),
            "late_completions_ignored": int(admission_metrics["late_completions_ignored"]),
            "oldest_running_age_seconds": oldest_age,
            "recovery_active": recovery_active or worker_circuit_open or live_gpu_fallback_active,
            "recent_abandoned": recent_counts["recent_live_abandoned"],
            "recent_late_completions_ignored": recent_counts["recent_live_late_ignored"],
        }

    def _describe_background_image_health(self, admission_metrics: dict) -> dict:
        background_metrics = admission_metrics["background"]
        throttled = bool(admission_metrics["background_throttled"])
        queued = int(background_metrics["queued"])
        oldest_queued_age = background_metrics.get("oldest_queued_age_seconds")
        status = "degraded" if throttled and queued > 0 else "ok"
        return {
            "status": status,
            "in_flight": int(background_metrics["running"]),
            "queued": queued,
            "abandoned": int(background_metrics["abandoned"]),
            "background_throttled": throttled,
            "oldest_queued_age_seconds": oldest_queued_age,
            "starvation_relief_active": bool(admission_metrics.get("background_starvation_relief_active")),
        }

    def get_admission_status(self) -> dict:
        admission_metrics = self._classification_admission.get_metrics()
        status = {
            "execution_mode": self._image_execution_mode,
            "live": {
                "capacity": int(admission_metrics["live"]["capacity"]),
                "queued": int(admission_metrics["live"]["queued"]),
                "running": int(admission_metrics["live"]["running"]),
                "abandoned": int(admission_metrics["live"]["abandoned"]),
                "oldest_running_age_seconds": admission_metrics["live"].get("oldest_running_age_seconds"),
            },
            "background": {
                "capacity": int(admission_metrics["background"]["capacity"]),
                "queued": int(admission_metrics["background"]["queued"]),
                "running": int(admission_metrics["background"]["running"]),
                "abandoned": int(admission_metrics["background"]["abandoned"]),
                "oldest_queued_age_seconds": admission_metrics["background"].get("oldest_queued_age_seconds"),
                "oldest_running_age_seconds": admission_metrics["background"].get("oldest_running_age_seconds"),
            },
            "background_throttled": bool(admission_metrics["background_throttled"]),
            "background_starvation_relief_active": bool(admission_metrics.get("background_starvation_relief_active")),
            "late_completions_ignored": int(admission_metrics["late_completions_ignored"]),
        }
        supervisor_metrics = self._get_supervisor_metrics()
        if supervisor_metrics is not None:
            status["worker_pools"] = supervisor_metrics
            status["late_results_ignored"] = int(supervisor_metrics.get("late_results_ignored") or 0)
        return status

    def check_health(self) -> dict:
        """Detailed health check for the classification service."""
        bird = self._models.get("bird")
        admission_metrics = self._classification_admission.get_metrics()
        live_image_health = self._describe_live_image_health(admission_metrics)
        background_image_health = self._describe_background_image_health(admission_metrics)
        supervisor_metrics = self._get_supervisor_metrics()
        effective_runtime_recovery = (
            self._latest_worker_runtime_recovery(supervisor_metrics)
            if self._image_execution_mode == "subprocess"
            else None
        ) or self._inference_health.most_recent_recovery()

        # Determine which TFLite runtime is actually in use
        tflite_type = _tflite_runtime_name() if tflite is not None else "none"

        runtime_recovery = {
            "invalid_output_failures": self._runtime_invalid_output_failures,
            "fallback_recoveries": self._runtime_fallback_recoveries,
            "last_recovery": effective_runtime_recovery,
        }
        runtime_recovery_failed = bool((effective_runtime_recovery or {}).get("status") == "failed")
        bird_runtime_ready = False
        if self._image_execution_mode == "subprocess":
            if supervisor_metrics is None:
                bird_runtime_ready = False
            else:
                live_pool = supervisor_metrics.get("live") or {}
                background_pool = supervisor_metrics.get("background") or {}
                live_workers = int(live_pool.get("workers") or 0)
                background_workers = int(background_pool.get("workers") or 0)
                live_circuit_open = bool(live_pool.get("circuit_open"))
                background_circuit_open = bool(background_pool.get("circuit_open"))
                live_exit_reason = str(live_pool.get("last_exit_reason") or "").strip()
                background_exit_reason = str(background_pool.get("last_exit_reason") or "").strip()
                explicit_start_failure = {
                    "startup_failed",
                    "startup_timeout",
                }
                bird_runtime_ready = bool(
                    live_workers > 0
                    or background_workers > 0
                    or (
                        not live_circuit_open
                        and not background_circuit_open
                        and live_exit_reason not in explicit_start_failure
                        and background_exit_reason not in explicit_start_failure
                    )
                )
        else:
            bird_runtime_ready = bool(bird and bird.loaded)

        health = {
            "status": "ok" if (bird_runtime_ready and not runtime_recovery_failed) else "error",
            "execution_mode": self._image_execution_mode,
            "runtimes": {
                "tflite": {"installed": tflite is not None, "type": tflite_type},
                "onnx": {"installed": ONNX_AVAILABLE, "available": ort is not None},
                "openvino": {"installed": OPENVINO_AVAILABLE, "available": OpenVINOCore is not None},
            },
            "models": {
                name: {
                    "loaded": model.loaded,
                    "runtime": (
                        "onnx"
                        if _safe_isinstance(model, ONNXModelInstance)
                        else ("openvino" if _safe_isinstance(model, OpenVINOModelInstance) else "tflite")
                    ),
                    "error": model.error,
                    # A label file altered after download names every detection
                    # wrongly, so the verdict is reported rather than only logged.
                    "labels": _label_integrity_for(model),
                }
                for name, model in self._models.items()
            },
            "live_image": live_image_health,
            "background_image": background_image_health,
            "background_throttled": background_image_health["background_throttled"],
            "runtime_recovery": runtime_recovery,
            "inference_health": self._inference_health.snapshot(),
            "runtime_benchmarks": dict(self._runtime_benchmarks or {}),
        }
        if supervisor_metrics is not None:
            health["worker_pools"] = supervisor_metrics
        return health

    # Legacy properties
    @property
    def interpreter(self):
        bird = self._models.get("bird")
        return getattr(bird, "interpreter", None)

    @property
    def labels(self) -> list[str]:
        bird = self._models.get("bird")
        if bird:
            return bird.labels
        if self._image_execution_mode == "subprocess" and not self._worker_process_mode:
            try:
                spec = self._resolve_active_bird_model_spec()
                labels_path = str(spec.get("labels_path") or "")
                if labels_path and os.path.exists(labels_path):
                    with open(labels_path, "r", encoding="utf-8", errors="replace") as handle:
                        return normalize_classifier_labels(line.strip() for line in handle.readlines() if line.strip())
            except Exception:
                return []
        return []

    @property
    def model_loaded(self) -> bool:
        bird = self._models.get("bird")
        return bool(getattr(bird, "loaded", False))

    @property
    def model_error(self) -> Optional[str]:
        bird = self._models.get("bird")
        return getattr(bird, "error", None)

    def get_status(self) -> dict:
        bird = self._models.get("bird")
        admission_metrics = self._classification_admission.get_metrics()
        live_image_health = self._describe_live_image_health(admission_metrics)
        # Reads the last known capabilities rather than detecting them. Detection
        # spawns subprocesses, and this runs on the event loop (#313).
        self._accel_caps_for_read()
        accel_caps_age = self._accel_caps_age_seconds()
        supervisor_metrics = self._get_supervisor_metrics()
        effective_runtime_recovery = (
            self._latest_worker_runtime_recovery(supervisor_metrics)
            if self._image_execution_mode == "subprocess"
            else None
        ) or self._inference_health.most_recent_recovery()
        effective_backend, effective_provider = (
            self._effective_subprocess_runtime_fields(effective_runtime_recovery)
            if self._image_execution_mode == "subprocess"
            else (self._inference_backend, self._active_inference_provider)
        )
        active_model_id = None
        effective_model_id = None
        try:
            from app.services.model_manager import model_manager

            active_model_id = getattr(model_manager, "active_model_id", None)
            crop_detector_status = dict(model_manager.get_crop_detector_spec() or {})
        except Exception:
            active_model_id = None
            crop_detector_status = {}

        if self._bird_crop_service is not None:
            try:
                crop_detector_status.update(dict(self._bird_crop_service.get_status() or {}))
            except Exception:
                pass

        selected_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        image_flavor = get_image_flavor()
        packaged_providers = packaged_inference_providers(image_flavor)
        try:
            active_model_spec = self._resolve_active_bird_model_spec()
            supported_providers = list(active_model_spec.get("supported_inference_providers") or [])
            validated_providers = list(active_model_spec.get("host_validated_inference_providers") or [])
            provider_order = list(active_model_spec.get("host_provider_preference_order") or [])
            candidate_providers = list(active_model_spec.get("candidate_inference_providers") or supported_providers)
            effective_model_id = str(active_model_spec.get("model_id") or active_model_id or "").strip() or None
        except Exception:
            supported_providers = []
            validated_providers = []
            provider_order = []
            candidate_providers = []
        provider_capabilities = _provider_capability_contract(
            caps=self._accel_caps,
            packaged_providers=packaged_providers,
            supported_providers=supported_providers,
            active_backend=str(effective_backend or ""),
            active_provider=str(effective_provider or ""),
            provider_order=provider_order,
        )

        status = {
            "image_execution_mode": self._image_execution_mode,
            "accel_caps_age_seconds": accel_caps_age,
            "accel_caps_stale": accel_caps_age is None or accel_caps_age > self._accel_caps_ttl_seconds,
            "image_flavor": image_flavor,
            "packaged_inference_providers": list(packaged_providers),
            "image_flavor_warning": image_flavor_warning(image_flavor, selected_provider),
            "runtime": _tflite_runtime_name(),
            "runtime_installed": tflite is not None,
            "onnx_available": ONNX_AVAILABLE,
            "active_model_id": active_model_id,
            "effective_model_id": effective_model_id,
            "openvino_available": bool(self._accel_caps.get("openvino_available")),
            "openvino_version": self._accel_caps.get("openvino_version"),
            "openvino_import_path": self._accel_caps.get("openvino_import_path"),
            "openvino_import_error": self._accel_caps.get("openvino_import_error"),
            "openvino_probe_error": self._accel_caps.get("openvino_probe_error"),
            "openvino_gpu_probe_error": self._accel_caps.get("openvino_gpu_probe_error"),
            "openvino_model_compile_ok": self._openvino_model_compile_ok,
            "openvino_model_compile_device": self._openvino_model_compile_device,
            "openvino_model_compile_error": self._openvino_model_compile_error,
            "openvino_model_compile_unsupported_ops": list(self._openvino_model_compile_unsupported_ops or []),
            "openvino_devices": self._accel_caps.get("openvino_devices") or [],
            "cuda_provider_installed": bool(self._accel_caps.get("cuda_provider_installed")),
            "cuda_hardware_available": bool(self._accel_caps.get("cuda_hardware_available")),
            "cuda_available": bool(self._accel_caps.get("cuda_available")),
            "cuda_probe_error": self._accel_caps.get("cuda_probe_error"),
            "intel_gpu_available": bool(self._accel_caps.get("intel_gpu_available")),
            "intel_cpu_available": bool(self._accel_caps.get("intel_cpu_available")),
            "intel_npu_available": bool(self._accel_caps.get("intel_npu_available")),
            "host_device_eligibility": _host_device_eligibility_summary(),
            "active_model_candidate_providers": candidate_providers,
            "active_model_validated_providers": validated_providers,
            "validated_provider_preference_order": provider_order,
            "dev_dri_present": bool(self._accel_caps.get("dev_dri_present")),
            "dev_dri_entries": self._accel_caps.get("dev_dri_entries") or [],
            "dev_accel_present": bool(self._accel_caps.get("dev_accel_present")),
            "process_uid": self._accel_caps.get("process_uid"),
            "process_gid": self._accel_caps.get("process_gid"),
            "process_groups": self._accel_caps.get("process_groups") or [],
            "selected_provider": selected_provider,
            "active_provider": effective_provider,
            "inference_backend": effective_backend,
            "fallback_reason": self._inference_fallback_reason,
            "model_config_warnings": list(self._model_config_warnings or []),
            "image_max_concurrent": CLASSIFIER_IMAGE_MAX_CONCURRENT,
            "image_admission_timeout_seconds": CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS,
            "image_admission_timeouts": self._image_admission_timeouts,
            "runtime_invalid_output_failures": self._runtime_invalid_output_failures,
            "runtime_fallback_recoveries": self._runtime_fallback_recoveries,
            "runtime_gpu_retries": self._runtime_gpu_retries,
            "runtime_gpu_restore_attempts": self._runtime_gpu_restore_attempts,
            "runtime_gpu_restore_successes": self._runtime_gpu_restore_successes,
            "runtime_gpu_restore_failures": self._runtime_gpu_restore_failures,
            "gpu_restore_not_before_monotonic": self._gpu_restore_not_before_monotonic,
            "strict_non_finite_output": _strict_non_finite_output_enabled(),
            "inference_health": self._inference_health.snapshot(),
            "runtime_benchmarks": dict(self._runtime_benchmarks or {}),
            "openvino_runtime": self._openvino_runtime_snapshot(
                active_backend=effective_backend,
                active_provider=effective_provider,
            ),
            "live_image_max_concurrent": admission_metrics["live"]["capacity"],
            "live_image_admission_timeout_seconds": CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS,
            "live_image_admission_timeouts": self._live_image_admission_timeouts,
            "live_image_in_flight": admission_metrics["live"]["running"],
            "live_image_queued": admission_metrics["live"]["queued"],
            "live_image_abandoned": admission_metrics["live"]["abandoned"],
            "live_image": live_image_health,
            "background_image_in_flight": admission_metrics["background"]["running"],
            "background_image_queued": admission_metrics["background"]["queued"],
            "background_image_abandoned": admission_metrics["background"]["abandoned"],
            "late_completions_ignored": admission_metrics["late_completions_ignored"],
            "admission_recent_outcomes": admission_metrics["recent_outcomes"],
            "background_throttled": admission_metrics["background_throttled"],
            **provider_capabilities,
            # legacy compatibility (can be removed later)
            "cuda_enabled": _normalize_inference_provider(
                getattr(settings.classification, "inference_provider", "auto")
            )
            == "cuda",
            "models": {},
            "crop_detector": crop_detector_status,
        }
        if supervisor_metrics is not None:
            status["worker_pools"] = supervisor_metrics

        for name, model in self._models.items():
            model_status = model.get_status()
            if name == "bird" and _safe_isinstance(model, ONNXModelInstance) and model.session:
                model_status["active_providers"] = model.session.get_providers()
            status["models"][name] = model_status

        if bird:
            # For backward compatibility
            status.update(bird.get_status())

        return status

    def probe_bird_runtime(
        self,
        *,
        device: str = "GPU",
        image: Image.Image | None = None,
        synthetic_image: bool = False,
    ) -> dict[str, Any]:
        normalized_device = str(device or "GPU").strip().upper() or "GPU"
        if normalized_device not in {"CPU", "GPU", "NPU"}:
            raise ValueError(f"Unsupported probe device: {device}")

        spec = self._resolve_active_bird_model_spec()
        model = OpenVINOModelInstance(
            "bird",
            str(spec.get("model_path") or ""),
            str(spec.get("labels_path") or ""),
            preprocessing=spec.get("preprocessing"),
            input_size=int(spec.get("input_size") or 384),
            device_name=normalized_device,
        )
        loaded = model.load()
        probe_image = image
        if probe_image is None:
            synthetic_image = True
            probe_image = model._build_startup_self_test_image()

        report: dict[str, Any] = {
            "device": normalized_device,
            "synthetic_image": bool(synthetic_image),
            "runtime": {
                "backend": "openvino",
                "provider": {"GPU": "intel_gpu", "NPU": "intel_npu"}.get(normalized_device, "intel_cpu"),
            },
            "model": {
                **self._runtime_model_snapshot(),
            },
            "gpu_settings": self._gpu_runtime_settings_snapshot(),
            "compile_ok": bool(loaded),
            "compile_error": getattr(model, "error", None),
            "compile_properties": model.current_compile_properties() if loaded else {},
            "startup_self_test": model.startup_self_test_status(),
        }
        if not loaded:
            report["status"] = "compile_failed"
            self._update_bird_model_compatibility(device=normalized_device, status=report["status"])
            return report

        probe_report = model.probe(probe_image)
        report.update(probe_report)
        self._update_bird_model_compatibility(device=normalized_device, status=str(report.get("status") or ""))
        report["image"] = {
            "mode": str(probe_image.mode),
            "size": [int(probe_image.size[0]), int(probe_image.size[1])],
        }
        log.info(
            "Executed bird runtime probe",
            device=normalized_device,
            synthetic_image=bool(synthetic_image),
            status=report.get("status"),
            compile_properties=report.get("compile_properties"),
            output_summary=report.get("output_summary"),
        )
        return report

    def get_wildlife_status(self) -> dict:
        wildlife = self._models.get("wildlife")
        if wildlife:
            return wildlife.get_status()

        model_path, labels_path = self._get_model_paths(
            settings.classification.wildlife_model, settings.classification.wildlife_labels
        )
        model_exists = os.path.exists(model_path)
        labels_exist = os.path.exists(labels_path)
        labels_count = 0
        if labels_exist:
            try:
                with open(labels_path, "r") as f:
                    labels_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        return {
            "loaded": False,
            "error": None if model_exists else f"Model not found: {model_path}",
            "labels_count": labels_count,
            "enabled": model_exists,
            "model_path": model_path,
        }

    def _resolve_active_model_id(self) -> str:
        try:
            from app.services.model_manager import model_manager

            active_model_id = str(getattr(model_manager, "active_model_id", "") or "").strip()
            if active_model_id:
                return active_model_id
        except Exception:
            pass

        configured_model = str(getattr(settings.classification, "model", "") or "").strip()
        return configured_model or "unknown"

    def _input_context_extra(self, input_context: ClassificationInputContext, key: str) -> Any | None:
        extra = getattr(input_context, "__pydantic_extra__", {}) or {}
        if key in extra:
            return extra.get(key)
        return getattr(input_context, key, None)

    def _resolve_frigate_hint_crop(
        self,
        image: Image.Image,
        *,
        input_context: ClassificationInputContext,
    ) -> dict[str, Any] | None:
        for hint_key, reason in (("frigate_box", "frigate_box"), ("frigate_region", "frigate_region")):
            raw_hint = self._input_context_extra(input_context, hint_key)
            box = self._restore_frigate_hint_box(raw_hint, image.size)
            if box is None:
                continue
            expanded = self._expand_hint_box(box, image.size)
            if expanded is None:
                continue
            crop_image = image.crop(expanded)
            return {
                "crop_image": crop_image,
                "box": expanded,
                "confidence": None,
                "reason": reason,
            }
        return None

    def _tracked_frigate_box_for_frame(
        self,
        input_context: ClassificationInputContext,
        *,
        frame_offset_seconds: float | None,
    ) -> list[float] | None:
        """Align Frigate's tracked path with the actual clip timeline."""
        raw_path_data = self._input_context_extra(input_context, "frigate_path_data")
        raw_box = self._input_context_extra(input_context, "frigate_box")
        raw_clip_start = self._input_context_extra(input_context, "clip_start_timestamp")
        if (
            not isinstance(raw_path_data, list)
            or not isinstance(raw_box, (list, tuple))
            or len(raw_box) != 4
            or frame_offset_seconds is None
        ):
            return None
        try:
            clip_start = float(raw_clip_start)
            offset = float(frame_offset_seconds)
            _left, _top, width, height = [float(value) for value in raw_box]
        except (TypeError, ValueError):
            return None
        if (
            not all(math.isfinite(value) for value in (clip_start, offset, width, height))
            or offset < 0.0
            or not (0.0 < width <= 1.0)
            or not (0.0 < height <= 1.0)
        ):
            return None

        path_points: list[tuple[float, float, float]] = []
        for item in raw_path_data:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            point = item[0]
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                y = float(point[1])
                timestamp = float(item[1])
            except (TypeError, ValueError):
                continue
            if all(math.isfinite(value) for value in (x, y, timestamp)) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                path_points.append((timestamp, x, y))
        if not path_points:
            return None

        target_timestamp = clip_start + offset
        point_timestamp, bottom_center_x, bottom_y = min(
            path_points,
            key=lambda item: abs(item[0] - target_timestamp),
        )
        if abs(point_timestamp - target_timestamp) > 0.75:
            return None

        left = max(0.0, min(1.0 - width, bottom_center_x - width / 2.0))
        top = max(0.0, min(1.0 - height, bottom_y - height))
        return [left, top, width, height]

    def _video_frame_input_context(
        self,
        input_context: ClassificationInputContext,
        *,
        frame_offset_seconds: float | None,
    ) -> ClassificationInputContext:
        """Return crop hints that are valid at this frame's clip timestamp.

        A Frigate event's top-level box describes one tracked instant. Reusing it
        across a full-visit recording repeatedly classifies the same background
        patch after a fleeting bird has moved away. Recording clips therefore use
        a Frigate hint only when ``path_data`` can align it to this frame. Event
        clips retain the static fallback when no tracking path was supplied.
        """
        frame_context_payload = dict(input_context.model_dump())
        clip_variant = str(self._input_context_extra(input_context, "clip_variant") or "event").strip().lower()
        raw_path_data = self._input_context_extra(input_context, "frigate_path_data")
        requires_time_aligned_hint = clip_variant == "recording" or bool(raw_path_data)
        if requires_time_aligned_hint:
            frame_context_payload.pop("frigate_box", None)
            frame_context_payload.pop("frigate_region", None)
            tracked_box = self._tracked_frigate_box_for_frame(
                input_context,
                frame_offset_seconds=frame_offset_seconds,
            )
            if tracked_box is not None:
                frame_context_payload["frigate_box"] = tracked_box
        return _normalize_classification_input_context(frame_context_payload)

    @staticmethod
    def _frigate_snapshot_crop_box(
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        """Recreate Frigate's saved-snapshot crop region defensively.

        Frigate centres a square around the tracked box, uses a 1.1 multiplier,
        rounds the side to a multiple of four, and keeps at least 300 pixels of
        context. Capping the square to the actual image makes the equivalent
        operation safe for unusually small or externally supplied snapshots.
        """
        left, top, right, bottom = box
        image_width, image_height = image_size
        box_width = right - left
        box_height = bottom - top
        if image_width <= 0 or image_height <= 0 or box_width <= 0 or box_height <= 0:
            return None

        longest_edge = max(box_width, box_height)
        side = int((longest_edge * 1.1) // 4 * 4)
        side = max(300, side)
        side = min(side, image_width, image_height)
        if side <= 0:
            return None

        centre_x = left + (box_width / 2.0)
        centre_y = top + (box_height / 2.0)
        crop_left = int(centre_x - (side / 2.0))
        crop_top = int(centre_y - (side / 2.0))
        crop_left = max(0, min(image_width - side, crop_left))
        crop_top = max(0, min(image_height - side, crop_top))
        return crop_left, crop_top, crop_left + side, crop_top + side

    def _resolve_frigate_snapshot_crop(
        self,
        image: Image.Image,
        *,
        input_context: ClassificationInputContext,
    ) -> dict[str, Any] | None:
        """Restore the crop Frigate supplies for an active event snapshot."""
        for hint_key, reason in (("frigate_box", "frigate_box"), ("frigate_region", "frigate_region")):
            raw_hint = self._input_context_extra(input_context, hint_key)
            box = self._restore_frigate_hint_box(raw_hint, image.size)
            if box is None:
                continue
            crop_box = self._frigate_snapshot_crop_box(box, image.size)
            if crop_box is None:
                continue
            return {
                "crop_image": image.crop(crop_box),
                "box": crop_box,
                "confidence": None,
                "reason": reason,
            }
        return None

    def _bird_crop_source_priority(self) -> str:
        configured = (
            str(getattr(settings.classification, "bird_crop_source_priority", "frigate_hints_first") or "")
            .strip()
            .lower()
        )
        if configured in {
            "frigate_hints_first",
            "crop_model_first",
            "crop_model_only",
            "frigate_hints_only",
        }:
            return configured
        return "frigate_hints_first"

    def _resolve_model_crop(
        self,
        image: Image.Image,
    ) -> dict[str, Any] | None:
        try:
            if self._bird_crop_service is None:
                return None
            generate_classification_crop = getattr(self._bird_crop_service, "generate_classification_crop", None)
            if callable(generate_classification_crop):
                return generate_classification_crop(image)
            return self._bird_crop_service.generate_crop(image)
        except Exception as exc:
            raise exc

    def _resolve_model_candidate_crop(
        self,
        image: Image.Image,
        *,
        search_box: tuple[int, int, int, int] | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a distance-tolerant crop only for multi-representation evidence."""
        crop_service = self._bird_crop_service
        if crop_service is None:
            return None
        guided_generator = getattr(crop_service, "generate_guided_classification_candidate_crop", None)
        guided_declared = callable(getattr(type(crop_service), "generate_guided_classification_candidate_crop", None))
        if search_box is not None and callable(guided_generator) and guided_declared:
            return guided_generator(image, search_box=search_box)
        candidate_generator = getattr(crop_service, "generate_classification_candidate_crop", None)
        declared_on_type = callable(getattr(type(crop_service), "generate_classification_candidate_crop", None))
        if callable(candidate_generator) and declared_on_type:
            return candidate_generator(image)
        return self._resolve_model_crop(image)

    def _bird_crop_detector_available(self) -> bool:
        crop_service = self._bird_crop_service
        if crop_service is None:
            return False
        get_status = getattr(crop_service, "get_status", None)
        if not callable(get_status):
            return True
        try:
            status = get_status()
        except Exception:
            return True
        if not isinstance(status, dict):
            return True
        return status.get("installed") is not False and status.get("enabled_for_runtime") is not False

    def _video_frame_candidates(
        self,
        image: Image.Image,
        *,
        input_context: ClassificationInputContext,
    ) -> list[tuple[str, Image.Image]]:
        """Return bounded, independently evaluated views of one video frame."""
        if bool(input_context.is_cropped):
            supplied_source = str(self._input_context_extra(input_context, "input_source") or "provided_crop")
            return [(supplied_source, image)]

        candidates: list[tuple[str, Image.Image]] = [("full_frame", image)]
        seen_boxes: set[tuple[int, int, int, int]] = set()

        hint_result = self._resolve_frigate_hint_crop(image, input_context=input_context)
        hint_image = hint_result.get("crop_image") if isinstance(hint_result, dict) else None
        hint_box: tuple[int, int, int, int] | None = None
        if isinstance(hint_image, Image.Image):
            candidates.append(("frigate_hint_crop", hint_image))
            raw_hint_box = hint_result.get("box")
            if isinstance(raw_hint_box, tuple) and len(raw_hint_box) == 4:
                hint_box = raw_hint_box
                seen_boxes.add(raw_hint_box)

        if self._bird_crop_detector_available():
            try:
                model_result = self._resolve_model_candidate_crop(image, search_box=hint_box)
            except Exception as exc:
                log.debug("Video frame crop detector failed; retaining other inputs", error=str(exc))
                model_result = None
            model_image = model_result.get("crop_image") if isinstance(model_result, dict) else None
            model_box = model_result.get("box") if isinstance(model_result, dict) else None
            duplicate_box = isinstance(model_box, tuple) and len(model_box) == 4 and model_box in seen_boxes
            if isinstance(model_image, Image.Image) and not duplicate_box:
                candidates.append(("model_crop", model_image))

        return candidates

    def _resolve_crop_by_priority(
        self,
        crop_source_image: Image.Image,
        *,
        input_context: ClassificationInputContext,
    ) -> dict[str, Any] | None:
        priority = self._bird_crop_source_priority()
        if priority == "crop_model_only":
            return self._resolve_model_crop(crop_source_image)
        if priority == "frigate_hints_only":
            return self._resolve_frigate_hint_crop(crop_source_image, input_context=input_context)
        if priority == "crop_model_first":
            crop_result = self._resolve_model_crop(crop_source_image)
            crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
            if isinstance(crop_image, Image.Image):
                return crop_result
            hint_crop = self._resolve_frigate_hint_crop(crop_source_image, input_context=input_context)
            return hint_crop or crop_result
        hint_crop = self._resolve_frigate_hint_crop(crop_source_image, input_context=input_context)
        if isinstance(hint_crop, dict) and isinstance(hint_crop.get("crop_image"), Image.Image):
            return hint_crop
        crop_result = self._resolve_model_crop(crop_source_image)
        return crop_result or hint_crop

    def _restore_frigate_hint_box(
        self,
        raw_hint: Any,
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        if not isinstance(raw_hint, (list, tuple)) or len(raw_hint) != 4:
            return None
        try:
            left = float(raw_hint[0])
            top = float(raw_hint[1])
            width = float(raw_hint[2])
            height = float(raw_hint[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, width, height)):
            return None

        image_width, image_height = image_size
        normalized = 0.0 <= left <= 1.0 and 0.0 <= top <= 1.0 and 0.0 <= width <= 1.0 and 0.0 <= height <= 1.0
        if normalized:
            left *= float(image_width)
            top *= float(image_height)
            width *= float(image_width)
            height *= float(image_height)

        right = left + width
        bottom = top + height
        if right <= left or bottom <= top:
            return None
        left_i = max(0, min(image_width, int(math.floor(left))))
        top_i = max(0, min(image_height, int(math.floor(top))))
        right_i = max(0, min(image_width, int(math.ceil(right))))
        bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _expand_hint_box(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        expand_ratio = 0.12
        min_crop_size = 96
        crop_service = self._bird_crop_service
        if crop_service is not None:
            try:
                crop_policy = crop_service.get_effective_crop_policy()
            except Exception:
                crop_policy = None
            try:
                if isinstance(crop_policy, dict):
                    expand_ratio = max(0.0, float(crop_policy.get("expand_ratio", expand_ratio)))
                else:
                    expand_ratio = max(0.0, float(getattr(crop_service, "expand_ratio", expand_ratio)))
            except Exception:
                expand_ratio = 0.12
            try:
                if isinstance(crop_policy, dict):
                    min_crop_size = max(1, int(crop_policy.get("min_crop_size", min_crop_size)))
                else:
                    min_crop_size = max(1, int(getattr(crop_service, "min_crop_size", min_crop_size)))
            except Exception:
                min_crop_size = 96
        pad_x = int(round(width * expand_ratio))
        pad_y = int(round(height * expand_ratio))
        expanded_left = max(0, left - pad_x)
        expanded_top = max(0, top - pad_y)
        expanded_right = min(int(image_size[0]), right + pad_x)
        expanded_bottom = min(int(image_size[1]), bottom + pad_y)
        crop_width = expanded_right - expanded_left
        crop_height = expanded_bottom - expanded_top
        if crop_width < min_crop_size or crop_height < min_crop_size:
            return None
        if expanded_right <= expanded_left or expanded_bottom <= expanded_top:
            return None
        return expanded_left, expanded_top, expanded_right, expanded_bottom

    def _resolve_bird_classification_image(
        self,
        image: Image.Image,
        *,
        input_context: Any | None = None,
    ) -> tuple[Image.Image, dict[str, Any]]:
        normalized_input_context = _normalize_classification_input_context(input_context)
        diagnostics: dict[str, Any] = {
            "crop_attempted": False,
            "crop_applied": False,
            "crop_reason": "crop_disabled",
            "source_reason": "standard",
        }

        if bool(self._input_context_extra(normalized_input_context, "disable_crop_resolution")):
            diagnostics["crop_reason"] = "explicit_input_representation"
            return image, diagnostics

        if bool(normalized_input_context.is_cropped):
            diagnostics["crop_reason"] = "input_already_cropped"
            log.debug(
                "Bird crop resolution skipped",
                crop_attempted=False,
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
            )
            return image, diagnostics

        restore_frigate_crop = (
            self._input_context_extra(normalized_input_context, "restore_frigate_snapshot_crop") is True
        )
        if restore_frigate_crop:
            diagnostics["crop_attempted"] = True
            crop_result = self._resolve_frigate_snapshot_crop(
                image,
                input_context=normalized_input_context,
            )
            crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
            if isinstance(crop_image, Image.Image):
                diagnostics["crop_applied"] = True
                diagnostics["crop_reason"] = str(crop_result.get("reason") or "frigate_box")
                diagnostics["source_reason"] = "frigate_snapshot_crop_restored"
                log.debug(
                    "Frigate snapshot crop restored",
                    crop_attempted=True,
                    crop_applied=True,
                    crop_reason=diagnostics["crop_reason"],
                    source_reason=diagnostics["source_reason"],
                    crop_box=crop_result.get("box"),
                )
                return crop_image, diagnostics
            diagnostics["crop_reason"] = "frigate_snapshot_crop_unavailable"
            diagnostics["source_reason"] = "frigate_snapshot_crop_restore_failed"

        try:
            spec = dict(self._resolve_active_bird_model_spec() or {})
        except Exception as exc:
            if not restore_frigate_crop:
                diagnostics["crop_reason"] = "spec_resolution_failed"
            log.debug(
                "Bird crop resolution skipped",
                crop_attempted=diagnostics["crop_attempted"],
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
                error=_summarize_runtime_exception(exc),
            )
            return image, diagnostics

        crop_generator = dict(spec.get("crop_generator") or {})
        crop_enabled = bool(crop_generator.get("enabled"))
        if not crop_enabled:
            if not restore_frigate_crop:
                diagnostics["crop_reason"] = "crop_disabled"
            log.debug(
                "Bird crop resolution skipped",
                crop_attempted=diagnostics["crop_attempted"],
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
            )
            return image, diagnostics

        diagnostics["crop_attempted"] = True
        source_preference = str(crop_generator.get("source_preference") or "standard").strip().lower()
        crop_source_image = image
        if self._crop_source_resolver is not None:
            try:
                crop_source_image, source_diagnostics = self._crop_source_resolver.resolve(
                    image,
                    input_context=normalized_input_context,
                    source_preference=source_preference,
                )
                if isinstance(source_diagnostics, dict):
                    diagnostics.update(source_diagnostics)
            except Exception as exc:
                diagnostics["source_reason"] = "source_resolver_error"
                log.warning(
                    "Bird crop source resolution failed",
                    crop_attempted=True,
                    crop_applied=False,
                    crop_reason=diagnostics["crop_reason"],
                    source_reason=diagnostics["source_reason"],
                    error=_summarize_runtime_exception(exc),
                )
                crop_source_image = image

        try:
            crop_result = self._resolve_crop_by_priority(
                crop_source_image,
                input_context=normalized_input_context,
            )
        except Exception as exc:
            diagnostics["crop_reason"] = "crop_service_error"
            log.warning(
                "Bird crop generation failed",
                crop_attempted=True,
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
                source_reason=diagnostics.get("source_reason"),
                error=_summarize_runtime_exception(exc),
            )
            return image, diagnostics

        crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
        crop_reason = str((crop_result or {}).get("reason") or "no_crop")
        if isinstance(crop_image, Image.Image):
            diagnostics["crop_applied"] = True
            diagnostics["crop_reason"] = crop_reason
            log.debug(
                "Bird crop applied",
                crop_attempted=True,
                crop_applied=True,
                crop_reason=diagnostics["crop_reason"],
                source_reason=diagnostics.get("source_reason"),
                crop_box=(crop_result or {}).get("box") if isinstance(crop_result, dict) else None,
            )
            return crop_image, diagnostics

        diagnostics["crop_reason"] = crop_reason
        log.debug(
            "Bird crop unavailable; using original image",
            crop_attempted=True,
            crop_applied=False,
            crop_reason=diagnostics["crop_reason"],
            source_reason=diagnostics.get("source_reason"),
        )
        return image, diagnostics

    def _resolved_classification_input_provenance(
        self,
        *,
        input_context: ClassificationInputContext,
        crop_diagnostics: dict[str, Any],
    ) -> tuple[str, bool]:
        """Describe the image that actually reached model preprocessing."""
        supplied_source = str(self._input_context_extra(input_context, "input_source") or "").strip().lower()
        if bool(crop_diagnostics.get("crop_applied")):
            crop_reason = str(crop_diagnostics.get("crop_reason") or "").strip().lower()
            if crop_reason in {"frigate_box", "frigate_region"}:
                return "snapshot_frigate_hint_crop", True
            return "snapshot_model_crop", True
        if supplied_source:
            return supplied_source, bool(input_context.is_cropped)
        if bool(input_context.is_cropped):
            return "provided_crop", True
        return "full_frame", False

    def _attach_classification_input_provenance(
        self,
        results: list[dict],
        *,
        input_context: ClassificationInputContext,
        crop_diagnostics: dict[str, Any],
    ) -> list[dict]:
        has_explicit_source = bool(str(self._input_context_extra(input_context, "input_source") or "").strip())
        if (
            not has_explicit_source
            and not bool(input_context.is_cropped)
            and not bool(crop_diagnostics.get("crop_applied"))
        ):
            return results
        input_source, input_is_cropped = self._resolved_classification_input_provenance(
            input_context=input_context,
            crop_diagnostics=crop_diagnostics,
        )
        for result in results:
            if not isinstance(result, dict):
                continue
            result["input_source"] = input_source
            result["input_is_cropped"] = input_is_cropped
        return results

    def classify(
        self,
        image: Image.Image,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
    ) -> list[dict]:
        """Classify an image using the bird model."""
        normalized_input_context = _normalize_classification_input_context(input_context)
        attempted_models: set[int] = set()
        while True:
            self._maybe_restore_gpu_provider()
            bird = self._models.get("bird")
            if bird is None:
                return []
            model_identity = id(bird)
            if model_identity in attempted_models:
                return []
            attempted_models.add(model_identity)
            try:
                crop_image, crop_diagnostics = self._resolve_bird_classification_image(
                    image,
                    input_context=normalized_input_context,
                )
                results = _invoke_model_classify(bird, crop_image, input_context=normalized_input_context)
                if self._inference_backend == "openvino" and self._active_inference_provider == "intel_gpu":
                    self._record_gpu_success()
                return self._attach_classification_input_provenance(
                    results,
                    input_context=normalized_input_context,
                    crop_diagnostics=crop_diagnostics,
                )
            except InvalidInferenceOutputError as exc:
                if not self._recover_from_invalid_bird_output(bird, exc):
                    raise
        return []

    def _classify_raw_with_runtime_recovery(
        self,
        image: Image.Image,
        input_context: Any | None = None,
    ) -> tuple[np.ndarray, ModelType | None]:
        crop_image, _crop_diagnostics = self._resolve_bird_classification_image(
            image,
            input_context=input_context,
        )
        return self._classify_resolved_raw_with_runtime_recovery(crop_image)

    def _classify_resolved_raw_with_runtime_recovery(
        self,
        image: Image.Image,
    ) -> tuple[np.ndarray, ModelType | None]:
        """Classify an image whose full-frame/crop representation is already chosen."""
        attempted_models: set[int] = set()
        while True:
            self._maybe_restore_gpu_provider()
            bird = self._models.get("bird")
            if bird is None:
                return np.array([]), None
            model_identity = id(bird)
            if model_identity in attempted_models:
                return np.array([]), bird
            attempted_models.add(model_identity)
            try:
                scores = bird.classify_raw(image)
                if self._inference_backend == "openvino" and self._active_inference_provider == "intel_gpu":
                    self._record_gpu_success()
                return scores, bird
            except InvalidInferenceOutputError as exc:
                if not self._recover_from_invalid_bird_output(bird, exc):
                    raise

    def _encode_image_for_worker(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    async def _run_supervised_inference(
        self,
        priority: Literal["live", "background"],
        image: Image.Image,
        camera_name: Optional[str],
        model_id: Optional[str],
        input_context: Any | None = None,
        *,
        work_id: str | None = None,
        lease_token: int | None = None,
    ) -> list[dict]:
        if self._classifier_supervisor is None:
            raise RuntimeError("classifier supervisor is not configured")
        normalized_input_context = _normalize_classification_input_context(input_context)
        try:
            return await self._classifier_supervisor.classify(
                priority=priority,
                work_id=str(work_id or f"{priority}-{time.monotonic_ns()}"),
                lease_token=int(lease_token or 1),
                image_b64=self._encode_image_for_worker(image),
                camera_name=camera_name,
                model_id=model_id,
                input_context=dict(normalized_input_context.model_dump())
                if normalized_input_context is not None
                else None,
            )
        except ClassifierWorkerCircuitOpenError:
            if priority == "live":
                raise LiveImageClassificationOverloadedError("classify_snapshot_circuit_open") from None
            raise BackgroundImageClassificationUnavailableError("background_image_circuit_open") from None
        except (ClassifierWorkerHeartbeatTimeoutError, ClassifierWorkerDeadlineExceededError):
            if priority == "live":
                raise ClassificationLeaseExpiredError(
                    "live",
                    "live_image_inference",
                    float(getattr(settings.classification, "worker_hard_deadline_seconds", 35.0) or 35.0),
                ) from None
            raise BackgroundImageClassificationUnavailableError("background_image_worker_timed_out") from None
        except ClassifierWorkerStartupTimeoutError:
            if priority == "live":
                raise LiveImageClassificationOverloadedError("classify_snapshot_worker_unavailable") from None
            raise BackgroundImageClassificationUnavailableError("background_image_worker_startup_timeout") from None
        except ClassifierWorkerExitedError:
            if priority == "live":
                raise LiveImageClassificationOverloadedError("classify_snapshot_worker_unavailable") from None
            raise BackgroundImageClassificationUnavailableError("background_image_worker_unavailable") from None

    async def _run_coordinated_inference(
        self,
        priority: Literal["live", "background"],
        kind: str,
        runner: Callable[..., list[dict] | Awaitable[list[dict]]],
        *,
        queue_timeout_seconds: float | None = None,
        runner_accepts_work_metadata: bool = False,
        on_lease_expired: Callable[[str, int], Awaitable[None] | None] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict]:
        if not isinstance(queue_timeout_seconds, (int, float)) or queue_timeout_seconds <= 0:
            queue_timeout_seconds = (
                CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS
                if priority == "live"
                else CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS
            )
        lease_timeout_seconds = (
            CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS
            if priority == "live"
            else (
                CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS
                if kind == "background_image_inference"
                else CLASSIFIER_IMAGE_LEASE_TIMEOUT_SECONDS
            )
        )
        pressure_metrics = self._classification_admission.get_metrics()
        priority_metrics = pressure_metrics[priority]
        capacity = int(priority_metrics["capacity"])
        latency_health_eligible = (
            int(priority_metrics.get("queued") or 0) == 0
            and int(priority_metrics.get("running") or 0) == 0
            and not bool(pressure_metrics.get("background_throttled"))
        )
        started_at = time.monotonic()
        runtime_key = self._inference_runtime_key_from_context(context)
        runner_latency_seconds: float | None = None

        async def _timed_runner(*runner_args: Any) -> list[dict]:
            nonlocal runner_latency_seconds
            runner_started_at = time.monotonic()
            try:
                return await runner(*runner_args)
            finally:
                runner_latency_seconds = time.monotonic() - runner_started_at

        try:
            result = await self._classification_admission.submit(
                priority=priority,
                kind=kind,
                runner=_timed_runner,
                queue_timeout_seconds=queue_timeout_seconds,
                lease_timeout_seconds=lease_timeout_seconds,
                runner_accepts_work_metadata=runner_accepts_work_metadata,
                on_lease_expired=on_lease_expired,
                context=context,
            )
            self._inference_health.record(
                runtime_key,
                outcome="ok",
                latency_seconds=runner_latency_seconds
                if runner_latency_seconds is not None
                else time.monotonic() - started_at,
                latency_health_eligible=latency_health_eligible,
            )
            return result
        except ClassificationAdmissionTimeoutError:
            self._inference_health.record(
                runtime_key,
                outcome="timeout",
                latency_seconds=time.monotonic() - started_at,
            )
            if priority == "live":
                self._live_image_admission_timeouts += 1
                log.warning(
                    "Live image classification admission timed out; dropping request",
                    timeout_seconds=queue_timeout_seconds,
                    max_concurrent=capacity,
                    admission_timeouts=self._live_image_admission_timeouts,
                )
                raise LiveImageClassificationOverloadedError("classify_snapshot_overloaded") from None

            self._image_admission_timeouts += 1
            # Emit WARNING on the first timeout in a burst so it surfaces in
            # logs, then drop to DEBUG for subsequent ones to avoid flooding
            # during bulk backfill runs where many events hit the gate at once.
            _timeout_log = log.warning if self._image_admission_timeouts == 1 else log.debug
            _timeout_log(
                "Image classification admission timed out; dropping request",
                timeout_seconds=queue_timeout_seconds,
                max_concurrent=capacity,
                admission_timeouts=self._image_admission_timeouts,
            )
            raise BackgroundImageClassificationUnavailableError("background_image_overloaded") from None
        except ClassificationLeaseExpiredError as exc:
            self._inference_health.record(
                runtime_key,
                outcome="lease_expired",
                latency_seconds=time.monotonic() - started_at,
            )
            if priority == "live":
                self._record_live_lease_expiry_and_maybe_fallback(exc, runtime_key=runtime_key)
                log.warning(
                    "Live image classification lease expired; reclaiming capacity",
                    timeout_seconds=lease_timeout_seconds,
                    max_concurrent=capacity,
                )
                raise
            log.warning(
                "Image classification lease expired; reclaiming capacity",
                timeout_seconds=lease_timeout_seconds,
                max_concurrent=capacity,
            )
            raise BackgroundImageClassificationUnavailableError("background_image_lease_expired") from None
        except Exception:
            self._inference_health.record(
                runtime_key,
                outcome="exception",
                latency_seconds=time.monotonic() - started_at,
            )
            raise

    async def _run_coordinated_executor_inference(
        self,
        priority: Literal["live", "background"],
        executor: ThreadPoolExecutor,
        kind: str,
        fn: Callable[..., list[dict]],
        *args: Any,
        queue_timeout_seconds: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict]:
        async def _runner() -> list[dict]:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, fn, *args)

        return await self._run_coordinated_inference(
            priority,
            kind,
            _runner,
            queue_timeout_seconds=queue_timeout_seconds,
            context=context,
        )

    async def _abort_supervised_request_after_lease_expiry(
        self,
        *,
        priority: Literal["live", "background"],
        work_id: str,
        lease_token: int,
    ) -> None:
        if self._classifier_supervisor is None:
            return
        try:
            await self._classifier_supervisor.abort_request(
                priority=priority,
                work_id=work_id,
                lease_token=lease_token,
                reason="coordinator_lease_expired",
            )
        except Exception as exc:
            log.warning(
                "Failed to abort supervised classifier request after lease expiry",
                priority=priority,
                work_id=work_id,
                lease_token=lease_token,
                error=str(exc),
            )

    async def _run_coordinated_supervised_inference(
        self,
        priority: Literal["live", "background"],
        kind: str,
        image: Image.Image,
        camera_name: Optional[str],
        model_id: Optional[str],
        input_context: ClassificationInputContext | None = None,
        queue_timeout_seconds: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict]:
        async def _runner(work_id: str, lease_token: int) -> list[dict]:
            return await self._run_supervised_inference(
                priority,
                image,
                camera_name,
                model_id,
                input_context,
                work_id=work_id,
                lease_token=lease_token,
            )

        async def _on_lease_expired(work_id: str, lease_token: int) -> None:
            await self._abort_supervised_request_after_lease_expiry(
                priority=priority,
                work_id=work_id,
                lease_token=lease_token,
            )

        return await self._run_coordinated_inference(
            priority,
            kind,
            _runner,
            queue_timeout_seconds=queue_timeout_seconds,
            runner_accepts_work_metadata=True,
            on_lease_expired=_on_lease_expired,
            context=context,
        )

    async def _run_image_inference(
        self,
        fn: Callable[..., list[dict]],
        *args: Any,
    ) -> list[dict]:
        context = self._classification_admission_context(
            model_id=args[2] if len(args) > 2 else None,
        )
        if self._image_execution_mode == "subprocess" and args:
            return await self._run_coordinated_supervised_inference(
                "background",
                "image_inference",
                args[0],
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
                args[3] if len(args) > 3 else None,
                context=context,
            )
        return await self._run_coordinated_executor_inference(
            "background",
            self._image_executor,
            "image_inference",
            fn,
            *args,
            context=context,
        )

    def _classification_admission_context(self, *, model_id: str | None = None) -> dict[str, Any]:
        resolved_model_id = model_id
        if not resolved_model_id:
            try:
                resolved_model_id = self._resolve_active_model_id()
            except Exception:
                resolved_model_id = "unknown"
        return {
            "backend": self._inference_backend,
            "provider": self._active_inference_provider,
            "model_id": resolved_model_id,
            "execution_mode": self._image_execution_mode,
        }

    def _inference_runtime_key_from_context(self, context: dict[str, Any] | None) -> RuntimeKey:
        context = context or {}
        return RuntimeKey.from_values(
            context.get("backend") or self._inference_backend,
            context.get("provider") or self._active_inference_provider,
            context.get("model_id") or self._resolve_active_model_id(),
        )

    async def _run_live_image_inference(
        self,
        fn: Callable[..., list[dict]],
        *args: Any,
        queue_timeout_seconds: float | None = None,
    ) -> list[dict]:
        context = self._classification_admission_context(
            model_id=args[2] if len(args) > 2 else None,
        )
        if self._image_execution_mode == "subprocess" and args:
            return await self._run_coordinated_supervised_inference(
                "live",
                "live_image_inference",
                args[0],
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
                args[3] if len(args) > 3 else None,
                queue_timeout_seconds=queue_timeout_seconds,
                context=context,
            )
        return await self._run_coordinated_executor_inference(
            "live",
            self._live_image_executor,
            "live_image_inference",
            fn,
            *args,
            queue_timeout_seconds=queue_timeout_seconds,
            context=context,
        )

    async def classify_async(
        self,
        image: Image.Image,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
    ) -> list[dict]:
        """Async wrapper for classify to prevent blocking the event loop."""
        normalized_input_context = _normalize_classification_input_context(input_context)
        try:
            base_results = await self._run_image_inference(
                self.classify, image, camera_name, model_id, normalized_input_context
            )
        except BackgroundImageClassificationUnavailableError:
            return []

        if not base_results:
            return base_results
        if not bool(getattr(settings.classification, "personalized_rerank_enabled", False)):
            return base_results
        if not camera_name:
            return base_results

        effective_model_id = str(model_id or self._resolve_active_model_id()).strip()
        if not effective_model_id:
            return base_results

        try:
            return await personalization_service.rerank(
                camera_name=camera_name,
                model_id=effective_model_id,
                results=base_results,
            )
        except Exception as exc:
            log.warning(
                "Personalized rerank failed; using base classifier scores",
                camera_name=camera_name,
                model_id=effective_model_id,
                error=str(exc),
            )
            return base_results

    async def classify_async_live(
        self,
        image: Image.Image,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
        queue_timeout_seconds: float | None = None,
    ) -> list[dict]:
        """Live image-classification path with bounded admission and accurate in-flight tracking."""
        normalized_input_context = _normalize_classification_input_context(input_context)
        base_results = await self._run_live_image_inference(
            self.classify,
            image,
            camera_name,
            model_id,
            normalized_input_context,
            queue_timeout_seconds=queue_timeout_seconds,
        )

        if not base_results:
            return base_results
        if not bool(getattr(settings.classification, "personalized_rerank_enabled", False)):
            return base_results
        if not camera_name:
            return base_results

        effective_model_id = str(model_id or self._resolve_active_model_id()).strip()
        if not effective_model_id:
            return base_results

        try:
            return await personalization_service.rerank(
                camera_name=camera_name,
                model_id=effective_model_id,
                results=base_results,
            )
        except Exception as exc:
            log.warning(
                "Live personalized rerank failed; using base classifier scores",
                camera_name=camera_name,
                model_id=effective_model_id,
                error=str(exc),
            )
            return base_results

    async def classify_async_background(
        self,
        image: Image.Image,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
        queue_timeout_seconds: float | None = None,
    ) -> list[dict]:
        """Background image-classification path using low-priority workers.

        Intended for backfill/batch-style work so live MQTT classification
        remains responsive under sustained load.
        """
        normalized_input_context = _normalize_classification_input_context(input_context)
        context = self._classification_admission_context(model_id=model_id)
        if self._image_execution_mode == "subprocess":
            base_results = await self._run_coordinated_supervised_inference(
                "background",
                "background_image_inference",
                image,
                camera_name,
                model_id,
                normalized_input_context,
                queue_timeout_seconds=queue_timeout_seconds,
                context=context,
            )
        else:
            base_results = await self._run_coordinated_executor_inference(
                "background",
                self._background_image_executor,
                "background_image_inference",
                self.classify,
                image,
                camera_name,
                model_id,
                normalized_input_context,
                queue_timeout_seconds=queue_timeout_seconds,
                context=context,
            )

        if not base_results:
            return base_results
        if not bool(getattr(settings.classification, "personalized_rerank_enabled", False)):
            return base_results
        if not camera_name:
            return base_results

        effective_model_id = str(model_id or self._resolve_active_model_id()).strip()
        if not effective_model_id:
            return base_results

        try:
            return await personalization_service.rerank(
                camera_name=camera_name,
                model_id=effective_model_id,
                results=base_results,
            )
        except Exception as exc:
            log.warning(
                "Background personalized rerank failed; using base classifier scores",
                camera_name=camera_name,
                model_id=effective_model_id,
                error=str(exc),
            )
            return base_results

    def classify_wildlife(self, image: Image.Image, input_context: Any | None = None) -> list[dict]:
        """Classify an image using the wildlife model."""
        wildlife = self._get_wildlife_model()
        return _invoke_model_classify(wildlife, image, input_context=input_context)

    async def classify_wildlife_async(self, image: Image.Image, input_context: Any | None = None) -> list[dict]:
        """Async wrapper for wildlife classification."""
        return await self._run_coordinated_executor_inference(
            "background",
            self._image_executor,
            "wildlife_image_inference",
            self.classify_wildlife,
            image,
            input_context,
        )

    def get_wildlife_labels(self) -> list[str]:
        wildlife = self._get_wildlife_model()
        return wildlife.labels

    def reload_wildlife_model(self):
        if "wildlife" in self._models:
            old_model = self._models.pop("wildlife")
            if hasattr(old_model, "cleanup"):
                old_model.cleanup()
            del old_model
            log.info("Cleared cached wildlife model instance")
        try:
            self._get_wildlife_model()
            log.info("Reloaded wildlife model")
        except Exception as e:
            log.error("Failed to reload wildlife model", error=str(e))

    async def shutdown(self) -> None:
        self._classification_admission.close_sync()
        if self._classifier_supervisor is not None:
            # Defensive check for mocks/fakes in tests that might not implement shutdown
            shutdown_fn = getattr(self._classifier_supervisor, "shutdown", None)
            if callable(shutdown_fn):
                result = shutdown_fn()
                if inspect.isawaitable(result):
                    await result
        if self._video_supervisor is not None and self._video_supervisor is not self._classifier_supervisor:
            shutdown_fn = getattr(self._video_supervisor, "shutdown", None)
            if callable(shutdown_fn):
                result = shutdown_fn()
                if inspect.isawaitable(result):
                    await result
        for executor in (
            self._image_executor,
            self._live_image_executor,
            self._background_image_executor,
            self._video_executor,
        ):
            executor.shutdown(wait=False, cancel_futures=True)

    def classify_video(
        self,
        video_path: str,
        stride: int = 5,
        max_frames: Optional[int] = None,
        progress_callback=None,
        input_context: Any | None = None,
    ) -> list[dict]:
        """
        Classify a video clip using Temporal Ensemble (Soft Voting) with Normal Distribution sampling.

        Args:
            video_path: Path to the video file.
            stride: Legacy parameter, no longer used for sampling but kept for API compatibility.
            max_frames: Maximum number of frames to process.
            progress_callback: Optional callback function.

        Returns:
            List of classifications with aggregated scores.
        """
        normalized_input_context = _normalize_classification_input_context(input_context)
        if max_frames is None:
            max_frames = settings.classification.video_classification_frames

        bird_model = self._models.get("bird")
        if not bird_model or not bird_model.loaded:
            log.error("Bird model not loaded for video classification")
            return []

        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                log.error(f"Could not open video file: {video_path}")
                return []

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            if total_frames <= 0:
                log.warning("Video has no frames", path=video_path)
                return []

            log.info("Analyzing video", frames=total_frames, fps=fps, max_samples=max_frames)

            sample_count = min(max_frames, total_frames)
            clip_variant = str(self._input_context_extra(normalized_input_context, "clip_variant") or "event")
            frame_indices = _select_video_frame_indices(
                total_frames=total_frames,
                sample_count=sample_count,
                clip_variant=clip_variant,
            )

            if bool(normalized_input_context.is_cropped):
                supplied_source = str(
                    self._input_context_extra(normalized_input_context, "input_source") or "provided_crop"
                )
                expected_input_sources = [supplied_source]
            else:
                expected_input_sources = ["full_frame"]
                has_frigate_hint = any(
                    isinstance(self._input_context_extra(normalized_input_context, key), (list, tuple))
                    and len(self._input_context_extra(normalized_input_context, key)) == 4
                    for key in ("frigate_box", "frigate_region")
                )
                if has_frigate_hint:
                    expected_input_sources.append("frigate_hint_crop")
                if self._bird_crop_detector_available():
                    expected_input_sources.append("model_crop")

            scores_by_input_source: dict[str, list[np.ndarray]] = {source: [] for source in expected_input_sources}
            offsets_by_input_source: dict[str, list[float | None]] = {source: [] for source in expected_input_sources}
            processed_frame_count = 0
            any_valid_scores = False
            skipped_unknown_frame_count = 0

            active_model_id = None
            try:
                from app.services.model_manager import model_manager, REMOTE_REGISTRY

                active_model_id = model_manager.active_model_id
                model_meta = next((m for m in REMOTE_REGISTRY if m["id"] == active_model_id), None)
            except Exception:
                model_meta = None
            model_name = model_meta["name"] if model_meta else None
            if not model_name and hasattr(bird_model, "model_path"):
                model_name = os.path.basename(bird_model.model_path)
            if not model_name:
                model_name = "bird"

            last_top_label = "Analyzing..."
            last_top_score = 0.0
            last_frame_thumb = None

            for i, idx in enumerate(frame_indices, 1):
                # Seek to frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                frame_offset_sec = float(idx) / fps if fps > 0 else None
                if not ret:
                    if progress_callback:
                        try:
                            progress_callback(
                                current_frame=i,
                                total_frames=len(frame_indices),
                                frame_score=last_top_score,
                                top_label=last_top_label,
                                frame_thumb=last_frame_thumb,
                                frame_index=int(idx) + 1,
                                clip_total=int(total_frames),
                                model_name=model_name,
                                frame_offset_seconds=frame_offset_sec,
                            )
                        except Exception:
                            pass
                    continue

                # Convert BGR (OpenCV) to RGB (PIL)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                processed_frame_count += 1

                frame_input_context = self._video_frame_input_context(
                    normalized_input_context,
                    frame_offset_seconds=frame_offset_sec,
                )

                candidate_scores: dict[str, np.ndarray] = {}
                candidate_images: dict[str, Image.Image] = {}
                for input_source, candidate_image in self._video_frame_candidates(
                    image,
                    input_context=frame_input_context,
                ):
                    if input_source not in scores_by_input_source:
                        expected_input_sources.append(input_source)
                        scores_by_input_source[input_source] = []
                        offsets_by_input_source[input_source] = []
                    candidate_context = dict(frame_input_context.model_dump())
                    candidate_context.update(
                        {
                            "is_cropped": input_source != "full_frame",
                            "input_source": input_source,
                            "disable_crop_resolution": True,
                        }
                    )
                    scores, active_bird_model = self._classify_raw_with_runtime_recovery(
                        candidate_image,
                        input_context=_normalize_classification_input_context(candidate_context),
                    )
                    if active_bird_model is not None:
                        bird_model = active_bird_model
                    if len(scores) > 0:
                        any_valid_scores = True
                        candidate_scores[input_source] = scores
                        candidate_images[input_source] = candidate_image

                labels = list(getattr(bird_model, "labels", []) or [])
                class_count = len(labels)
                for input_source, scores in candidate_scores.items():
                    if len(scores) == class_count:
                        scores_by_input_source[input_source].append(scores)
                        offsets_by_input_source[input_source].append(frame_offset_sec)

                strongest_frame_candidate: tuple[float, int, str, Image.Image] | None = None
                for input_source, scores in candidate_scores.items():
                    if len(scores) == 0:
                        continue
                    top_idx = int(np.argmax(scores))
                    top_score = float(scores[top_idx])
                    candidate = (top_score, top_idx, input_source, candidate_images[input_source])
                    if strongest_frame_candidate is None or candidate[0] > strongest_frame_candidate[0]:
                        strongest_frame_candidate = candidate

                if strongest_frame_candidate is not None:
                    last_top_score, top_idx, _frame_input_source, strongest_image = strongest_frame_candidate
                    last_top_label = (
                        normalize_classifier_label(labels[top_idx]) if top_idx < len(labels) else f"Class {top_idx}"
                    )
                    if should_hide_species_label(last_top_label):
                        skipped_unknown_frame_count += 1

                    try:
                        from io import BytesIO
                        import base64

                        thumb = strongest_image.copy()
                        thumb.thumbnail((96, 72))
                        buf = BytesIO()
                        thumb.save(buf, format="JPEG", quality=60)
                        last_frame_thumb = base64.b64encode(buf.getvalue()).decode("ascii")
                    except Exception as e:
                        log.debug("Failed to encode frame thumbnail", error=str(e))

                # Call progress callback for every sampled frame
                if progress_callback:
                    try:
                        progress_callback(
                            current_frame=i,
                            total_frames=len(frame_indices),
                            frame_score=last_top_score,
                            top_label=last_top_label,
                            frame_thumb=last_frame_thumb,
                            frame_index=int(idx) + 1,
                            clip_total=int(total_frames),
                            model_name=model_name,
                            frame_offset_seconds=frame_offset_sec,
                        )
                    except Exception as exc:
                        log.warning(
                            "Video classification progress callback failed; continuing",
                            error=str(exc),
                            frame_index=int(idx) + 1,
                            total_frames=len(frame_indices),
                        )

            if not any_valid_scores:
                log.warning("No frames processed from video")
                return []

            labels = list(getattr(bird_model, "labels", []) or [])
            excluded_class_indices = {
                class_index
                for class_index, label in enumerate(labels)
                if should_hide_species_label(normalize_classifier_label(label))
            }
            recommended_threshold = float((model_meta or {}).get("recommended_threshold") or 0.0)
            minimum_frame_score = max(
                float(getattr(settings.classification, "min_confidence", 0.0) or 0.0),
                recommended_threshold,
            )
            source_assessments = {
                input_source: assess_temporal_consensus(
                    source_scores,
                    minimum_frame_score=minimum_frame_score,
                    excluded_class_indices=excluded_class_indices,
                    minimum_evaluated_frames=3,
                    frame_offsets_seconds=offsets_by_input_source.get(input_source),
                )
                for input_source, source_scores in scores_by_input_source.items()
            }
            source_consensuses = [
                SourceTemporalConsensus(input_source=input_source, consensus=assessment.consensus)
                for input_source, assessment in source_assessments.items()
            ]
            selected_source_consensus = select_temporal_source_consensus(source_consensuses)
            consensus_diagnostics = {
                input_source: {
                    "reason": assessment.reason,
                    "evaluated_frames": assessment.evaluated_frame_count,
                    "independent_frames": assessment.independent_frame_count,
                    "confident_frames": assessment.confident_frame_count,
                    "required_supporting_frames": assessment.required_supporting_frames,
                    "confident_coverage_ratio": round(
                        assessment.confident_frame_count / max(1, assessment.independent_frame_count),
                        4,
                    ),
                    "top_candidates": [
                        {
                            "label": (
                                normalize_classifier_label(labels[evidence.class_index])
                                if evidence.class_index < len(labels)
                                else f"Class {evidence.class_index}"
                            ),
                            "supporting_frames": evidence.supporting_frame_count,
                            "support_ratio": round(evidence.support_ratio, 4),
                            "median_score": round(evidence.score, 4),
                            "pooled_frames": evidence.pooled_frame_count,
                        }
                        for evidence in assessment.ranked_classes[:3]
                    ],
                    "top_observations": [
                        {
                            "label": (
                                normalize_classifier_label(labels[evidence.class_index])
                                if evidence.class_index < len(labels)
                                else f"Class {evidence.class_index}"
                            ),
                            "supporting_frames": evidence.supporting_frame_count,
                            "support_ratio": round(evidence.support_ratio, 4),
                            "median_score": round(evidence.score, 4),
                            "pooled_frames": evidence.pooled_frame_count,
                        }
                        for evidence in assessment.ranked_observations[:3]
                    ],
                }
                for input_source, assessment in source_assessments.items()
            }
            diagnostic_payload = {
                "version": 3,
                "outcome": "accepted" if selected_source_consensus is not None else "abstained",
                "aggregation": "sparse_top_k_median",
                "maximum_pooled_frames": VIDEO_SPARSE_POOL_MAX_FRAMES,
                "minimum_frame_separation_seconds": VIDEO_MIN_FRAME_SEPARATION_SECONDS,
                "sampled_frames": len(frame_indices),
                "processed_frames": processed_frame_count,
                "minimum_frame_score": round(minimum_frame_score, 4),
                "sources": consensus_diagnostics,
                "reason": (
                    "accepted"
                    if selected_source_consensus is not None
                    else (
                        "source_disagreement"
                        if len(
                            {item.consensus.winner_index for item in source_consensuses if item.consensus is not None}
                        )
                        > 1
                        else "no_source_consensus"
                    )
                ),
            }
            include_diagnostics = bool(self._input_context_extra(normalized_input_context, "include_video_diagnostics"))
            if selected_source_consensus is None or selected_source_consensus.consensus is None:
                log.info(
                    "Video classification abstained because inputs lacked consensus or disagreed",
                    processed_frames=processed_frame_count,
                    minimum_frame_score=minimum_frame_score,
                    skipped_unknown_frames=skipped_unknown_frame_count,
                    input_consensus=consensus_diagnostics,
                )
                return [{"_video_diagnostics": diagnostic_payload}] if include_diagnostics else []

            input_source = selected_source_consensus.input_source
            consensus = selected_source_consensus.consensus
            top_evidence = consensus.ranked_classes[:5]

            classifications = []
            for evidence in top_evidence:
                i = evidence.class_index
                score = evidence.score
                label = normalize_classifier_label(labels[i]) if i < len(labels) else f"Class {i}"
                classifications.append(
                    {
                        "index": int(i),
                        "score": score,
                        "label": label,
                        "inference_provider": str(self._active_inference_provider or ""),
                        "inference_backend": str(self._inference_backend or ""),
                        "model_id": str(active_model_id or ""),
                        "model_name": model_name,
                        "input_source": input_source,
                        "input_is_cropped": input_source != "full_frame",
                        "temporal_supporting_frames": evidence.supporting_frame_count,
                        "temporal_evaluated_frames": consensus.evaluated_frame_count,
                        "temporal_independent_frames": consensus.independent_frame_count,
                        "temporal_required_frames": consensus.required_supporting_frames,
                    }
                )

            if classifications:
                top_score = float(classifications[0]["score"])
                class_count = int(len(labels))
                uniform_baseline = (1.0 / class_count) if class_count > 0 else 1.0
                degenerate_cutoff = uniform_baseline * CLASSIFIER_VIDEO_UNIFORM_SCORE_MULTIPLIER
                if (not np.isfinite(top_score)) or top_score <= degenerate_cutoff:
                    log.warning(
                        "Video classification produced degenerate confidence distribution",
                        top_score=top_score,
                        class_count=class_count,
                        uniform_baseline=uniform_baseline,
                        degenerate_cutoff=degenerate_cutoff,
                        top_label=classifications[0].get("label"),
                    )
                    diagnostic_payload["outcome"] = "abstained"
                    diagnostic_payload["reason"] = "degenerate_output"
                    return [{"_video_diagnostics": diagnostic_payload}] if include_diagnostics else []

            log.info(
                f"Video classification complete (consensus). Analyzed {processed_frame_count} frames.",
                top_result=classifications[0]["label"] if classifications else None,
                top_score=round(classifications[0]["score"], 3),
                input_source=input_source,
                supporting_frames=consensus.supporting_frame_count,
                evaluated_frames=consensus.evaluated_frame_count,
                independent_frames=consensus.independent_frame_count,
                required_frames=consensus.required_supporting_frames,
                skipped_unknown_frames=skipped_unknown_frame_count,
                input_consensus=consensus_diagnostics,
            )

            if include_diagnostics:
                classifications.append({"_video_diagnostics": diagnostic_payload})
            return classifications

        except Exception as e:
            log.error("Error during video classification", error=str(e))
            raise
        finally:
            # Always release video capture to prevent memory leaks
            if cap is not None:
                cap.release()

    async def classify_video_async(
        self,
        video_path: str,
        stride: int = 5,
        max_frames: Optional[int] = None,
        progress_callback=None,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
        propagate_worker_failure: bool = False,
        diagnostics_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> list[dict]:
        """Async wrapper for video classification."""
        normalized_input_context = _normalize_classification_input_context(input_context)
        if max_frames is None:
            max_frames = settings.classification.video_classification_frames

        if self._video_supervisor is not None:
            work_id = f"video-{time.monotonic_ns()}"
            lease_token = 1
            try:
                base_results = await self._video_supervisor.classify_video(
                    work_id=work_id,
                    lease_token=lease_token,
                    video_path=video_path,
                    stride=stride,
                    max_frames=max_frames,
                    progress_callback=progress_callback,
                    input_context=dict(normalized_input_context.model_dump()),
                )
            except asyncio.CancelledError:
                # ``wait_for`` cancellation must kill the native worker, not
                # merely abandon the Future while OpenVINO continues burning
                # CPU/GPU in an unreachable process.
                with contextlib.suppress(Exception):
                    await self._video_supervisor.abort_request(
                        priority="video",
                        work_id=work_id,
                        lease_token=lease_token,
                        reason="video_request_cancelled",
                    )
                raise
            except (
                ClassifierWorkerCircuitOpenError,
                ClassifierWorkerHeartbeatTimeoutError,
                ClassifierWorkerDeadlineExceededError,
                ClassifierWorkerStartupTimeoutError,
                ClassifierWorkerExitedError,
            ) as exc:
                log.warning("Supervised video classification failed", error=str(exc), video_path=video_path)
                if propagate_worker_failure:
                    if isinstance(exc, ClassifierWorkerCircuitOpenError):
                        raise VideoClassificationWorkerError("video_worker_circuit_open") from exc
                    if isinstance(exc, ClassifierWorkerHeartbeatTimeoutError):
                        raise VideoClassificationWorkerError("video_worker_heartbeat_timeout") from exc
                    if isinstance(exc, ClassifierWorkerDeadlineExceededError):
                        raise VideoClassificationWorkerError("video_worker_deadline_exceeded") from exc
                    if isinstance(exc, ClassifierWorkerStartupTimeoutError):
                        raise VideoClassificationWorkerError("video_worker_startup_timeout") from exc
                    raise VideoClassificationWorkerError("video_worker_unavailable") from exc
                return []
        else:
            loop = asyncio.get_running_loop()

            # Wrap the callback to make it thread-safe
            if progress_callback:

                def sync_callback(
                    current_frame,
                    total_frames,
                    frame_score,
                    top_label,
                    frame_thumb=None,
                    frame_index=None,
                    clip_total=None,
                    model_name=None,
                    frame_offset_seconds=None,
                ):
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            progress_callback(
                                current_frame,
                                total_frames,
                                frame_score,
                                top_label,
                                frame_thumb,
                                frame_index,
                                clip_total,
                                model_name,
                                frame_offset_seconds,
                            ),
                            loop,
                        )
                        try:
                            future.result(timeout=1.0)
                        except TimeoutError:
                            log.warning("Progress callback timed out after 1s", frame=current_frame, total=total_frames)
                        except Exception as e:
                            log.error("Progress callback failed", error=str(e), frame=current_frame, total=total_frames)
                    except Exception as e:
                        log.error("Failed to schedule progress callback", error=str(e))

                base_results = await loop.run_in_executor(
                    self._video_executor,
                    self.classify_video,
                    video_path,
                    stride,
                    max_frames,
                    sync_callback,
                    normalized_input_context,
                )
            else:
                base_results = await loop.run_in_executor(
                    self._video_executor,
                    self.classify_video,
                    video_path,
                    stride,
                    max_frames,
                    None,
                    normalized_input_context,
                )

        diagnostics = next(
            (
                item.get("_video_diagnostics")
                for item in base_results
                if isinstance(item, dict) and isinstance(item.get("_video_diagnostics"), dict)
            ),
            None,
        )
        base_results = [
            item
            for item in base_results
            if not (isinstance(item, dict) and isinstance(item.get("_video_diagnostics"), dict))
        ]
        if diagnostics_callback is not None and diagnostics is not None:
            callback_result = diagnostics_callback(diagnostics)
            if inspect.isawaitable(callback_result):
                await callback_result

        if not base_results:
            return base_results
        if not bool(getattr(settings.classification, "personalized_rerank_enabled", False)):
            return base_results
        if not camera_name:
            return base_results

        effective_model_id = str(model_id or self._resolve_active_model_id()).strip()
        if not effective_model_id:
            return base_results

        try:
            return await personalization_service.rerank(
                camera_name=camera_name,
                model_id=effective_model_id,
                results=base_results,
            )
        except Exception as exc:
            log.warning(
                "Personalized rerank failed for video classification; using base scores",
                camera_name=camera_name,
                model_id=effective_model_id,
                error=str(exc),
            )
            return base_results
