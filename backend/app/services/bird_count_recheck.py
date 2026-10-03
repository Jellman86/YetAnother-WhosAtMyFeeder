"""Choose bounded search hints; only a new same-frame detection can add a bird."""

from collections.abc import Mapping
import math
from typing import Any

from app.services.bird_observation_selection import MIN_DETECTOR_CONFIDENCE, MIN_SPECIES_CONFIDENCE

MAX_COUNT_RECHECKS = 4
MAX_NEIGHBOR_SECONDS = 10.0
MIN_EXPLORATORY_CONFIDENCE = 0.02


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _box(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(_number(v) is None for v in value):
        return None
    if not (0 <= value[0] < value[2] and 0 <= value[1] < value[3]):
        return None
    return tuple(float(v) for v in value)


def _area(box: tuple[float, ...]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _intersection(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )


def _compatible(left: tuple[float, ...], right: tuple[float, ...], *, minimum_area_ratio: float) -> bool:
    smaller, larger = sorted((_area(left), _area(right)))
    return smaller / larger >= minimum_area_ratio and _intersection(left, right) / smaller >= 0.6


def _same_geometry(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return bool(left.get("clip_variant")) and all(
        left.get(key) == right.get(key) for key in ("clip_variant", "frame_width", "frame_height")
    )


def _usable(candidate: dict[str, Any]) -> bool:
    width, height = candidate.get("frame_width"), candidate.get("frame_height")
    box = _box(candidate.get("detector_box"))
    confidence = _number(candidate.get("crop_confidence"))
    return (
        candidate.get("source_mode") == "model_crop"
        and type(candidate.get("frame_index")) is int
        and _number(candidate.get("frame_offset_seconds")) is not None
        and type(width) is int
        and width > 0
        and type(height) is int
        and height > 0
        and box is not None
        and box[2] <= width
        and box[3] <= height
        and confidence is not None
        and MIN_EXPLORATORY_CONFIDENCE <= confidence <= 1
    )


def choose_count_rechecks(
    candidates: list[dict[str, Any]],
    *,
    bird_species: Mapping[str, str],
    observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Use only original crops from one fresh scoring bundle, never retained history."""
    usable = [candidate for candidate in candidates if _usable(candidate)]
    strong = [candidate for candidate in usable if candidate["crop_confidence"] >= MIN_DETECTOR_CONFIDENCE]
    already_observed = [
        {**candidate, "detector_box": candidate.get("detector_box") or candidate.get("crop_box")}
        for candidate in observations or []
        if _box(candidate.get("detector_box") or candidate.get("crop_box")) is not None
        and MIN_DETECTOR_CONFIDENCE <= (_number(candidate.get("crop_confidence")) or 0) <= 1
    ]
    donors = [
        candidate
        for candidate in strong
        if bird_species.get(candidate.get("classifier_label"))
        and (_number(candidate.get("classifier_score")) or 0) >= MIN_SPECIES_CONFIDENCE
    ]
    chosen: list[dict[str, Any]] = []
    for seed in sorted(usable, key=lambda candidate: candidate["crop_confidence"], reverse=True):
        species = bird_species.get(seed.get("classifier_label"))
        if not species or seed["crop_confidence"] >= MIN_DETECTOR_CONFIDENCE:
            continue
        seed_box = _box(seed["detector_box"])
        if any(
            _same_geometry(seed, previous)
            and seed["frame_index"] == previous["frame_index"]
            and _compatible(seed_box, _box(previous["detector_box"]), minimum_area_ratio=0.5)
            for previous in strong + already_observed + chosen
        ):
            continue
        if not any(
            _same_geometry(seed, donor)
            and seed["frame_index"] != donor["frame_index"]
            and 0.5 <= abs(seed["frame_offset_seconds"] - donor["frame_offset_seconds"]) <= MAX_NEIGHBOR_SECONDS
            and species == bird_species.get(donor.get("classifier_label"))
            and _compatible(seed_box, _box(donor["detector_box"]), minimum_area_ratio=0.2)
            for donor in donors
        ):
            continue
        chosen.append(seed)
        if len(chosen) == MAX_COUNT_RECHECKS:
            break
    return chosen


def recheck_confirms_seed(seed: dict[str, Any], result: dict[str, Any]) -> bool:
    """A neighboring bird or a group-sized box cannot confirm this small crop."""
    confidence = _number(result.get("confidence"))
    box = _box(result.get("detector_box"))
    original = _box(seed.get("detector_box"))
    crop = _box(seed.get("crop_box"))
    if confidence is None or not MIN_DETECTOR_CONFIDENCE <= confidence <= 1 or not box or not original or not crop:
        return False
    return (
        box[2] <= seed["frame_width"]
        and box[3] <= seed["frame_height"]
        and _compatible(original, box, minimum_area_ratio=0.5)
        and _intersection(crop, box) / _area(box) >= 0.8
    )
