"""Compare photographs independently of the classification winner."""

from collections.abc import Mapping
import math
from typing import Any

import cv2
import numpy as np
from PIL import Image

PHOTO_REPLACEMENT_MARGIN = 0.02


def image_quality_score(image: Image.Image) -> float:
    grayscale = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    scale = 256 / max(image.size)
    normalized = cv2.resize(
        grayscale,
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    sharpness = float(cv2.Laplacian(normalized, cv2.CV_64F).var())
    sharpness_score = min(1.0, math.log1p(max(0.0, sharpness)) / math.log1p(1000.0))
    exposure = float(((grayscale >= 8) & (grayscale <= 247)).mean())
    resolution = min(1.0, math.sqrt(image.width * image.height) / 512.0)
    return sharpness_score * 0.45 + exposure * 0.35 + resolution * 0.20


_WEIGHTS = {"classifier_score": 0.65, "image_quality_score": 0.25, "crop_confidence": 0.10}


def _value(candidate: Mapping[str, Any], key: str) -> float | None:
    raw = candidate.get(key)
    return float(raw) if type(raw) in {int, float} and math.isfinite(raw) and 0 <= raw <= 1 else None


def _score(candidate: Mapping[str, Any], keys: tuple[str, ...]) -> float:
    total = sum(_WEIGHTS[key] for key in keys)
    return sum(_WEIGHTS[key] * (_value(candidate, key) or 0.0) for key in keys) / total


def materially_improves_photo(challenger: Mapping[str, Any], incumbent: Mapping[str, Any]) -> bool:
    """True when the challenger is clearly the better photograph, not merely a marginal winner.

    Only measures both sides carry are compared, so a photograph is never judged on a quality
    that was not measured for it. The classifier score is always part of the comparison.
    """
    keys = tuple(
        key
        for key in _WEIGHTS
        if key == "classifier_score" or (_value(challenger, key) is not None and _value(incumbent, key) is not None)
    )
    return _score(challenger, keys) > _score(incumbent, keys) + PHOTO_REPLACEMENT_MARGIN
