from __future__ import annotations

import importlib
import json
import math
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
import structlog
from PIL import Image

from app.config import settings

log = structlog.get_logger()


def _openvino_dimension_value(dimension: Any) -> int | str:
    """Convert an OpenVINO dimension into the ORT-like shape form we consume."""
    try:
        if bool(getattr(dimension, "is_static")):
            return int(dimension.get_length())
    except Exception:
        pass
    try:
        value = int(dimension)
        return value if value > 0 else "dynamic"
    except (TypeError, ValueError):
        return "dynamic"


def _openvino_port_name(port: Any, fallback: str) -> str:
    for method_name in ("get_any_name", "get_names"):
        try:
            value = getattr(port, method_name)()
            if isinstance(value, set):
                value = sorted(value)[0] if value else None
            if value:
                return str(value)
        except Exception:
            continue
    return fallback


def _openvino_tensor_type(port: Any) -> str:
    try:
        element_type = str(port.get_element_type()).strip().lower()
    except Exception:
        element_type = "f32"
    return "tensor(uint8)" if "u8" in element_type or "uint8" in element_type else "tensor(float)"


class _OpenVINODetectorSession:
    """Small ORT-compatible adapter for detector inference on Intel devices."""

    def __init__(self, model_path: Path, *, device: str):
        try:
            openvino = importlib.import_module("openvino")
            core_cls = getattr(openvino, "Core")
        except Exception:
            runtime = importlib.import_module("openvino.runtime")
            core_cls = getattr(runtime, "Core")

        self.device = str(device or "CPU")
        self._lock = threading.Lock()
        self._core = core_cls()
        cache_dir = os.getenv("OPENVINO_CACHE_DIR", "/tmp/openvino_cache")
        os.makedirs(cache_dir, exist_ok=True)
        try:
            self._core.set_property({"CACHE_DIR": cache_dir})
        except Exception:
            pass
        model = self._core.read_model(str(model_path))

        is_gpu = self.device == "GPU" or self.device.startswith("GPU.")
        is_npu = self.device == "NPU" or self.device.startswith("NPU.")
        if is_gpu or is_npu:
            try:
                partial = model.inputs[0].get_partial_shape()
                if partial.rank.is_static and partial[0].is_dynamic:
                    static_shape = [1] + [partial[index].get_length() for index in range(1, partial.rank.get_length())]
                    model.reshape(static_shape)
            except Exception:
                # Static reshape is a compatibility aid. Compilation remains the
                # authoritative test and will fail closed in the provider probe.
                pass

        config: dict[str, str] = {"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1"}
        if is_gpu:
            # The detector outputs include large intermediate activations. Avoid
            # silent f16 overflow on Intel GPUs, matching the classifier policy.
            config["INFERENCE_PRECISION_HINT"] = "f32"
        self._compiled = self._core.compile_model(model, self.device, config)
        self._input_port = self._compiled.inputs[0]
        self._output_ports = list(self._compiled.outputs)

        try:
            partial_shape = self._input_port.get_partial_shape()
            shape = [
                _openvino_dimension_value(partial_shape[index]) for index in range(partial_shape.rank.get_length())
            ]
        except Exception:
            try:
                shape = [int(value) for value in self._input_port.shape]
            except Exception:
                shape = []
        self._input = SimpleNamespace(
            name=_openvino_port_name(self._input_port, "images"),
            shape=shape,
            type=_openvino_tensor_type(self._input_port),
        )
        self._outputs = [
            SimpleNamespace(name=_openvino_port_name(port, f"output_{index}"))
            for index, port in enumerate(self._output_ports)
        ]

    def get_inputs(self) -> list[Any]:
        return [self._input]

    def get_outputs(self) -> list[Any]:
        return list(self._outputs)

    def get_providers(self) -> list[str]:
        return [f"OpenVINO:{self.device}"]

    def run(self, _output_names: Any, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        if self._input.name not in feeds:
            raise ValueError(f"Missing detector input {self._input.name}")
        with self._lock:
            request = self._compiled.create_infer_request()
            values = request.infer({self._input.name: feeds[self._input.name]})
        outputs: list[np.ndarray] = []
        for port in self._output_ports:
            try:
                outputs.append(np.asarray(values[port]))
            except Exception:
                outputs.append(np.asarray(values[_openvino_port_name(port, "")]))
        return outputs


class BirdCropService:
    """Fail-soft helper for producing a tighter bird crop."""

    ACCURATE_TIER_CONFIDENCE_FLOOR = 0.05
    # Exploratory crops are never allowed to replace a full frame by themselves.
    # They are admitted only into pathways that retain the full frame and require
    # downstream classifier/temporal evidence before promotion.  The lower floor
    # recovers small, distant birds whose correct YOLOX box can score below the
    # normal thumbnail/single-image replacement threshold.
    CLASSIFICATION_CANDIDATE_CONFIDENCE_FLOOR = 0.02
    CLASSIFICATION_CANDIDATE_MIN_DETECTION_SIZE = 24
    CLASSIFICATION_CANDIDATE_MIN_OUTPUT_SIZE = 160
    CLASSIFICATION_TILE_GRID_SIZE = 2
    CLASSIFICATION_TILE_OVERLAP_RATIO = 0.20
    CLASSIFICATION_TILE_MODEL_INPUT_SIZE = 416
    ACCURATE_TIER_MIN_CROP_SIZE = 64

    def __init__(
        self,
        *,
        model_id: str = "bird_crop",
        detector_tier: str | None = None,
        accurate_model_id: str = "bird_crop_detector_accurate_yolox_tiny",
        confidence_threshold: float = 0.35,
        expand_ratio: float = 0.12,
        min_crop_size: int = 96,
        fallback_to_original: bool = True,
        model_loader: Callable[[], Any] | None = None,
        provider_override: str | None = None,
        strict_provider: bool = False,
    ):
        self.model_id = str(model_id or "bird_crop")
        normalized_detector_tier = str(detector_tier or "").strip().lower()
        self.detector_tier = normalized_detector_tier if normalized_detector_tier in {"fast", "accurate"} else None
        self.accurate_model_id = str(accurate_model_id or "bird_crop_detector_accurate_yolox_tiny")
        self.confidence_threshold = float(confidence_threshold)
        self.expand_ratio = max(0.0, float(expand_ratio))
        self.min_crop_size = max(1, int(min_crop_size))
        self.fallback_to_original = bool(fallback_to_original)
        self._model_loader = model_loader
        self.provider_override = str(provider_override or "").strip().lower() or None
        self.strict_provider = bool(strict_provider)
        self._model_lock = threading.Lock()
        self._models: dict[str, Any | None] = {}
        self._models_loaded: dict[str, bool] = {}
        self._model_error: str | None = None
        self._model_errors: dict[str, str | None] = {}
        self._active_providers: dict[str, str] = {}
        self._provider_fallbacks: dict[str, str | None] = {}

    def generate_crop(self, image: Image.Image, *, detector_tier: str | None = None) -> dict[str, Any]:
        """Return the best crop candidate, failing from accurate to fast on any miss."""
        return self._generate_crop(
            image,
            detector_tier=detector_tier,
        )

    def _generate_crop(
        self,
        image: Image.Image,
        *,
        detector_tier: str | None = None,
        accurate_confidence_ceiling: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(image, Image.Image):
            return self._empty_result("invalid_image")

        requested_tier = self._normalize_detector_tier(detector_tier)
        result, model_available = self._generate_crop_for_tier(
            image,
            requested_tier,
            confidence_threshold_ceiling=(accurate_confidence_ceiling if requested_tier == "accurate" else None),
        )
        if requested_tier != "accurate" or (model_available and result.get("reason") == "selected"):
            return result

        accurate_reason = str(result.get("reason") or "unavailable").removesuffix("_no_fallback")
        fallback_reason = "accurate_unavailable" if not model_available else f"accurate_{accurate_reason}"
        fast_result, fast_available = self._generate_crop_for_tier(
            image,
            "fast",
            fallback_reason=fallback_reason,
        )
        if fast_available:
            return fast_result
        if not model_available:
            return self._empty_result(
                "load_failed",
                detector_tier=None,
                fallback_reason="no_detector_available",
            )

        preserved = dict(result)
        preserved["fallback_reason"] = f"{fallback_reason}:fast_unavailable"
        return preserved

    def _generate_crop_for_tier(
        self,
        image: Image.Image,
        detector_tier: str,
        *,
        fallback_reason: str | None = None,
        confidence_threshold_ceiling: float | None = None,
        min_crop_size_ceiling: int | None = None,
        minimum_output_size: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Run one detector tier and return its fail-soft result plus availability."""
        try:
            model = self._ensure_model_for_tier(detector_tier)
        except Exception as exc:  # pragma: no cover - defensive guard
            self._model_error = str(exc)
            self._model_errors[detector_tier] = str(exc)
            log.warning("Bird crop model load failed", detector_tier=detector_tier, error=str(exc))
            model = None

        if model is None:
            return (
                self._empty_result(
                    "load_failed",
                    detector_tier=detector_tier,
                    fallback_reason=fallback_reason,
                ),
                False,
            )

        try:
            candidates = self._infer_candidates(model, image)
        except Exception as exc:
            active_provider = str((model or {}).get("provider") or "cpu") if isinstance(model, dict) else "cpu"
            if not self.strict_provider and active_provider != "cpu":
                try:
                    model = self._replace_tier_with_cpu(detector_tier, failed_provider=active_provider)
                    candidates = self._infer_candidates(model, image)
                except Exception as fallback_exc:
                    log.warning(
                        "Bird crop inference and CPU fallback failed",
                        detector_tier=detector_tier,
                        provider=active_provider,
                        error=str(fallback_exc),
                    )
                    return (
                        self._empty_result(
                            "inference_failed",
                            detector_tier=detector_tier,
                            fallback_reason=fallback_reason,
                        ),
                        True,
                    )
            else:
                log.warning("Bird crop inference failed", detector_tier=detector_tier, error=str(exc))
                return (
                    self._empty_result(
                        "inference_failed",
                        detector_tier=detector_tier,
                        fallback_reason=fallback_reason,
                    ),
                    True,
                )

        return (
            self._select_best_valid_candidate(
                image,
                candidates,
                detector_tier=detector_tier,
                fallback_reason=fallback_reason,
                confidence_threshold_ceiling=confidence_threshold_ceiling,
                min_crop_size_ceiling=min_crop_size_ceiling,
                minimum_output_size=minimum_output_size,
            ),
            True,
        )

    def generate_classification_crop(self, image: Image.Image) -> dict[str, Any]:
        """Use the detector tier validated for automatic classifier image preparation."""
        return self.generate_crop(image, detector_tier="accurate")

    def generate_classification_candidate_crop(self, image: Image.Image) -> dict[str, Any]:
        """Return a distance-tolerant crop for evidence-comparison pathways only.

        The caller must retain the full frame and apply downstream identity or
        temporal-consensus gates.  This deliberately does not change the normal
        thumbnail or single-image replacement policy. Native inference remains
        the first attempt. If it misses on a high-resolution frame, four bounded
        overlapping tiles improve the effective pixels-on-bird without creating
        an unbounded background workload.
        """
        if not isinstance(image, Image.Image):
            return self._annotate_candidate_strategy(self._empty_result("invalid_image"), strategy="native")
        native_result, accurate_available = self._generate_classification_candidate_for_tier(
            image,
            strategy="native",
        )
        if native_result.get("reason") == "selected":
            return native_result

        if accurate_available:
            sliced_result = self._generate_sliced_classification_candidate_crop(image)
            if sliced_result is not None and sliced_result.get("reason") == "selected":
                return sliced_result

        accurate_reason = str(native_result.get("reason") or "unavailable").removesuffix("_no_fallback")
        fallback_reason = "accurate_unavailable" if not accurate_available else f"accurate_{accurate_reason}"
        fast_result, fast_available = self._generate_crop_for_tier(
            image,
            "fast",
            fallback_reason=fallback_reason,
        )
        if fast_available:
            return self._annotate_candidate_strategy(fast_result, strategy="fast_native")
        if not accurate_available:
            return self._annotate_candidate_strategy(
                self._empty_result(
                    "load_failed",
                    detector_tier=None,
                    fallback_reason="no_detector_available",
                ),
                strategy="native",
            )
        return native_result

    def generate_guided_classification_candidate_crop(
        self,
        image: Image.Image,
        *,
        search_box: tuple[int, int, int, int] | list[int],
    ) -> dict[str, Any]:
        """Refine a trustworthy Frigate region before falling back to native/sliced inference.

        Frigate's tracked box supplies localisation only. YOLOX still has to find
        a bird inside the high-resolution region, and the returned coordinates
        are restored to the unchanged source frame. The caller keeps both the
        Frigate crop and full frame as independent peers.
        """
        if not isinstance(image, Image.Image):
            return self._annotate_candidate_strategy(self._empty_result("invalid_image"), strategy="frigate_guided")
        normalized_search_box = self._normalize_search_box(search_box, image.size)
        if normalized_search_box is None:
            fallback = self.generate_classification_candidate_crop(image)
            return self._with_fallback_reason(fallback, "invalid_guided_search_box")
        normalized_search_box = self._square_search_box(
            normalized_search_box,
            image.size,
            minimum_size=self.CLASSIFICATION_CANDIDATE_MIN_OUTPUT_SIZE,
        )
        if normalized_search_box is None:
            fallback = self.generate_classification_candidate_crop(image)
            return self._with_fallback_reason(fallback, "invalid_guided_search_box")

        search_image = image.crop(normalized_search_box)
        guided_result, accurate_available = self._generate_classification_candidate_for_tier(
            search_image,
            strategy="frigate_guided",
        )
        if guided_result.get("reason") == "selected":
            return self._restore_region_result_to_image(
                image,
                guided_result,
                region_box=normalized_search_box,
                strategy="frigate_guided",
            )

        fallback = self.generate_classification_candidate_crop(image)
        guided_reason = "unavailable" if not accurate_available else str(guided_result.get("reason") or "miss")
        return self._with_fallback_reason(fallback, f"guided_{guided_reason}")

    def _generate_classification_candidate_for_tier(
        self,
        image: Image.Image,
        *,
        strategy: str,
    ) -> tuple[dict[str, Any], bool]:
        result, available = self._generate_crop_for_tier(
            image,
            "accurate",
            confidence_threshold_ceiling=self.CLASSIFICATION_CANDIDATE_CONFIDENCE_FLOOR,
            min_crop_size_ceiling=self.CLASSIFICATION_CANDIDATE_MIN_DETECTION_SIZE,
            minimum_output_size=self.CLASSIFICATION_CANDIDATE_MIN_OUTPUT_SIZE,
        )
        return self._annotate_candidate_strategy(result, strategy=strategy), available

    def _generate_sliced_classification_candidate_crop(self, image: Image.Image) -> dict[str, Any] | None:
        tile_boxes = self._classification_tile_boxes(image.size)
        if not tile_boxes:
            return None

        selected: list[dict[str, Any]] = []
        for tile_box in tile_boxes:
            tile = image.crop(tile_box)
            tile_result, available = self._generate_classification_candidate_for_tier(
                tile,
                strategy="sliced_2x2",
            )
            if not available:
                return None
            if tile_result.get("reason") != "selected":
                continue
            selected.append(
                self._restore_region_result_to_image(
                    image,
                    tile_result,
                    region_box=tile_box,
                    strategy="sliced_2x2",
                    tile_count=len(tile_boxes),
                )
            )
        if not selected:
            return None
        return max(selected, key=lambda result: float(result.get("confidence") or 0.0))

    def _classification_tile_boxes(self, image_size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
        width, height = (max(0, int(image_size[0])), max(0, int(image_size[1])))
        model_input = self.CLASSIFICATION_TILE_MODEL_INPUT_SIZE
        if min(width, height) < model_input or max(width, height) < model_input * 2:
            return []

        overlap = min(0.49, max(0.0, float(self.CLASSIFICATION_TILE_OVERLAP_RATIO)))
        grid_size = max(2, int(self.CLASSIFICATION_TILE_GRID_SIZE))
        divisor = float(grid_size) - (float(grid_size - 1) * overlap)
        tile_width = min(width, max(1, int(math.ceil(float(width) / divisor))))
        tile_height = min(height, max(1, int(math.ceil(float(height) / divisor))))
        x_positions = [int(round(index * (width - tile_width) / float(grid_size - 1))) for index in range(grid_size)]
        y_positions = [int(round(index * (height - tile_height) / float(grid_size - 1))) for index in range(grid_size)]
        return [
            (left, top, min(width, left + tile_width), min(height, top + tile_height))
            for top in y_positions
            for left in x_positions
        ]

    def _normalize_search_box(
        self,
        raw_box: tuple[int, int, int, int] | list[int],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            left, top, right, bottom = [float(value) for value in raw_box]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, right, bottom)):
            return None
        width, height = image_size
        normalized = (
            max(0, min(int(width), int(math.floor(left)))),
            max(0, min(int(height), int(math.floor(top)))),
            max(0, min(int(width), int(math.ceil(right)))),
            max(0, min(int(height), int(math.ceil(bottom)))),
        )
        if normalized[2] <= normalized[0] or normalized[3] <= normalized[1]:
            return None
        return normalized

    def _square_search_box(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
        *,
        minimum_size: int,
    ) -> tuple[int, int, int, int] | None:
        left, top, right, bottom = box
        image_width, image_height = image_size
        if right <= left or bottom <= top or image_width <= 0 or image_height <= 0:
            return None
        target_size = min(
            int(image_width),
            int(image_height),
            max(right - left, bottom - top, int(minimum_size)),
        )
        return self._expand_box_to_minimum_size(
            box,
            image_size,
            minimum_size=target_size,
        )

    def _restore_region_result_to_image(
        self,
        image: Image.Image,
        result: dict[str, Any],
        *,
        region_box: tuple[int, int, int, int],
        strategy: str,
        tile_count: int | None = None,
    ) -> dict[str, Any]:
        relative_box = self._extract_box(result)
        if relative_box is None:
            return self._annotate_candidate_strategy(result, strategy=strategy)
        offset_x, offset_y = region_box[0], region_box[1]
        restored = self._normalize_search_box(
            (
                relative_box[0] + offset_x,
                relative_box[1] + offset_y,
                relative_box[2] + offset_x,
                relative_box[3] + offset_y,
            ),
            image.size,
        )
        if restored is None:
            return self._annotate_candidate_strategy(
                self._empty_result("invalid_box", detector_tier="accurate"),
                strategy=strategy,
            )
        updated = dict(result)
        updated["box"] = restored
        updated["crop_image"] = image.crop(restored)
        updated["strategy"] = strategy
        if strategy == "frigate_guided":
            updated["search_box"] = region_box
        if tile_count is not None:
            updated["tile_count"] = int(tile_count)
        return updated

    @staticmethod
    def _annotate_candidate_strategy(result: dict[str, Any], *, strategy: str) -> dict[str, Any]:
        updated = dict(result)
        updated["strategy"] = strategy
        return updated

    @staticmethod
    def _with_fallback_reason(result: dict[str, Any], reason: str) -> dict[str, Any]:
        updated = dict(result)
        existing = str(updated.get("fallback_reason") or "").strip()
        updated["fallback_reason"] = f"{reason}:{existing}" if existing else reason
        return updated

    def get_classification_candidate_crop_policy(self) -> dict[str, float | int | str | bool]:
        """Describe the bounded policy used for evidence-only crop candidates."""
        policy = dict(self.get_effective_crop_policy("accurate"))
        policy["confidence_threshold"] = min(
            float(policy["confidence_threshold"]),
            self.CLASSIFICATION_CANDIDATE_CONFIDENCE_FLOOR,
        )
        policy["selection_mode"] = "evidence_candidate"
        policy["guided_roi"] = True
        policy["min_detection_size"] = self.CLASSIFICATION_CANDIDATE_MIN_DETECTION_SIZE
        policy["min_output_size"] = self.CLASSIFICATION_CANDIDATE_MIN_OUTPUT_SIZE
        policy["slicing_grid"] = f"{self.CLASSIFICATION_TILE_GRID_SIZE}x{self.CLASSIFICATION_TILE_GRID_SIZE}"
        policy["slicing_overlap_ratio"] = self.CLASSIFICATION_TILE_OVERLAP_RATIO
        policy["max_sliced_inference_calls"] = self.CLASSIFICATION_TILE_GRID_SIZE**2
        return policy

    def _ensure_model(self) -> Any | None:
        return self._ensure_model_for_tier("fast")

    def _requested_detector_tier(self) -> str:
        if self.detector_tier in {"fast", "accurate"}:
            return self.detector_tier
        configured = str(getattr(settings.classification, "bird_crop_detector_tier", "fast") or "fast").strip().lower()
        return configured if configured in {"fast", "accurate"} else "fast"

    def _model_id_for_tier(self, tier: str) -> str:
        return self.accurate_model_id if str(tier or "").strip().lower() == "accurate" else self.model_id

    def _registry_model_id_for_tier(self, tier: str) -> str:
        return self.accurate_model_id if str(tier or "").strip().lower() == "accurate" else "bird_crop_detector"

    def _normalize_detector_tier(self, detector_tier: str | None = None) -> str:
        normalized = str(detector_tier or "").strip().lower()
        if normalized in {"fast", "accurate"}:
            return normalized
        return self._requested_detector_tier()

    def get_effective_crop_policy(self, detector_tier: str | None = None) -> dict[str, float | int | str]:
        normalized_tier = self._normalize_detector_tier(detector_tier)
        confidence_threshold = self.confidence_threshold
        min_crop_size = self.min_crop_size
        if normalized_tier == "accurate":
            confidence_threshold = min(confidence_threshold, self.ACCURATE_TIER_CONFIDENCE_FLOOR)
            min_crop_size = min(min_crop_size, self.ACCURATE_TIER_MIN_CROP_SIZE)
        return {
            "detector_tier": normalized_tier,
            "confidence_threshold": float(confidence_threshold),
            "min_crop_size": max(1, int(min_crop_size)),
            "expand_ratio": max(0.0, float(self.expand_ratio)),
        }

    def _ensure_model_for_tier(self, tier: str) -> Any | None:
        normalized_tier = "accurate" if str(tier or "").strip().lower() == "accurate" else "fast"
        if self._models_loaded.get(normalized_tier):
            return self._models.get(normalized_tier)

        with self._model_lock:
            if self._models_loaded.get(normalized_tier):
                return self._models.get(normalized_tier)
            model = self._load_model_for_tier(normalized_tier)
            self._models[normalized_tier] = model
            self._models_loaded[normalized_tier] = model is not None
            return model

    def _load_model(self) -> Any | None:
        return self._load_model_impl("fast")

    def _load_model_for_tier(self, tier: str) -> Any | None:
        normalized_tier = "accurate" if str(tier or "").strip().lower() == "accurate" else "fast"
        if normalized_tier == "fast":
            return self._load_model()
        return self._load_model_impl(normalized_tier)

    def _load_model_impl(self, tier: str) -> Any | None:
        if self._model_loader is not None:
            return self._model_loader()
        model_path = self._resolve_model_path(tier)
        if model_path is None:
            return None
        model_config = self._load_model_config(model_path)
        requested_provider = self._provider_for_tier(tier)
        try:
            model = self._load_model_on_provider(
                tier=tier,
                model_path=model_path,
                model_config=model_config,
                provider=requested_provider,
            )
            self._active_providers[tier] = requested_provider
            self._provider_fallbacks[tier] = None
            return model
        except Exception as exc:
            if self.strict_provider or requested_provider == "cpu":
                raise
            log.warning(
                "Bird crop accelerated provider load failed; falling back to CPU",
                detector_tier=tier,
                provider=requested_provider,
                error=str(exc),
            )
            model = self._load_model_on_provider(
                tier=tier,
                model_path=model_path,
                model_config=model_config,
                provider="cpu",
            )
            self._active_providers[tier] = "cpu"
            self._provider_fallbacks[tier] = requested_provider
            return model

    def _provider_for_tier(self, tier: str) -> str:
        if self.provider_override:
            return self.provider_override
        try:
            from app.services.model_validation import activation_provider_recommendation

            recommendation = activation_provider_recommendation(self._registry_model_id_for_tier(tier))
        except Exception:
            recommendation = None
        return str(recommendation or "cpu").strip().lower()

    def _load_model_on_provider(
        self,
        *,
        tier: str,
        model_path: Path,
        model_config: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        detector_config = dict(model_config.get("detector") or {})
        preprocessing = dict(model_config.get("preprocessing") or {})
        preferred_input_size = self._resolve_config_input_size(model_config)
        normalized_provider = str(provider or "cpu").strip().lower()
        if normalized_provider in {"cpu", "cuda"}:
            ort = self._import_onnxruntime()
            sess_options = ort.SessionOptions()
            ort_provider = "CUDAExecutionProvider" if normalized_provider == "cuda" else "CPUExecutionProvider"
            session = ort.InferenceSession(
                str(model_path),
                sess_options=sess_options,
                providers=[ort_provider],
            )
            active = list(getattr(session, "get_providers", lambda: [ort_provider])() or [])
            if not active or active[0] != ort_provider:
                raise RuntimeError(f"{ort_provider} was requested but is not the primary active provider")
        else:
            device = {
                "intel_cpu": "CPU",
                "intel_gpu": "GPU",
                "intel_npu": "NPU",
            }.get(normalized_provider)
            if not device:
                raise ValueError(f"Unsupported crop detector provider: {normalized_provider}")
            session = _OpenVINODetectorSession(model_path, device=device)
        model_input = session.get_inputs()[0]
        input_shape = getattr(model_input, "shape", None)
        input_layout = self._infer_input_layout(input_shape)
        dynamic_input_hw = self._has_dynamic_hw(input_shape, layout=input_layout)
        input_height, input_width = self._resolve_input_hw(input_shape, layout=input_layout)
        get_outputs = getattr(session, "get_outputs", None)
        session_outputs = get_outputs() if callable(get_outputs) else []
        return {
            "session": session,
            "input_name": str(getattr(model_input, "name", "images") or "images"),
            "input_height": input_height,
            "input_width": input_width,
            "input_layout": input_layout,
            "input_type": str(getattr(model_input, "type", "") or ""),
            "dynamic_input_hw": dynamic_input_hw,
            "preferred_input_height": preferred_input_size,
            "preferred_input_width": preferred_input_size,
            "preprocessing": preprocessing,
            "output_names": [str(getattr(output, "name", "") or "") for output in (session_outputs or [])],
            "detector_tier": "accurate" if str(tier or "").strip().lower() == "accurate" else "fast",
            "detector_config": detector_config,
            "model_path": str(model_path),
            "provider": normalized_provider,
        }

    def reset_models(self) -> None:
        """Release cached detector sessions so a new validation result takes effect."""
        with self._model_lock:
            self._models.clear()
            self._models_loaded.clear()
            self._active_providers.clear()
            self._provider_fallbacks.clear()
            self._model_error = None
            self._model_errors.clear()

    def _replace_tier_with_cpu(self, tier: str, *, failed_provider: str) -> dict[str, Any]:
        model_path = self._resolve_model_path(tier)
        if model_path is None:
            raise FileNotFoundError(f"Crop detector model for {tier} is no longer installed")
        replacement = self._load_model_on_provider(
            tier=tier,
            model_path=model_path,
            model_config=self._load_model_config(model_path),
            provider="cpu",
        )
        with self._model_lock:
            self._models[tier] = replacement
            self._models_loaded[tier] = True
            self._active_providers[tier] = "cpu"
            self._provider_fallbacks[tier] = failed_provider
        log.warning(
            "Bird crop provider failed during inference; CPU fallback activated",
            detector_tier=tier,
            failed_provider=failed_provider,
        )
        return replacement

    def _load_model_config(self, model_path: Path) -> dict[str, Any]:
        config_path = model_path.with_name("model_config.json")
        if not config_path.exists():
            return {}
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def _resolve_config_input_size(self, model_config: dict[str, Any] | None = None) -> int | None:
        raw = (model_config or {}).get("input_size")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _resolve_model_path(self, tier: str = "fast") -> Path | None:
        try:
            candidates = self._candidate_model_paths(tier)
        except TypeError:
            candidates = self._candidate_model_paths()
        for candidate in candidates:
            normalized = Path(str(candidate or "")).expanduser()
            if normalized.is_file():
                return normalized
        return None

    def _candidate_model_paths(self, tier: str = "fast") -> list[str]:
        normalized_tier = "accurate" if str(tier or "").strip().lower() == "accurate" else "fast"
        env_var = "BIRD_CROP_MODEL_PATH_ACCURATE" if normalized_tier == "accurate" else "BIRD_CROP_MODEL_PATH"
        env_path = str(os.getenv(env_var) or "").strip()
        candidates: list[str] = []
        if env_path:
            candidates.append(env_path)

        try:
            from app.services.model_manager import model_manager

            try:
                detector_spec = model_manager.get_crop_detector_spec(normalized_tier)
            except TypeError:
                detector_spec = model_manager.get_crop_detector_spec()
            managed_model_path = str(detector_spec.get("model_path") or "").strip()
            if managed_model_path:
                candidates.append(managed_model_path)
        except Exception:
            pass

        model_id = self._model_id_for_tier(normalized_tier)
        base_dirs = [
            "/data/models",
            str((Path(__file__).resolve().parent / "../../data/models").resolve()),
        ]
        seen: set[str] = set()
        for base_dir in base_dirs:
            normalized_base = str(base_dir or "").strip()
            if not normalized_base or normalized_base in seen:
                continue
            seen.add(normalized_base)
            candidates.extend(
                [
                    os.path.join(normalized_base, model_id, "model.onnx"),
                    os.path.join(normalized_base, f"{model_id}.onnx"),
                    os.path.join(normalized_base, model_id, f"{model_id}.onnx"),
                ]
            )
        return candidates

    def get_status(self) -> dict[str, Any]:
        try:
            from app.services.model_manager import model_manager

            try:
                status = dict(model_manager.get_crop_detector_spec("accurate") or {})
            except TypeError:
                status = dict(model_manager.get_crop_detector_spec() or {})
        except Exception:
            model_path = self._resolve_model_path(self._requested_detector_tier())
            status = {
                "model_id": self._model_id_for_tier(self._requested_detector_tier()),
                "selected_tier": self._requested_detector_tier(),
                "resolved_tier": self._requested_detector_tier(),
                "installed": model_path is not None,
                "healthy": model_path is not None,
                "enabled_for_runtime": model_path is not None,
                "reason": "ready" if model_path is not None else "not_installed",
                "model_path": str(model_path) if model_path is not None else None,
            }
        status["load_error"] = self._model_error
        status["policy"] = "accurate_then_fast"
        status["classification_candidate_policy"] = self.get_classification_candidate_crop_policy()
        status["active_providers"] = dict(self._active_providers)
        status["provider_fallbacks"] = dict(self._provider_fallbacks)
        return status

    def run_detector_outputs(self, model: Any, image: Image.Image) -> tuple[list[Any], dict[str, float]]:
        """Run one detector and return raw outputs plus its geometric transform."""
        if not isinstance(model, dict):
            raise TypeError("Raw detector output is only available for managed sessions")
        session = model.get("session")
        if session is None:
            raise RuntimeError("Detector session is not loaded")
        input_tensor, transform = self._prepare_detector_input(
            image,
            input_width=int(model.get("input_width") or 640),
            input_height=int(model.get("input_height") or 640),
            input_layout=str(model.get("input_layout") or "nchw").strip().lower(),
            input_type=str(model.get("input_type") or "tensor(float)").strip().lower(),
            dynamic_input_hw=bool(model.get("dynamic_input_hw", False)),
            preferred_input_width=int(model.get("preferred_input_width") or 0),
            preferred_input_height=int(model.get("preferred_input_height") or 0),
            preprocessing=dict(model.get("preprocessing") or {}),
        )
        outputs = session.run(None, {str(model.get("input_name") or "images"): input_tensor})
        return list(outputs or []), transform

    def _infer_candidates(self, model: Any, image: Image.Image) -> list[dict[str, Any]]:
        infer_fn = getattr(model, "infer", None)
        if callable(infer_fn):
            results = infer_fn(image)
            return list(results or [])
        if not isinstance(model, dict):
            return []
        output_names = [str(name or "") for name in (model.get("output_names") or [])]
        detector_config = dict(model.get("detector_config") or {})
        outputs, transform = self.run_detector_outputs(model, image)
        return self._parse_detector_outputs(
            outputs,
            transform=transform,
            image_size=image.size,
            output_names=output_names,
            detector_tier=str(model.get("detector_tier") or self._requested_detector_tier()),
            detector_config=detector_config,
        )

    def _import_onnxruntime(self):
        return importlib.import_module("onnxruntime")

    def _infer_input_layout(self, shape: Any) -> str:
        if isinstance(shape, (list, tuple)) and len(shape) >= 4:
            last_dim = shape[-1]
            try:
                if int(last_dim) == 3:
                    return "nhwc"
            except (TypeError, ValueError):
                pass
        return "nchw"

    def _has_dynamic_hw(self, shape: Any, *, layout: str = "nchw") -> bool:
        if not isinstance(shape, (list, tuple)) or len(shape) < 4:
            return False
        if layout == "nhwc":
            values = (shape[1], shape[2])
        else:
            values = (shape[2], shape[3])
        for value in values:
            try:
                int(value)
            except (TypeError, ValueError):
                return True
        return False

    def _resolve_input_hw(self, shape: Any, *, layout: str = "nchw") -> tuple[int, int]:
        if isinstance(shape, (list, tuple)) and len(shape) >= 4:
            candidates: list[tuple[Any, Any]] = []
            if layout == "nhwc":
                candidates.append((shape[1], shape[2]))
                candidates.append((shape[2], shape[3]))
            else:
                candidates.append((shape[2], shape[3]))
                candidates.append((shape[1], shape[2]))
            for raw_height, raw_width in candidates:
                try:
                    height = int(raw_height)
                    width = int(raw_width)
                except (TypeError, ValueError):
                    continue
                if height > 0 and width > 0 and height != 3 and width != 3:
                    return height, width
        return 640, 640

    def _prepare_detector_input(
        self,
        image: Image.Image,
        *,
        input_width: int,
        input_height: int,
        input_layout: str = "nchw",
        input_type: str = "tensor(float)",
        dynamic_input_hw: bool = False,
        preferred_input_width: int = 0,
        preferred_input_height: int = 0,
        preprocessing: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, float]]:
        preprocessing = dict(preprocessing or {})
        rgb = image.convert("RGB")
        src_w, src_h = rgb.size
        if input_layout == "nhwc" and input_type == "tensor(uint8)":
            if dynamic_input_hw and preferred_input_width > 0 and preferred_input_height > 0:
                prepared = rgb.resize((preferred_input_width, preferred_input_height), Image.Resampling.BILINEAR)
                scale_x = float(preferred_input_width) / float(src_w)
                scale_y = float(preferred_input_height) / float(src_h)
                resize_mode = "direct_resize"
            elif dynamic_input_hw:
                prepared = rgb
                scale_x = 1.0
                scale_y = 1.0
                resize_mode = "native"
            else:
                prepared = rgb.resize((input_width, input_height), Image.Resampling.BILINEAR)
                scale_x = float(input_width) / float(src_w)
                scale_y = float(input_height) / float(src_h)
                resize_mode = "direct_resize"
            arr = np.asarray(prepared, dtype=np.uint8)[None, ...]
            return arr, {
                "scale": 1.0,
                "scale_x": float(scale_x),
                "scale_y": float(scale_y),
                "pad_x": 0.0,
                "pad_y": 0.0,
                "normalized_yxyx": False,
                "resize_mode": resize_mode,
                "input_width": float(prepared.size[0]),
                "input_height": float(prepared.size[1]),
                "pad_alignment": "center",
            }
        resize_mode = str(preprocessing.get("resize_mode") or "letterbox").strip().lower()
        color_space = str(preprocessing.get("color_space") or "RGB").strip().upper()
        normalization = str(preprocessing.get("normalization") or "float32_0_1").strip().lower()
        pad_alignment = str(preprocessing.get("pad_alignment") or "center").strip().lower()
        scale = min(float(input_width) / float(src_w), float(input_height) / float(src_h))
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        resized = rgb.resize((resized_w, resized_h), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (input_width, input_height), color=(114, 114, 114))
        if resize_mode == "direct_resize":
            pad_x = 0
            pad_y = 0
        elif pad_alignment == "top_left":
            pad_x = 0
            pad_y = 0
        else:
            pad_x = int(round((input_width - resized_w) / 2.0))
            pad_y = int(round((input_height - resized_h) / 2.0))
        canvas.paste(resized, (pad_x, pad_y))

        arr = np.asarray(canvas, dtype=np.float32)
        if color_space == "BGR":
            arr = arr[:, :, ::-1]
        if normalization in {"float32", "float32_0_1", "0_1"}:
            arr /= 255.0
        arr = np.transpose(arr, (2, 0, 1))[None, ...]
        return arr, {
            "scale": float(scale),
            "scale_x": float(scale),
            "scale_y": float(scale),
            "pad_x": float(pad_x),
            "pad_y": float(pad_y),
            "normalized_yxyx": False,
            "resize_mode": resize_mode,
            "input_width": float(input_width),
            "input_height": float(input_height),
            "pad_alignment": pad_alignment,
        }

    def _parse_detector_outputs(
        self,
        outputs: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        output_names: list[str] | None = None,
        detector_tier: str | None = None,
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(outputs, (list, tuple)) or not outputs:
            return []
        normalized_detector_tier = str(detector_tier or "").strip().lower()
        detector_config = dict(detector_config or {})
        parser = str(detector_config.get("parser") or "").strip().lower()
        if parser == "yolox" or normalized_detector_tier == "accurate":
            parsed = self._parse_yolox_detection_outputs(
                outputs[0],
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
            if parsed or self._looks_like_yolox_tensor(outputs[0]):
                return parsed
        parsed, matched_named_route = self._parse_named_detection_outputs(
            outputs,
            transform=transform,
            image_size=image_size,
            output_names=output_names or [],
            detector_config=detector_config,
        )
        if matched_named_route:
            return parsed
        parsed = self._parse_single_tensor_detections(
            outputs[0],
            transform=transform,
            image_size=image_size,
            detector_config=detector_config,
        )
        if parsed:
            return parsed
        if len(outputs) >= 2:
            parsed = self._parse_split_tensor_detections(
                outputs,
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
            if parsed:
                return parsed
        return []

    def _parse_named_detection_outputs(
        self,
        outputs: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        output_names: list[str],
        detector_config: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        normalized_names = [name.strip().lower() for name in output_names]
        if not normalized_names:
            return [], False
        by_name = {name: outputs[idx] for idx, name in enumerate(normalized_names) if idx < len(outputs)}
        if {"detection_boxes", "detection_classes", "detection_scores"} <= set(by_name.keys()):
            return self._parse_ssd_detection_outputs(
                boxes_output=by_name["detection_boxes"],
                classes_output=by_name["detection_classes"],
                scores_output=by_name["detection_scores"],
                count_output=by_name.get("num_detections"),
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            ), True
        return [], False

    def _parse_ssd_detection_outputs(
        self,
        *,
        boxes_output: Any,
        classes_output: Any,
        scores_output: Any,
        count_output: Any,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            boxes = np.asarray(boxes_output).reshape(-1, 4)
            classes = np.asarray(classes_output).reshape(-1)
            scores = np.asarray(scores_output).reshape(-1)
        except Exception:
            return []
        count = min(len(boxes), len(classes), len(scores))
        if count_output is not None:
            try:
                reported = int(float(np.asarray(count_output).reshape(-1)[0]))
                if reported >= 0:
                    count = min(count, reported)
            except Exception:
                pass
        candidates: list[dict[str, Any]] = []
        target_class_id = self._resolve_target_class_id(detector_config)
        for idx in range(count):
            class_id = self._finite_float(classes[idx])
            confidence = self._finite_float(scores[idx])
            if class_id is None or confidence is None:
                continue
            if int(round(class_id)) != target_class_id:
                continue
            box = self._restore_box_to_image(
                boxes[idx],
                transform={
                    **transform,
                    "normalized_yxyx": True,
                },
                image_size=image_size,
                detector_config=detector_config,
            )
            if box is None:
                continue
            candidates.append({"box": box, "confidence": confidence})
        return candidates

    def _looks_like_yolox_tensor(self, output: Any) -> bool:
        try:
            arr = np.asarray(output)
        except Exception:
            return False
        if arr.size == 0 or arr.ndim < 2:
            return False
        return int(arr.shape[-1]) in {6, 7, 85} or int(arr.shape[-2]) in {6, 7, 85}

    def _parse_yolox_detection_outputs(
        self,
        output: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            arr = np.asarray(output)
        except Exception:
            return []
        if arr.size == 0:
            return []
        if arr.ndim >= 2 and arr.shape[-1] not in {6, 7} and arr.shape[-2] in {6, 7}:
            arr = np.swapaxes(arr, -1, -2)
        if arr.shape[-1] > 7:
            return self._parse_yolox_raw_grid_outputs(
                arr,
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
        if arr.shape[-1] not in {6, 7}:
            return []
        rows = arr.reshape(-1, arr.shape[-1])
        candidates: list[dict[str, Any]] = []
        target_class_id = self._resolve_target_class_id(detector_config)
        confidence_mode = str((detector_config or {}).get("confidence_mode") or "object_times_class").strip().lower()
        for row in rows:
            if row.shape[0] == 6:
                confidence = self._finite_float(row[4])
                class_id = self._finite_float(row[5])
            elif row.shape[0] == 7:
                object_confidence = self._finite_float(row[4])
                class_confidence = self._finite_float(row[5])
                class_id = self._finite_float(row[6])
                if object_confidence is None or class_confidence is None:
                    continue
                if confidence_mode == "score":
                    confidence = float(class_confidence)
                elif confidence_mode == "object":
                    confidence = float(object_confidence)
                else:
                    confidence = float(object_confidence * class_confidence)
            else:
                continue
            if confidence is None or class_id is None:
                continue
            if int(round(class_id)) != target_class_id:
                continue
            box = self._restore_box_to_image(
                row[:4],
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
            if box is None:
                continue
            candidates.append({"box": box, "confidence": confidence})
        return candidates

    def _parse_yolox_raw_grid_outputs(
        self,
        output: np.ndarray,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        arr = np.asarray(output, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2 or arr.shape[-1] <= 5:
            return []

        img_h = int(round(float(transform.get("input_height") or 0.0)))
        img_w = int(round(float(transform.get("input_width") or 0.0)))
        if img_h <= 0 or img_w <= 0:
            img_h = int(
                round(
                    float(transform.get("scale_y") or transform.get("scale") or 1.0) * float(image_size[1])
                    + float(transform.get("pad_y") or 0.0) * 2.0
                )
            )
            img_w = int(
                round(
                    float(transform.get("scale_x") or transform.get("scale") or 1.0) * float(image_size[0])
                    + float(transform.get("pad_x") or 0.0) * 2.0
                )
            )
        decoded = self._decode_yolox_predictions(arr.copy(), input_size=(img_h, img_w))
        if decoded is None:
            return []

        target_class_id = self._resolve_target_class_id(detector_config)
        scores = decoded[:, 4] * decoded[:, 5 + target_class_id]
        valid_mask = np.isfinite(scores) & (scores > 0.0)
        if not np.any(valid_mask):
            return []

        decoded = decoded[valid_mask]
        scores = scores[valid_mask]
        keep = self._single_class_nms_cxcywh(decoded[:, :4], scores, iou_threshold=0.45)
        candidates: list[dict[str, Any]] = []
        cxcywh_config = {**dict(detector_config or {}), "box_format": "cxcywh"}
        for idx in keep:
            confidence = self._finite_float(scores[idx])
            if confidence is None:
                continue
            box = self._restore_box_to_image(
                decoded[idx, :4],
                transform=transform,
                image_size=image_size,
                detector_config=cxcywh_config,
            )
            if box is None:
                continue
            candidates.append({"box": box, "confidence": confidence})
        return candidates

    def _decode_yolox_predictions(self, predictions: np.ndarray, *, input_size: tuple[int, int]) -> np.ndarray | None:
        strides = [8, 16, 32]
        grids: list[np.ndarray] = []
        expanded_strides: list[np.ndarray] = []
        hsize_total = 0
        expected_predictions = 0
        for stride in strides:
            hsize = input_size[0] // stride
            wsize = input_size[1] // stride
            yv, xv = np.meshgrid(np.arange(hsize), np.arange(wsize), indexing="ij")
            grid = np.stack((xv, yv), axis=2).reshape(-1, 2)
            grids.append(grid)
            expanded_strides.append(np.full((grid.shape[0], 1), stride, dtype=np.float32))
            expected_predictions += grid.shape[0]
            hsize_total += hsize * wsize
        if predictions.shape[0] != expected_predictions:
            return None
        grid = np.concatenate(grids, axis=0).astype(np.float32)
        stride = np.concatenate(expanded_strides, axis=0).astype(np.float32)
        predictions[:, :2] = (predictions[:, :2] + grid) * stride
        predictions[:, 2:4] = np.exp(predictions[:, 2:4]) * stride
        return predictions

    def _single_class_nms_cxcywh(self, boxes: np.ndarray, scores: np.ndarray, *, iou_threshold: float) -> list[int]:
        if boxes.size == 0 or scores.size == 0:
            return []
        x1 = boxes[:, 0] - (boxes[:, 2] / 2.0)
        y1 = boxes[:, 1] - (boxes[:, 3] / 2.0)
        x2 = boxes[:, 0] + (boxes[:, 2] / 2.0)
        y2 = boxes[:, 1] + (boxes[:, 3] / 2.0)
        areas = np.maximum(0.0, x2 - x1 + 1.0) * np.maximum(0.0, y2 - y1 + 1.0)
        order = scores.argsort()[::-1]
        keep: list[int] = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1.0)
            h = np.maximum(0.0, yy2 - yy1 + 1.0)
            inter = w * h
            union = areas[i] + areas[order[1:]] - inter
            iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0.0)
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        return keep

    def _resolve_target_class_id(self, detector_config: dict[str, Any] | None = None) -> int:
        config_class_id = (detector_config or {}).get("target_class_id")
        try:
            if config_class_id is not None:
                return int(config_class_id)
        except (TypeError, ValueError):
            pass
        raw = os.getenv("BIRD_CROP_CLASS_ID")
        try:
            return int(raw) if raw is not None else 16
        except (TypeError, ValueError):
            return 16

    def _parse_single_tensor_detections(
        self,
        output: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            arr = np.asarray(output)
        except Exception:
            return []
        if arr.size == 0:
            return []
        if arr.ndim >= 2 and arr.shape[-1] < 5 and arr.shape[-2] >= 5:
            arr = np.swapaxes(arr, -1, -2)
        if arr.shape[-1] < 5:
            return []
        rows = arr.reshape(-1, arr.shape[-1])
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if row.shape[0] < 5 or row.shape[0] > 6:
                continue
            confidence = self._finite_float(row[4])
            if confidence is None:
                continue
            box = self._restore_box_to_image(
                row[:4],
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
            if box is None:
                continue
            candidates.append({"box": box, "confidence": confidence})
        return candidates

    def _parse_split_tensor_detections(
        self,
        outputs: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            boxes = np.asarray(outputs[0]).reshape(-1, 4)
            scores = np.asarray(outputs[1]).reshape(-1)
        except Exception:
            return []
        count = min(len(boxes), len(scores))
        candidates: list[dict[str, Any]] = []
        for idx in range(count):
            confidence = self._finite_float(scores[idx])
            if confidence is None:
                continue
            box = self._restore_box_to_image(
                boxes[idx],
                transform=transform,
                image_size=image_size,
                detector_config=detector_config,
            )
            if box is None:
                continue
            candidates.append({"box": box, "confidence": confidence})
        return candidates

    def _restore_box_to_image(
        self,
        box: Any,
        *,
        transform: dict[str, float],
        image_size: tuple[int, int],
        detector_config: dict[str, Any] | None = None,
    ) -> tuple[float, float, float, float] | None:
        try:
            left, top, right, bottom = [float(value) for value in box[:4]]
        except Exception:
            return None
        box_format = (
            str((detector_config or {}).get("box_format") or os.getenv("BIRD_CROP_BOX_FORMAT") or "xyxy")
            .strip()
            .lower()
        )
        if box_format == "cxcywh":
            center_x, center_y, width, height = left, top, right, bottom
            left = center_x - (width / 2.0)
            right = center_x + (width / 2.0)
            top = center_y - (height / 2.0)
            bottom = center_y + (height / 2.0)
        if not all(math.isfinite(value) for value in (left, top, right, bottom)):
            return None
        scale = float(transform.get("scale") or 1.0)
        scale_x = float(transform.get("scale_x") or scale or 1.0)
        scale_y = float(transform.get("scale_y") or scale or 1.0)
        pad_x = float(transform.get("pad_x") or 0.0)
        pad_y = float(transform.get("pad_y") or 0.0)
        normalized_yxyx = bool(transform.get("normalized_yxyx"))
        resize_mode = str(transform.get("resize_mode") or "letterbox").strip().lower()
        if normalized_yxyx:
            image_width, image_height = image_size
            top_norm, left_norm, bottom_norm, right_norm = left, top, right, bottom
            left = left_norm * float(image_width)
            right = right_norm * float(image_width)
            top = top_norm * float(image_height)
            bottom = bottom_norm * float(image_height)
            scale_x = 1.0
            scale_y = 1.0
            pad_x = 0.0
            pad_y = 0.0
        if scale_x <= 0.0 or scale_y <= 0.0:
            return None
        if resize_mode == "direct_resize":
            left = left / scale_x
            right = right / scale_x
            top = top / scale_y
            bottom = bottom / scale_y
        else:
            left = (left - pad_x) / scale_x
            right = (right - pad_x) / scale_x
            top = (top - pad_y) / scale_y
            bottom = (bottom - pad_y) / scale_y
        width, height = image_size
        left = max(0.0, min(float(width), left))
        right = max(0.0, min(float(width), right))
        top = max(0.0, min(float(height), top))
        bottom = max(0.0, min(float(height), bottom))
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom

    def _finite_float(self, value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    def _select_candidate(self, candidates: Any) -> dict[str, Any] | None:
        if not candidates:
            return None

        normalized: list[dict[str, Any]] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                normalized.append(candidate)

        normalized.sort(key=lambda candidate: self._coerce_confidence(candidate) or float("-inf"), reverse=True)
        return normalized[0] if normalized else None

    def _select_best_valid_candidate(
        self,
        image: Image.Image,
        candidates: Any,
        *,
        detector_tier: str | None,
        fallback_reason: str | None,
        confidence_threshold_ceiling: float | None = None,
        min_crop_size_ceiling: int | None = None,
        minimum_output_size: int | None = None,
    ) -> dict[str, Any]:
        crop_policy = self.get_effective_crop_policy(detector_tier)
        confidence_threshold = float(crop_policy["confidence_threshold"])
        if confidence_threshold_ceiling is not None:
            try:
                ceiling = float(confidence_threshold_ceiling)
            except (TypeError, ValueError):
                ceiling = confidence_threshold
            if math.isfinite(ceiling) and ceiling >= 0.0:
                confidence_threshold = min(confidence_threshold, ceiling)
        min_crop_size = int(crop_policy["min_crop_size"])
        if min_crop_size_ceiling is not None:
            try:
                min_crop_size = min(min_crop_size, max(1, int(min_crop_size_ceiling)))
            except (TypeError, ValueError):
                pass
        normalized: list[dict[str, Any]] = []
        for candidate in candidates or []:
            if isinstance(candidate, dict):
                normalized.append(candidate)
        normalized.sort(key=lambda candidate: self._coerce_confidence(candidate) or float("-inf"), reverse=True)

        highest_confidence: float | None = None
        failure_reason: str | None = None
        failure_confidence: float | None = None
        for candidate in normalized:
            confidence = self._coerce_confidence(candidate)
            if confidence is None:
                continue
            if highest_confidence is None:
                highest_confidence = confidence
            if confidence < confidence_threshold:
                break

            raw_box = self._extract_box(candidate)
            if raw_box is None:
                if failure_reason is None:
                    failure_reason = "invalid_box"
                    failure_confidence = confidence
                continue

            box = self._normalize_box(raw_box)
            if box is None:
                if failure_reason is None:
                    failure_reason = "invalid_box"
                    failure_confidence = confidence
                continue

            left, top, right, bottom = box
            if (right - left) < min_crop_size or (bottom - top) < min_crop_size:
                if failure_reason is None:
                    failure_reason = "too_small"
                    failure_confidence = confidence
                continue

            expanded = self._expand_and_clamp_box(box, image.size)
            if expanded is None:
                if failure_reason is None:
                    failure_reason = "invalid_box"
                    failure_confidence = confidence
                continue

            if minimum_output_size is not None:
                expanded = self._expand_box_to_minimum_size(
                    expanded,
                    image.size,
                    minimum_size=max(1, int(minimum_output_size)),
                )
                if expanded is None:
                    if failure_reason is None:
                        failure_reason = "invalid_box"
                        failure_confidence = confidence
                    continue

            crop_width = expanded[2] - expanded[0]
            crop_height = expanded[3] - expanded[1]
            if crop_width < 1 or crop_height < 1:
                if failure_reason is None:
                    failure_reason = "invalid_box"
                    failure_confidence = confidence
                continue
            if crop_width < min_crop_size or crop_height < min_crop_size:
                if failure_reason is None:
                    failure_reason = "too_small"
                    failure_confidence = confidence
                continue

            crop_image = image.crop(expanded)
            return {
                "crop_image": crop_image,
                "box": expanded,
                "confidence": confidence,
                "reason": "selected",
                "detector_tier": detector_tier,
                "fallback_reason": fallback_reason,
            }

        if highest_confidence is not None and highest_confidence < confidence_threshold:
            return self._empty_result(
                "below_threshold",
                confidence=highest_confidence,
                detector_tier=detector_tier,
                fallback_reason=fallback_reason,
            )
        if failure_reason is not None:
            return self._empty_result(
                failure_reason,
                confidence=failure_confidence,
                detector_tier=detector_tier,
                fallback_reason=fallback_reason,
            )
        return self._empty_result(
            "no_candidate",
            detector_tier=detector_tier,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _expand_box_to_minimum_size(
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
        *,
        minimum_size: int,
    ) -> tuple[int, int, int, int] | None:
        left, top, right, bottom = box
        image_width, image_height = image_size
        if right <= left or bottom <= top or image_width <= 0 or image_height <= 0:
            return None
        target_width = min(int(image_width), max(right - left, int(minimum_size)))
        target_height = min(int(image_height), max(bottom - top, int(minimum_size)))
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0
        expanded_left = int(math.floor(center_x - target_width / 2.0))
        expanded_top = int(math.floor(center_y - target_height / 2.0))
        expanded_left = min(max(0, expanded_left), int(image_width) - target_width)
        expanded_top = min(max(0, expanded_top), int(image_height) - target_height)
        return (
            expanded_left,
            expanded_top,
            expanded_left + target_width,
            expanded_top + target_height,
        )

    def _coerce_confidence(self, candidate: Any) -> float | None:
        if not isinstance(candidate, dict):
            return None
        value = candidate.get("confidence", candidate.get("score"))
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(confidence):
            return None
        return confidence

    def _extract_box(self, candidate: dict[str, Any]) -> tuple[float, float, float, float] | None:
        box = candidate.get("box")
        if box is None:
            box = candidate.get("bbox")
        if box is None:
            box = candidate.get("xyxy")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            return None
        try:
            left = float(box[0])
            top = float(box[1])
            right = float(box[2])
            bottom = float(box[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, right, bottom)):
            return None
        return left, top, right, bottom

    def _normalize_box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int] | None:
        left, top, right, bottom = box
        left_i = int(math.floor(left))
        top_i = int(math.floor(top))
        right_i = int(math.ceil(right))
        bottom_i = int(math.ceil(bottom))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _expand_and_clamp_box(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None

        pad_x = int(round(width * self.expand_ratio))
        pad_y = int(round(height * self.expand_ratio))

        expanded_left = max(0, left - pad_x)
        expanded_top = max(0, top - pad_y)
        expanded_right = min(int(image_size[0]), right + pad_x)
        expanded_bottom = min(int(image_size[1]), bottom + pad_y)

        if expanded_right <= expanded_left or expanded_bottom <= expanded_top:
            return None
        return expanded_left, expanded_top, expanded_right, expanded_bottom

    def _empty_result(
        self,
        reason: str,
        *,
        confidence: float | None = None,
        detector_tier: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        if not self.fallback_to_original:
            reason = f"{reason}_no_fallback"
        return {
            "crop_image": None,
            "box": None,
            "confidence": confidence if confidence is not None and math.isfinite(confidence) else None,
            "reason": reason,
            "detector_tier": detector_tier,
            "fallback_reason": fallback_reason,
        }


bird_crop_service = BirdCropService()
