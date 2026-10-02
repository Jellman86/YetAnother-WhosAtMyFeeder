"""Object-location evidence is separate from species confidence."""

from collections.abc import Mapping
import math
from typing import Any

from app.services.bird_observation_selection import MIN_DETECTOR_CONFIDENCE

DETECTOR_PHOTO_STRATEGY = "detector_supported"


def _valid_box(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(type(coordinate) is int for coordinate in value)
        and 0 <= value[0] < value[2]
        and 0 <= value[1] < value[3]
    )


def has_localized_bird(evidence: Mapping[str, Any]) -> bool:
    if evidence.get("presence_source") != "bird_crop_detector":
        return False
    confidence = evidence.get("detector_confidence")
    if not _usable_confidence(confidence):
        return False
    width, height = evidence.get("frame_width"), evidence.get("frame_height")
    bird = evidence.get("bird_box")
    crop = evidence.get("crop_box")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        return False
    if not _valid_box(bird) or bird[2] > width or bird[3] > height:
        return False
    if crop is None:
        return not evidence.get("input_is_cropped")
    if not _valid_box(crop) or crop[2] > width or crop[3] > height:
        return False
    overlap = max(0, min(bird[2], crop[2]) - max(bird[0], crop[0])) * max(
        0, min(bird[3], crop[3]) - max(bird[1], crop[1])
    )
    return overlap >= (bird[2] - bird[0]) * (bird[3] - bird[1]) * 0.5


def has_reusable_bird_presence(candidate: Mapping[str, Any]) -> bool:
    confidence = candidate.get("crop_confidence")
    if not _usable_confidence(confidence):
        return False
    mode = candidate.get("source_mode")
    box = candidate.get("crop_box")
    if mode == "model_crop":
        return _valid_box(box)
    if candidate.get("crop_strategy") != DETECTOR_PHOTO_STRATEGY:
        return False
    return (mode == "full_frame" and box is None) or (mode == "frigate_hint_crop" and _valid_box(box))


def attach_photo_presence(candidates: list[dict[str, Any]], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reuse detector work from this exact moment without rescanning photographs."""
    located = [
        dict(item)
        for item in candidates + observations
        if item.get("source_mode") in {"model_crop", "model_observation"}
    ]
    supported = []
    for candidate in candidates:
        frame = (candidate.get("clip_variant"), candidate.get("frame_index"))
        if not isinstance(frame[0], str) or type(frame[1]) is not int:
            continue
        for bird in located:
            if candidate.get("source_mode") == "model_crop" and bird.get("candidate_id") != candidate.get(
                "candidate_id"
            ):
                continue
            if frame != (bird.get("clip_variant"), bird.get("frame_index")):
                continue
            evidence = {
                **candidate,
                "presence_source": "bird_crop_detector",
                "bird_box": bird.get("crop_box")
                if bird.get("source_mode") == "model_observation"
                else bird.get("detector_box"),
                "detector_confidence": bird.get("crop_confidence"),
                "input_is_cropped": candidate.get("input_is_cropped") is True
                or candidate.get("source_mode") != "full_frame",
            }
            if has_localized_bird(evidence):
                candidate["crop_strategy"] = DETECTOR_PHOTO_STRATEGY
                candidate["crop_confidence"] = bird.get("crop_confidence")
                supported.append(candidate)
                break
    return supported


def _usable_confidence(confidence: object) -> bool:
    return type(confidence) in {int, float} and math.isfinite(confidence) and MIN_DETECTOR_CONFIDENCE <= confidence <= 1


def has_confident_photo_species(candidate: Mapping[str, Any], *, threshold: float) -> bool:
    score = candidate.get("classifier_score")
    return type(score) in {int, float} and math.isfinite(score) and max(0.6, threshold) <= score <= 1.0
