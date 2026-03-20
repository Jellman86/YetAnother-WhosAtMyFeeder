from __future__ import annotations

import math
import os
import threading
from typing import Any, Callable

import structlog
from PIL import Image

log = structlog.get_logger()


class BirdCropService:
    """Fail-soft helper for producing a tighter bird crop."""

    def __init__(
        self,
        *,
        model_id: str = "bird_crop",
        confidence_threshold: float = 0.35,
        expand_ratio: float = 0.12,
        min_crop_size: int = 96,
        fallback_to_original: bool = True,
        model_loader: Callable[[], Any] | None = None,
    ):
        self.model_id = str(model_id or "bird_crop")
        self.confidence_threshold = float(confidence_threshold)
        self.expand_ratio = max(0.0, float(expand_ratio))
        self.min_crop_size = max(1, int(min_crop_size))
        self.fallback_to_original = bool(fallback_to_original)
        self._model_loader = model_loader
        self._model_lock = threading.Lock()
        self._model: Any | None = None
        self._model_loaded = False
        self._model_error: str | None = None

    def generate_crop(self, image: Image.Image) -> dict[str, Any]:
        """Return the best crop candidate or a fail-soft empty result."""
        if not isinstance(image, Image.Image):
            return self._empty_result("invalid_image")

        try:
            model = self._ensure_model()
        except Exception as exc:  # pragma: no cover - defensive guard
            self._model_error = str(exc)
            log.warning("Bird crop model load failed", model_id=self.model_id, error=str(exc))
            return self._empty_result("load_failed")

        if model is None:
            return self._empty_result("load_failed")

        try:
            candidates = self._infer_candidates(model, image)
        except Exception as exc:
            log.warning("Bird crop inference failed", model_id=self.model_id, error=str(exc))
            return self._empty_result("inference_failed")

        candidate = self._select_candidate(candidates)
        if candidate is None:
            return self._empty_result("no_candidate")

        confidence = self._coerce_confidence(candidate)
        if confidence is None or confidence < self.confidence_threshold:
            return self._empty_result("below_threshold", confidence=confidence)

        raw_box = self._extract_box(candidate)
        if raw_box is None:
            return self._empty_result("invalid_box", confidence=confidence)

        box = self._normalize_box(raw_box)
        if box is None:
            return self._empty_result("invalid_box", confidence=confidence)

        left, top, right, bottom = box
        if (right - left) < self.min_crop_size or (bottom - top) < self.min_crop_size:
            return self._empty_result("too_small", confidence=confidence)

        expanded = self._expand_and_clamp_box(box, image.size)
        if expanded is None:
            return self._empty_result("invalid_box", confidence=confidence)

        crop_width = expanded[2] - expanded[0]
        crop_height = expanded[3] - expanded[1]
        if crop_width < 1 or crop_height < 1:
            return self._empty_result("invalid_box", confidence=confidence)
        if crop_width < self.min_crop_size or crop_height < self.min_crop_size:
            return self._empty_result("too_small", confidence=confidence)

        crop_image = image.crop(expanded)
        return {
            "crop_image": crop_image,
            "box": expanded,
            "confidence": confidence,
            "reason": "selected",
        }

    def _ensure_model(self) -> Any | None:
        if self._model_loaded:
            return self._model

        with self._model_lock:
            if self._model_loaded:
                return self._model
            self._model = self._load_model()
            self._model_loaded = True
            return self._model

    def _load_model(self) -> Any | None:
        """Placeholder loader for later model/runtime integration."""
        if self._model_loader is not None:
            return self._model_loader()
        model_path = os.getenv("BIRD_CROP_MODEL_PATH")
        if not model_path:
            return None
        if not os.path.exists(model_path):
            return None
        raise RuntimeError("Bird crop runtime integration is not wired yet")

    def _infer_candidates(self, model: Any, image: Image.Image) -> list[dict[str, Any]]:
        """Placeholder inference hook for later runtime integration."""
        infer_fn = getattr(model, "infer", None)
        if callable(infer_fn):
            results = infer_fn(image)
            return list(results or [])
        return []

    def _select_candidate(self, candidates: Any) -> dict[str, Any] | None:
        if not candidates:
            return None

        normalized: list[dict[str, Any]] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                normalized.append(candidate)

        normalized.sort(key=lambda candidate: self._coerce_confidence(candidate) or float("-inf"), reverse=True)
        return normalized[0] if normalized else None

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

    def _empty_result(self, reason: str, *, confidence: float | None = None) -> dict[str, Any]:
        if not self.fallback_to_original:
            reason = f"{reason}_no_fallback"
        return {
            "crop_image": None,
            "box": None,
            "confidence": confidence if confidence is not None and math.isfinite(confidence) else None,
            "reason": reason,
        }


bird_crop_service = BirdCropService()
