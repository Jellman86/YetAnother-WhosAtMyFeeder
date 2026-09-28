"""Choose one frame's localized birds for a capture-level count."""

from dataclasses import dataclass
import math
from typing import Any

from app.utils.canonical_species import UNKNOWN_BIRD_DISPLAY_LABEL, should_hide_species_label


MIN_DETECTOR_CONFIDENCE = 0.08
MIN_SPECIES_CONFIDENCE = 0.65
DUPLICATE_BOX_OVERLAP = 0.4


@dataclass(frozen=True)
class BirdObservation:
    candidate_id: str
    box: tuple[float, float, float, float]
    detector_confidence: float | None
    species: str
    classifier_label: str | None
    classifier_score: float


@dataclass(frozen=True)
class BirdObservationSelection:
    clip_variant: str | None
    frame_index: int | None
    full_frame_candidate_id: str | None
    birds: tuple[BirdObservation, ...]


def _finite_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) else None


def _box(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    try:
        box = tuple(float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(part) for part in box) or box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _overlap_of_smaller_box(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    smaller_area = min(left_area, right_area)
    return overlap / smaller_area if smaller_area > 0 else 0.0


def _frame_key(candidate: dict[str, Any]) -> tuple[str, int] | None:
    variant = candidate.get("clip_variant")
    frame_index = candidate.get("frame_index")
    if not isinstance(variant, str) or not isinstance(frame_index, int):
        return None
    return variant, frame_index


def select_bird_observations(
    candidates: list[dict[str, Any]],
    *,
    selected_candidate: dict[str, Any] | None,
) -> BirdObservationSelection:
    """Count distinct detector birds in one frame so repeats across frames do not multiply birds."""
    by_frame: dict[tuple[str, int], list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {}
    observations_by_frame: dict[tuple[str, int], list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {}
    hint_by_frame: dict[tuple[str, int], list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {}
    for candidate in candidates:
        frame = _frame_key(candidate)
        box = _box(candidate.get("detector_box") or candidate.get("crop_box"))
        if frame is None or box is None:
            continue
        mode = candidate.get("source_mode")
        if mode in {"model_crop", "model_observation"}:
            confidence = _finite_score(candidate.get("crop_confidence"))
            if confidence is not None and confidence >= MIN_DETECTOR_CONFIDENCE:
                target = observations_by_frame if mode == "model_observation" else by_frame
                target.setdefault(frame, []).append((candidate, box))
        elif mode == "frigate_hint_crop":
            hint_by_frame.setdefault(frame, []).append((candidate, box))

    by_frame.update(observations_by_frame)
    if not by_frame:
        by_frame = hint_by_frame
    if not by_frame:
        return BirdObservationSelection(None, None, None, ())

    distinct_by_frame: dict[tuple[str, int], list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {}
    for frame, items in by_frame.items():
        distinct: list[tuple[dict[str, Any], tuple[float, float, float, float]]] = []
        for candidate, box in sorted(
            items, key=lambda pair: _finite_score(pair[0].get("crop_confidence")) or 0.0, reverse=True
        ):
            if not any(
                _overlap_of_smaller_box(box, previous_box) >= DUPLICATE_BOX_OVERLAP for _, previous_box in distinct
            ):
                distinct.append((candidate, box))
        distinct_by_frame[frame] = distinct

    selected_frame = _frame_key(selected_candidate) if selected_candidate else None
    anchor = max(
        distinct_by_frame,
        key=lambda frame: (
            len(distinct_by_frame[frame]),
            frame == selected_frame,
            frame[0] == "frigate_snapshot",
            sum(_finite_score(item.get("ranking_score")) or 0.0 for item, _ in distinct_by_frame[frame]),
        ),
    )
    full_frame = next(
        (item for item in candidates if item.get("source_mode") == "full_frame" and _frame_key(item) == anchor),
        None,
    )
    birds = []
    for candidate, box in sorted(distinct_by_frame[anchor], key=lambda pair: (pair[1][0], pair[1][1])):
        score = _finite_score(candidate.get("classifier_score")) or 0.0
        label = str(candidate.get("classifier_label") or "").strip() or None
        species = (
            label
            if label and score >= MIN_SPECIES_CONFIDENCE and not should_hide_species_label(label)
            else UNKNOWN_BIRD_DISPLAY_LABEL
        )
        birds.append(
            BirdObservation(
                candidate_id=str(candidate.get("candidate_id") or ""),
                box=box,
                detector_confidence=_finite_score(candidate.get("crop_confidence")),
                species=species,
                classifier_label=label,
                classifier_score=score,
            )
        )
    return BirdObservationSelection(
        clip_variant=anchor[0],
        frame_index=anchor[1],
        full_frame_candidate_id=str(full_frame.get("candidate_id") or "") if full_frame else None,
        birds=tuple(birds),
    )
