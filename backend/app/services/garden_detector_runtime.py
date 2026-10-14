"""Qualified RGB letterbox and raw three-class detector contract.

Native inference belongs in the disposable motion worker, never the API process.
"""

import cv2
import math
import numpy as np

DetectorMeta = tuple[int, int, float, int, int]
DetectorCandidate = tuple[str, float, tuple[float, float, float, float]]


def detector_input(image: np.ndarray) -> tuple[np.ndarray, DetectorMeta]:
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("Detector input must be uint8 RGB")
    height, width = image.shape[:2]
    if min(width, height) < 1 or width * height > 16_000_000:
        raise ValueError("Detector image exceeds the pixel limit")
    scale = min(640 / width, 640 / height)
    resized_width, resized_height = round(width * scale), round(height * scale)
    left, top = round((640 - resized_width) / 2 - 0.1), round((640 - resized_height) / 2 - 0.1)
    resized = cv2.resize(image, (resized_width, resized_height))
    padded = cv2.copyMakeBorder(
        resized,
        top,
        640 - resized_height - top,
        left,
        640 - resized_width - left,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    value = np.ascontiguousarray(padded.transpose(2, 0, 1)[None].astype(np.float32) / 255)
    return value, (width, height, scale, left, top)


def decode_candidates(
    output: np.ndarray, meta: DetectorMeta, names: list[str], animal_confidence: float = 0.5
) -> list[DetectorCandidate]:
    if (
        type(animal_confidence) not in (float, int)
        or not math.isfinite(animal_confidence)
        or not 0.5 <= animal_confidence <= 0.95
    ):
        raise ValueError("Animal confidence must be between 0.5 and 0.95")
    if names != ["animal", "person", "vehicle"]:
        raise ValueError("Detector catalogue outputs differ from the qualified model contract")
    if output.ndim != 3 or output.shape[:2] != (1, 7) or not np.isfinite(output).all():
        raise ValueError("Expected a finite raw three-class detector head")
    raw = output[0].T
    if np.any(raw[:, 4:] < 0) or np.any(raw[:, 4:] > 1) or np.any(raw[:, 2:4] < 0):
        raise ValueError("Detector returned invalid probabilities or dimensions")
    width, height, scale, left, top = meta
    candidates: list[DetectorCandidate] = []
    for index, (name, threshold) in enumerate(zip(names, (animal_confidence, 0.2, 0.4))):
        selected = raw[raw[:, 4 + index] >= threshold]
        if not len(selected):
            continue
        boxes = selected[:, :4].copy()
        boxes[:, :2] -= boxes[:, 2:] / 2
        scores = selected[:, 4 + index]
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), threshold, 0.45)
        for chosen in np.asarray(keep, dtype=int).reshape(-1)[:100]:
            x, y, w, h = boxes[chosen]
            x1, y1 = max(0.0, (float(x) - left) / scale / width), max(0.0, (float(y) - top) / scale / height)
            x2, y2 = min(1.0, (float(x + w) - left) / scale / width), min(1.0, (float(y + h) - top) / scale / height)
            if x2 > x1 and y2 > y1:
                candidates.append((name, float(scores[chosen]), (x1, y1, x2 - x1, y2 - y1)))
    # Limits apply per class so stronger animal scores cannot hide a person veto.
    return sorted(candidates, key=lambda item: -item[1])
