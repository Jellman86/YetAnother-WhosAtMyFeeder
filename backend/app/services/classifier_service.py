import structlog
import numpy as np
import os
import cv2
import asyncio
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

# TFLite runtime
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        tflite = None

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
    if not ONNX_AVAILABLE or ort is None:
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
from app.utils.classifier_labels import (  # noqa: E402
    build_grouped_classifier_labels,
    normalize_classifier_label,
    normalize_classifier_labels,
)

log = structlog.get_logger()

SUPPORTED_INFERENCE_PROVIDERS = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu"}
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
CLASSIFIER_VIDEO_UNIFORM_SCORE_MULTIPLIER = max(
    1.0,
    float(os.getenv("CLASSIFIER_VIDEO_UNIFORM_SCORE_MULTIPLIER", "1.25")),
)
LEGACY_CLASSIFIER_STRICT_NON_FINITE_OUTPUT = os.getenv("CLASSIFIER_STRICT_NON_FINITE_OUTPUT", "true").strip().lower() != "false"


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

    def _linspace_indices(start: int, end: int, count: int) -> list[int]:
        if count <= 0:
            return []
        if count == 1:
            return [int(round((start + end) / 2))]
        return [int(round(value)) for value in np.linspace(start, end, count)]

    center_start = int(round(max_index * 0.25))
    center_end = int(round(max_index * 0.75))

    candidate_indices: list[int] = []
    if normalized_variant == "recording":
        uniform_count = max(2, int(math.ceil(sample_count * 0.7)))
        uniform_count = min(uniform_count, sample_count)
        center_count = max(0, sample_count - uniform_count)
        candidate_indices.extend(_linspace_indices(0, max_index, uniform_count))
        candidate_indices.extend(_linspace_indices(center_start, center_end, center_count))
    else:
        edge_count = min(2, sample_count)
        center_count = max(0, sample_count - edge_count)
        candidate_indices.extend([0, max_index][:edge_count])
        candidate_indices.extend(_linspace_indices(center_start, center_end, center_count))

    deduped: list[int] = []
    seen: set[int] = set()
    for idx in sorted(max(0, min(max_index, int(value))) for value in candidate_indices):
        if idx in seen:
            continue
        seen.add(idx)
        deduped.append(idx)

    if len(deduped) < sample_count:
        for idx in _linspace_indices(0, max_index, total_frames):
            idx = max(0, min(max_index, int(idx)))
            if idx in seen:
                continue
            seen.add(idx)
            deduped.append(idx)
            if len(deduped) >= sample_count:
                break

    return np.array(sorted(deduped[:sample_count]), dtype=int)


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
        if "unexpected keyword argument 'input_context'" not in error_text and 'unexpected keyword argument "input_context"' not in error_text:
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
            total_elements=logits.size
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
    allowed = {
        _normalize_inference_provider(item)
        for item in (spec or {}).get("supported_inference_providers") or []
    }
    allowed.discard("auto")
    return not allowed or normalized in allowed


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
        "openvino_devices": [],
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
                caps["cuda_provider_installed"]
                and caps["cuda_hardware_available"]
                and not caps["cuda_probe_error"]
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


def _resolve_inference_selection(
    requested_provider: Optional[str],
    caps: dict,
    supported_providers: Optional[list[str]] = None,
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
        return _ort_cpu(_reason_with_constraint(
            f"CUDA requested but {_cuda_unavailable_reason(caps)}",
            "cuda",
            "CUDA",
        ))

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

    # auto: prefer Intel GPU, then CUDA, then CPU
    if caps.get("openvino_available") and caps.get("intel_gpu_available") and _provider_allowed("intel_gpu"):
        return {
            "requested_provider": requested,
            "active_provider": "intel_gpu",
            "backend": "openvino",
            "ort_providers": [],
            "openvino_device": "GPU",
            "fallback_reason": None,
        }
    if caps.get("ort_available") and caps.get("cuda_available") and _provider_allowed("cuda"):
        return {
            "requested_provider": requested,
            "active_provider": "cuda",
            "backend": "onnxruntime",
            "ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "openvino_device": None,
            "fallback_reason": None,
        }
    if caps.get("openvino_available") and caps.get("intel_cpu_available") and _provider_allowed("intel_cpu"):
        fallback_reason = None
        if allowed and "intel_gpu" not in allowed:
            fallback_reason = "Active model artifact does not support Intel GPU"
        elif caps.get("cuda_probe_error"):
            fallback_reason = _cuda_unavailable_reason(caps)
        return {
            "requested_provider": requested,
            "active_provider": "intel_cpu",
            "backend": "openvino",
            "ort_providers": [],
            "openvino_device": "CPU",
            "fallback_reason": fallback_reason,
        }
    fallback_reason = None
    if allowed and "intel_gpu" not in allowed:
        fallback_reason = "Active model artifact does not support Intel GPU"
    elif caps.get("cuda_probe_error"):
        fallback_reason = _cuda_unavailable_reason(caps)
    return _ort_cpu(fallback_reason)


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
        return (
            f"{prefix} (unsupported ONNX ops: {', '.join(unsupported_ops)}); "
            f"using {fallback_target}."
        )

    raw = (error_text or "").strip()
    if raw.lower().startswith("failed to load openvino model:"):
        raw = raw.split(":", 1)[1].strip()
    snippet = " ".join(raw.split()) if raw else "unknown compile error"
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."
    return f"{prefix}: {snippet}; using {fallback_target}."

# Global singleton instance
_classifier_instance: Optional['ClassifierService'] = None
_classifier_lock = threading.Lock()


def get_classifier() -> 'ClassifierService':
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


class ModelInstance:
    """Represents a loaded TFLite model with its labels."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
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

            # Load labels first
            if os.path.exists(self.labels_path):
                try:
                    with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                        self.labels = normalize_classifier_labels(line.strip() for line in f.readlines() if line.strip())
                    strategy = str(self.label_grouping.get("strategy") or "").strip()
                    if strategy:
                        self.grouped_labels = build_grouped_classifier_labels(self.labels, strategy=strategy)
                    log.info(f"Loaded {len(self.labels)} labels for {self.name}")
                except Exception as e:
                    log.error(f"Failed to load labels for {self.name}", error=str(e))

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
        input_shape = input_details['shape']

        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300  # Default fallback

        # Preprocess image
        input_data = self._preprocess_image(image, target_width, target_height)

        # Normalize based on model input type
        if input_details['dtype'] == np.float32:
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
        elif input_details['dtype'] == np.uint8:
            input_data = input_data.astype(np.uint8)

        # Add batch dimension
        input_data = np.expand_dims(input_data, axis=0)

        # Run inference protected by lock
        with self._lock:
            self.interpreter.set_tensor(input_details['index'], input_data)
            self.interpreter.invoke()

            # Get output
            output_details = self.output_details[0]
            output_data = self.interpreter.get_tensor(output_details['index'])

        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize if needed
        if output_details['dtype'] == np.uint8:
            quant_params = output_details.get('quantization_parameters', {})
            scales = quant_params.get('scales', None)
            zero_points = quant_params.get('zero_points', None)

            if scales is not None and len(scales) > 0:
                scale = scales[0]
                zero_point = zero_points[0] if zero_points is not None and len(zero_points) > 0 else 0
                results = (results - zero_point) * scale
            else:
                results = results / 255.0

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
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
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

        # Load labels first
        if os.path.exists(self.labels_path):
            try:
                with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.labels = normalize_classifier_labels(line.strip() for line in f.readlines() if line.strip())
                strategy = str(self.label_grouping.get("strategy") or "").strip()
                if strategy:
                    self.grouped_labels = build_grouped_classifier_labels(self.labels, strategy=strategy)
                log.info(f"Loaded {len(self.labels)} labels for ONNX model {self.name}")
            except Exception as e:
                log.error(f"Failed to load labels for {self.name}", error=str(e))

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
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # HWC -> CHW (ONNX expects NCHW)
        return arr[np.newaxis, ...].astype(np.float32)  # Add batch dimension

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply softmax to convert logits to probabilities."""
        return _safe_softmax(x, context=f"{self.name}:onnx")

    def classify(self, image: Image.Image, top_k: int = 5, input_context: Any | None = None) -> list[dict]:
        """Classify an image using this ONNX model."""
        if not self.loaded or not self.session:
            log.warning(f"{self.name} ONNX model not loaded, cannot classify")
            return []

        try:
            input_tensor = self._preprocess(image)

            # Get input name from model
            input_name = self.session.get_inputs()[0].name

            # Run inference
            with self._lock:
                outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]

            # Apply softmax to get probabilities
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="onnxruntime",
                    provider=(self.ort_providers[0] if self.ort_providers else "cpu"),
                    detail=f"{self.name} inference produced no finite probabilities",
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
            log.error(f"ONNX inference failed for {self.name}", error=str(e))
            return []

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.session:
            return np.array([])

        try:
            input_tensor = self._preprocess(image)
            input_name = self.session.get_inputs()[0].name
            with self._lock:
                outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="onnxruntime",
                    provider=(self.ort_providers[0] if self.ort_providers else "cpu"),
                    detail=f"{self.name} inference produced no finite probabilities",
                )
            return probs
        except InvalidInferenceOutputError:
            raise
        except Exception as e:
            log.error("ONNX raw classification failed", error=str(e))
            return np.array([])

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
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
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

        if os.path.exists(self.labels_path):
            try:
                with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.labels = normalize_classifier_labels(line.strip() for line in f.readlines() if line.strip())
                strategy = str(self.label_grouping.get("strategy") or "").strip()
                if strategy:
                    self.grouped_labels = build_grouped_classifier_labels(self.labels, strategy=strategy)
                log.info(f"Loaded {len(self.labels)} labels for OpenVINO model {self.name}")
            except Exception as e:
                log.error(f"Failed to load labels for {self.name}", error=str(e))

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
            config = {
                "PERFORMANCE_HINT": "LATENCY",
                "NUM_STREAMS": "1"
            }
            if self.device_name == "GPU" or str(self.device_name).startswith("GPU."):
                config["INFERENCE_PRECISION_HINT"] = "f32"
                config.update(_openvino_gpu_optional_compile_properties())
                # Some Intel GPU drivers crash with clWaitForEvents -14 when the model
                # has a dynamic batch dimension (e.g. [?,3,224,224]).  Reshaping to a
                # fixed batch=1 before compile avoids this without affecting accuracy.
                try:
                    partial = model.inputs[0].get_partial_shape()
                    if partial.rank.is_static and partial[0].is_dynamic:
                        static_shape = [1] + [partial[d].get_length() for d in range(1, partial.rank.get_length())]
                        model.reshape(static_shape)
                except Exception:
                    pass  # Non-fatal; proceed with original dynamic shape

            self.compiled_model = self.core.compile_model(model, self.device_name, config=config)
            self.input_name = self.compiled_model.inputs[0].get_any_name()
            if self._startup_self_test_enabled and (
                self.device_name == "GPU" or str(self.device_name).startswith("GPU.")
            ):
                self._run_gpu_startup_self_test()
            self.loaded = True
            self.error = None
            log.info("OpenVINO model loaded successfully", model=self.name, device=self.device_name, input_size=self.input_size)
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
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # NCHW
        return arr[np.newaxis, ...].astype(np.float32)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        return _safe_softmax(x, context=f"{self.name}:openvino")

    def _infer_output_tensor(self, image: Image.Image) -> np.ndarray:
        if self.compiled_model is None or self.input_name is None:
            return np.array([])

        input_tensor = self._preprocess(image)
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
        configured_mode = str(
            getattr(settings.classification, "image_execution_mode", "in_process") or "in_process"
        ).strip().lower()
        self._image_execution_mode = "in_process" if self._worker_process_mode else configured_mode
        self._classifier_supervisor = supervisor
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
            background_admission_capacity = int(
                getattr(settings.classification, "background_worker_count", 1) or 1
            )
        self._image_executor = ThreadPoolExecutor(max_workers=image_workers, thread_name_prefix="ml_image_worker")
        self._live_image_executor = ThreadPoolExecutor(max_workers=image_workers, thread_name_prefix="ml_live_image_worker")
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
        if self._classifier_supervisor is None and self._image_execution_mode == "subprocess":
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
            self._classifier_supervisor = ClassifierSupervisor(
                live_worker_count=int(getattr(settings.classification, "live_worker_count", image_workers) or image_workers),
                background_worker_count=int(getattr(settings.classification, "background_worker_count", 1) or 1),
                video_worker_count=video_workers,
                heartbeat_timeout_seconds=float(getattr(settings.classification, "worker_heartbeat_timeout_seconds", 5.0) or 5.0),
                hard_deadline_seconds=image_hard_deadline_seconds,
                background_hard_deadline_seconds=background_hard_deadline_seconds,
                video_hard_deadline_seconds=max(image_hard_deadline_seconds, video_timeout_seconds + 15.0),
                worker_ready_timeout_seconds=float(getattr(settings.classification, "worker_ready_timeout_seconds", 20.0) or 20.0),
                video_worker_ready_timeout_seconds=max(
                    float(getattr(settings.classification, "worker_ready_timeout_seconds", 20.0) or 20.0),
                    min(60.0, max(30.0, video_timeout_seconds / 2.0)),
                ),
            )
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
        self._runtime_invalid_output_failures = 0
        self._runtime_fallback_recoveries = 0
        self._runtime_gpu_retries = 0
        self._runtime_gpu_restore_attempts = 0
        self._runtime_gpu_restore_successes = 0
        self._runtime_gpu_restore_failures = 0
        self._gpu_invalid_retry_remaining = CLASSIFIER_GPU_INVALID_RETRY_LIMIT
        self._gpu_restore_not_before_monotonic: float = 0.0
        self._last_runtime_recovery: Optional[dict[str, Any]] = None
        self._bird_model_artifact_metadata: dict[str, Any] = {}
        self._model_config_warnings: list[str] = []
        self._bird_model_compatibility: dict[str, Any] = {}
        self._accel_caps_ttl_seconds = CLASSIFIER_ACCEL_PROBE_TTL_SECONDS
        self._accel_caps_last_refreshed_monotonic: float | None = None
        self._accel_caps = self._refresh_accel_caps(force=True)
        if self._worker_process_mode or self._image_execution_mode != "subprocess":
            self._init_bird_model()

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
        from app.services.model_manager import model_manager

        spec = dict(model_manager.get_active_model_spec() or {})
        model_path = str(spec.get("model_path") or "")
        labels_path = str(spec.get("labels_path") or "")
        input_size = int(spec.get("input_size") or 224)
        preprocessing = spec.get("preprocessing")
        label_grouping = spec.get("label_grouping")
        supported_inference_providers = list(spec.get("supported_inference_providers") or [])
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
            "model_path": model_path,
            "labels_path": labels_path,
            "input_size": input_size,
            "preprocessing": preprocessing,
            "label_grouping": dict(label_grouping or {}),
            "runtime": runtime,
            "resolved_region": spec.get("resolved_region"),
            "supported_inference_providers": supported_inference_providers,
            "model_config_warnings": model_config_warnings,
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
        if isinstance(bird, OpenVINOModelInstance):
            return bird
        return None

    def _openvino_runtime_snapshot(
        self,
        *,
        active_backend: str,
        active_provider: str,
        runtime_recovery: dict[str, Any] | None,
    ) -> dict[str, Any]:
        active_model = self._active_openvino_model()
        snapshot = {
            "selected_provider": _normalize_inference_provider(getattr(settings.classification, "inference_provider", "auto")),
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
            "last_runtime_recovery": runtime_recovery,
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
            device_name = "GPU" if provider == "intel_gpu" else "CPU"
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
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if provider == "cuda"
                else ["CPUExecutionProvider"]
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

    def _runtime_fallback_targets(self) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []

        def _append(target_backend: str, target_provider: str) -> None:
            target = (target_backend, target_provider)
            if (
                target not in targets
                and not (
                    target_backend == self._inference_backend
                    and target_provider == self._active_inference_provider
                )
            ):
                targets.append(target)

        if self._inference_backend == "openvino":
            if self._active_inference_provider == "intel_gpu" and self._accel_caps.get("intel_cpu_available"):
                _append("openvino", "intel_cpu")
            if self._accel_caps.get("ort_available"):
                _append("onnxruntime", "cpu")
            _append("tflite", "tflite")
            return targets

        if self._inference_backend == "onnxruntime":
            if self._active_inference_provider != "cpu" and self._accel_caps.get("ort_available"):
                _append("onnxruntime", "cpu")
            if self._accel_caps.get("openvino_available") and self._accel_caps.get("intel_cpu_available"):
                _append("openvino", "intel_cpu")
            _append("tflite", "tflite")
            return targets

        if self._inference_backend == "tflite":
            return targets

        if self._accel_caps.get("ort_available"):
            _append("onnxruntime", "cpu")
        _append("tflite", "tflite")
        return targets

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
                f"Runtime fallback after invalid {failed_backend}/{failed_provider} output: "
                f"{failure_detail}; using {backend}/{provider}"
            )
            return replacement, backend, provider, reason
        return None, None, None, None

    def _gpu_restore_eligible(self) -> bool:
        if self._inference_backend != "openvino" or self._active_inference_provider != "intel_cpu":
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
                self._gpu_restore_not_before_monotonic = (
                    time.monotonic() + CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS
                )
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
            self._last_runtime_recovery = {
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "intel_cpu",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_gpu",
                "detail": "Auto-restored OpenVINO GPU provider after cooldown",
                "at": time.time(),
            }

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
        self._last_runtime_recovery = {
            "status": "recovered",
            "failed_backend": error.backend,
            "failed_provider": error.provider,
            "recovered_backend": "openvino",
            "recovered_provider": "intel_gpu",
            "detail": f"{error.detail}; reloaded GPU model and retrying once",
            "at": time.time(),
        }
        if error.diagnostics:
            self._last_runtime_recovery["diagnostics"] = dict(error.diagnostics)
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
                self._last_runtime_recovery = {
                    "status": "failed",
                    "failed_backend": error.backend,
                    "failed_provider": error.provider,
                    "detail": error.detail,
                    "at": time.time(),
                }
                if error.diagnostics:
                    self._last_runtime_recovery["diagnostics"] = dict(error.diagnostics)
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
                self._gpu_restore_not_before_monotonic = (
                    time.monotonic() + CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS
                )
            self._append_inference_fallback_reason(reason)
            self._runtime_fallback_recoveries += 1
            self._last_runtime_recovery = {
                "status": "recovered",
                "failed_backend": error.backend,
                "failed_provider": error.provider,
                "recovered_backend": backend,
                "recovered_provider": provider,
                "detail": error.detail,
                "at": time.time(),
            }
            if error.diagnostics:
                self._last_runtime_recovery["diagnostics"] = dict(error.diagnostics)
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
        input_size = int(spec["input_size"])
        preprocessing = spec.get("preprocessing")
        runtime = str(spec["runtime"])
        supported_inference_providers = list(spec.get("supported_inference_providers") or [])
        model_config_warnings = [
            str(item).strip() for item in (spec.get("model_config_warnings") or []) if str(item).strip()
        ]

        log.info("Initializing bird model",
                 path=model_path,
                 input_size=input_size,
                 runtime=runtime,
                 preprocessing=preprocessing)

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
        if runtime == 'onnx':
            selection = _resolve_inference_selection(
                self._selected_inference_provider,
                self._accel_caps,
                supported_providers=supported_inference_providers,
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
                )
                if bird_model.load():
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
                    self._inference_fallback_reason = f"{prev_reason}; {fallback_reason}" if prev_reason else fallback_reason
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
                    runtime = 'tflite'
                prev_reason = self._inference_fallback_reason
                fallback_reason = _summarize_openvino_load_error(
                    self._openvino_model_compile_error,
                    self._openvino_model_compile_device,
                    fallback_target="TFLite",
                )
                self._inference_fallback_reason = f"{prev_reason}; {fallback_reason}" if prev_reason else fallback_reason
                log.warning("OpenVINO model load failed and no ORT fallback available; falling back to TFLite", error=bird_model.error)
                runtime = 'tflite'

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
                    log.warning("ONNX Runtime model load failed; retrying with OpenVINO CPU fallback", error=bird_model.error)
                    self._inference_backend = "openvino"
                    self._active_inference_provider = "intel_cpu"
                    prev_reason = self._inference_fallback_reason
                    self._inference_fallback_reason = (
                        f"{prev_reason}; ONNX Runtime load failed" if prev_reason else "ONNX Runtime load failed; using OpenVINO CPU"
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
                    runtime = 'tflite'
                log.warning("ONNX Runtime model load failed; falling back to TFLite", error=bird_model.error)
                runtime = 'tflite'

            log.error(
                "ONNX model requested but no ONNX-capable runtime is available; falling back to TFLite",
                requested_provider=self._selected_inference_provider,
                reason=self._inference_fallback_reason,
            )
            runtime = 'tflite'

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
        with self._models_lock:
            if "bird" in self._models:
                # Cleanup old model resources before replacing
                old_model = self._models.pop("bird")
                if hasattr(old_model, 'cleanup'):
                    old_model.cleanup()
                del old_model
            
            # 1. Initialize locally ONLY if we are a worker or NOT in subprocess mode.
            # This prevents the main process from loading large models into RAM when it
            # should be using supervisor workers instead.
            if self._worker_process_mode or self._image_execution_mode != "subprocess":
                self._init_bird_model()
        
        # 2. If we have a supervisor (main process in subprocess mode), 
        # tell it to restart all workers to pick up the new model.
        if self._classifier_supervisor is not None:
            log.info("Requesting supervisor worker restart for model change")
            await self._classifier_supervisor.restart_pool()

        log.info("Reloaded bird model")

    def _get_wildlife_model(self) -> ModelInstance:
        """Get or lazily load the wildlife model."""
        if "wildlife" not in self._models:
            model_path, labels_path = self._get_model_paths(
                settings.classification.wildlife_model,
                settings.classification.wildlife_labels
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
        if self._classifier_supervisor is None:
            return None
        try:
            metrics = self._classifier_supervisor.get_metrics()
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
        return recoveries[0]

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
        recovery_active = (
            recent_counts["recent_live_abandoned"] > 0
            or recent_counts["recent_live_late_ignored"] > 0
        )
        supervisor_metrics = self._get_supervisor_metrics() or {}
        live_worker_pool = supervisor_metrics.get("live") if isinstance(supervisor_metrics, dict) else {}
        worker_circuit_open = bool((live_worker_pool or {}).get("circuit_open"))
        recovery_reason = None
        if worker_circuit_open:
            recovery_reason = "worker_circuit_open"
        elif recovery_active:
            recovery_reason = "stale_work_reclaim"

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
        if recovery_active or pressure_level == "critical" or worker_circuit_open:
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
            "recovery_active": recovery_active or worker_circuit_open,
            "recovery_reason": recovery_reason,
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
        ) or self._last_runtime_recovery
        
        # Determine which TFLite runtime is actually in use
        tflite_type = "none"
        if tflite:
            if "tflite_runtime" in str(tflite):
                tflite_type = "tflite-runtime"
            else:
                tflite_type = "tensorflow-full"

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
                "tflite": {
                    "installed": tflite is not None,
                    "type": tflite_type
                },
                "onnx": {
                    "installed": ONNX_AVAILABLE,
                    "available": ort is not None
                },
                "openvino": {
                    "installed": OPENVINO_AVAILABLE,
                    "available": OpenVINOCore is not None
                }
            },
            "models": {
                name: {
                    "loaded": model.loaded,
                    "runtime": "onnx" if isinstance(model, ONNXModelInstance) else ("openvino" if isinstance(model, OpenVINOModelInstance) else "tflite"),
                    "error": model.error
                } for name, model in self._models.items()
            },
            "live_image": live_image_health,
            "background_image": background_image_health,
            "background_throttled": background_image_health["background_throttled"],
            "runtime_recovery": runtime_recovery,
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
        self._refresh_accel_caps()
        supervisor_metrics = self._get_supervisor_metrics()
        effective_runtime_recovery = (
            self._latest_worker_runtime_recovery(supervisor_metrics)
            if self._image_execution_mode == "subprocess"
            else None
        ) or self._last_runtime_recovery
        effective_backend, effective_provider = (
            self._effective_subprocess_runtime_fields(effective_runtime_recovery)
            if self._image_execution_mode == "subprocess"
            else (self._inference_backend, self._active_inference_provider)
        )
        active_model_id = None
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

        status = {
            "image_execution_mode": self._image_execution_mode,
            "runtime": "tflite-runtime" if "tflite_runtime" in str(tflite) else "tensorflow",
            "runtime_installed": tflite is not None,
            "onnx_available": ONNX_AVAILABLE,
            "active_model_id": active_model_id,
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
            "dev_dri_present": bool(self._accel_caps.get("dev_dri_present")),
            "dev_dri_entries": self._accel_caps.get("dev_dri_entries") or [],
            "process_uid": self._accel_caps.get("process_uid"),
            "process_gid": self._accel_caps.get("process_gid"),
            "process_groups": self._accel_caps.get("process_groups") or [],
            "selected_provider": _normalize_inference_provider(getattr(settings.classification, "inference_provider", "auto")),
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
            "last_runtime_recovery": effective_runtime_recovery,
            "openvino_runtime": self._openvino_runtime_snapshot(
                active_backend=effective_backend,
                active_provider=effective_provider,
                runtime_recovery=effective_runtime_recovery,
            ),
            "live_image_max_concurrent": admission_metrics["live"]["capacity"],
            "live_image_admission_timeout_seconds": CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS,
            "live_image_admission_timeouts": self._live_image_admission_timeouts,
            "live_image_in_flight": admission_metrics["live"]["running"],
            "live_image_queued": admission_metrics["live"]["queued"],
            "live_image_abandoned": admission_metrics["live"]["abandoned"],
            "background_image_in_flight": admission_metrics["background"]["running"],
            "background_image_queued": admission_metrics["background"]["queued"],
            "background_image_abandoned": admission_metrics["background"]["abandoned"],
            "late_completions_ignored": admission_metrics["late_completions_ignored"],
            "background_throttled": admission_metrics["background_throttled"],
            "available_providers": [
                p for p in ["cpu", "cuda", "intel_cpu", "intel_gpu"]
                if p == "cpu"
                or (p == "cuda" and self._accel_caps.get("cuda_available"))
                or (p == "intel_cpu" and self._accel_caps.get("intel_cpu_available"))
                or (p == "intel_gpu" and self._accel_caps.get("intel_gpu_available"))
            ],
            # legacy compatibility (can be removed later)
            "cuda_enabled": _normalize_inference_provider(getattr(settings.classification, "inference_provider", "auto")) == "cuda",
            "models": {},
            "crop_detector": crop_detector_status,
        }
        if supervisor_metrics is not None:
            status["worker_pools"] = supervisor_metrics

        for name, model in self._models.items():
            model_status = model.get_status()
            if name == "bird" and isinstance(model, ONNXModelInstance) and model.session:
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
        if normalized_device not in {"CPU", "GPU"}:
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
                "provider": "intel_gpu" if normalized_device == "GPU" else "intel_cpu",
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
            settings.classification.wildlife_model,
            settings.classification.wildlife_labels
        )
        model_exists = os.path.exists(model_path)
        labels_exist = os.path.exists(labels_path)
        labels_count = 0
        if labels_exist:
            try:
                with open(labels_path, 'r') as f:
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
        normalized = (
            0.0 <= left <= 1.0
            and 0.0 <= top <= 1.0
            and 0.0 <= width <= 1.0
            and 0.0 <= height <= 1.0
        )
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

        try:
            spec = dict(self._resolve_active_bird_model_spec() or {})
        except Exception as exc:
            diagnostics["crop_reason"] = "spec_resolution_failed"
            log.debug(
                "Bird crop resolution skipped",
                crop_attempted=False,
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
                error=_summarize_runtime_exception(exc),
            )
            return image, diagnostics

        crop_generator = dict(spec.get("crop_generator") or {})
        crop_enabled = bool(crop_generator.get("enabled"))
        if not crop_enabled:
            diagnostics["crop_reason"] = "crop_disabled"
            log.debug(
                "Bird crop resolution skipped",
                crop_attempted=False,
                crop_applied=False,
                crop_reason=diagnostics["crop_reason"],
            )
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

        hint_crop = self._resolve_frigate_hint_crop(
            crop_source_image,
            input_context=normalized_input_context,
        )
        if isinstance(hint_crop, dict) and isinstance(hint_crop.get("crop_image"), Image.Image):
            diagnostics["crop_applied"] = True
            diagnostics["crop_reason"] = str(hint_crop.get("reason") or "frigate_hint")
            log.debug(
                "Bird crop applied",
                crop_attempted=True,
                crop_applied=True,
                crop_reason=diagnostics["crop_reason"],
                source_reason=diagnostics.get("source_reason"),
                crop_box=hint_crop.get("box"),
            )
            return hint_crop["crop_image"], diagnostics

        crop_result: dict[str, Any] | None = None
        try:
            crop_result = self._bird_crop_service.generate_crop(crop_source_image) if self._bird_crop_service is not None else None
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

    def classify(
        self,
        image: Image.Image,
        camera_name: Optional[str] = None,
        model_id: Optional[str] = None,
        input_context: Any | None = None,
    ) -> list[dict]:
        """Classify an image using the bird model."""
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
                crop_image, _crop_diagnostics = self._resolve_bird_classification_image(
                    image,
                    input_context=input_context,
                )
                results = _invoke_model_classify(bird, crop_image, input_context=input_context)
                if self._inference_backend == "openvino" and self._active_inference_provider == "intel_gpu":
                    self._record_gpu_success()
                return results
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
                scores = bird.classify_raw(crop_image)
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
                input_context=dict(normalized_input_context.model_dump()) if normalized_input_context is not None else None,
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
        capacity = int(self._classification_admission.get_metrics()[priority]["capacity"])

        try:
            return await self._classification_admission.submit(
                priority=priority,
                kind=kind,
                runner=runner,
                queue_timeout_seconds=queue_timeout_seconds,
                lease_timeout_seconds=lease_timeout_seconds,
                runner_accepts_work_metadata=runner_accepts_work_metadata,
                on_lease_expired=on_lease_expired,
            )
        except ClassificationAdmissionTimeoutError:
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
        except ClassificationLeaseExpiredError:
            if priority == "live":
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

    async def _run_coordinated_executor_inference(
        self,
        priority: Literal["live", "background"],
        executor: ThreadPoolExecutor,
        kind: str,
        fn: Callable[..., list[dict]],
        *args: Any,
        queue_timeout_seconds: float | None = None,
    ) -> list[dict]:
        async def _runner() -> list[dict]:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, fn, *args)

        return await self._run_coordinated_inference(
            priority,
            kind,
            _runner,
            queue_timeout_seconds=queue_timeout_seconds,
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
        )

    async def _run_image_inference(
        self,
        fn: Callable[..., list[dict]],
        *args: Any,
    ) -> list[dict]:
        if self._image_execution_mode == "subprocess" and args:
            return await self._run_coordinated_supervised_inference(
                "background",
                "image_inference",
                args[0],
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
                args[3] if len(args) > 3 else None,
            )
        return await self._run_coordinated_executor_inference(
            "background",
            self._image_executor,
            "image_inference",
            fn,
            *args,
        )

    async def _run_live_image_inference(
        self,
        fn: Callable[..., list[dict]],
        *args: Any,
        queue_timeout_seconds: float | None = None,
    ) -> list[dict]:
        if self._image_execution_mode == "subprocess" and args:
            return await self._run_coordinated_supervised_inference(
                "live",
                "live_image_inference",
                args[0],
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
                args[3] if len(args) > 3 else None,
                queue_timeout_seconds=queue_timeout_seconds,
            )
        return await self._run_coordinated_executor_inference(
            "live",
            self._live_image_executor,
            "live_image_inference",
            fn,
            *args,
            queue_timeout_seconds=queue_timeout_seconds,
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
            base_results = await self._run_image_inference(self.classify, image, camera_name, model_id, normalized_input_context)
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
        if self._image_execution_mode == "subprocess":
            base_results = await self._run_coordinated_supervised_inference(
                "background",
                "background_image_inference",
                image,
                camera_name,
                model_id,
                normalized_input_context,
                queue_timeout_seconds=queue_timeout_seconds,
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
            if hasattr(old_model, 'cleanup'):
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

            all_scores = []

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
                                model_name=model_name
                            )
                        except Exception:
                            pass
                    continue

                # Convert BGR (OpenCV) to RGB (PIL)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)

                # Get raw probability vector, recovering from invalid runtime output if possible.
                scores, active_bird_model = self._classify_raw_with_runtime_recovery(
                    image,
                    input_context=normalized_input_context,
                )
                if active_bird_model is not None:
                    bird_model = active_bird_model

                if len(scores) > 0:
                    all_scores.append(scores)

                    # Update last valid result metadata
                    top_idx = int(np.argmax(scores))
                    last_top_score = float(scores[top_idx])
                    last_top_label = normalize_classifier_label(bird_model.labels[top_idx]) if top_idx < len(bird_model.labels) else f"Class {top_idx}"
                    
                    try:
                        from io import BytesIO
                        import base64
                        thumb = image.copy()
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
                            model_name=model_name
                        )
                    except Exception as exc:
                        log.warning(
                            "Video classification progress callback failed; continuing",
                            error=str(exc),
                            frame_index=int(idx) + 1,
                            total_frames=len(frame_indices),
                        )

            if not all_scores:
                log.warning("No frames processed from video")
                return []

            # Best-frame ensemble: keep each class' strongest frame confidence.
            # This avoids suppressing legitimate transient detections when many
            # sampled frames are background-heavy.
            processed_count = len(all_scores)
            scores_matrix = np.vstack(all_scores)
            representative_scores = np.max(scores_matrix, axis=0)

            # Create standard classification list from representative scores
            top_indices = representative_scores.argsort()[-5:][::-1]

            classifications = []
            for i in top_indices:
                score = float(representative_scores[i])
                label = normalize_classifier_label(bird_model.labels[i]) if i < len(bird_model.labels) else f"Class {i}"
                classifications.append({
                    "index": int(i),
                    "score": score,
                    "label": label,
                    "inference_provider": str(self._active_inference_provider or ""),
                    "inference_backend": str(self._inference_backend or ""),
                    "model_id": str(active_model_id or ""),
                    "model_name": model_name,
                })

            if classifications:
                top_score = float(classifications[0]["score"])
                class_count = int(len(representative_scores))
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
                    return []

            log.info(f"Video classification complete (Top-K). Analyzed {processed_count} frames.",
                     top_result=classifications[0]['label'] if classifications else None,
                     top_score=round(classifications[0]['score'], 3))

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
    ) -> list[dict]:
        """Async wrapper for video classification."""
        normalized_input_context = _normalize_classification_input_context(input_context)
        if max_frames is None:
            max_frames = settings.classification.video_classification_frames

        if self._image_execution_mode == "subprocess" and self._classifier_supervisor is not None:
            try:
                base_results = await self._classifier_supervisor.classify_video(
                    work_id=f"video-{time.monotonic_ns()}",
                    lease_token=1,
                    video_path=video_path,
                    stride=stride,
                    max_frames=max_frames,
                    progress_callback=progress_callback,
                    input_context=dict(normalized_input_context.model_dump()),
                )
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
                    model_name=None
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
                                model_name
                            ),
                            loop
                        )
                        try:
                            future.result(timeout=1.0)
                        except TimeoutError:
                            log.warning("Progress callback timed out after 1s",
                                       frame=current_frame,
                                       total=total_frames)
                        except Exception as e:
                            log.error("Progress callback failed",
                                     error=str(e),
                                     frame=current_frame,
                                     total=total_frames)
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
