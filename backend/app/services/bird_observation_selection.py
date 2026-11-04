"""Choose one frame's localized birds for a capture-level count."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import combinations
import math
from typing import Any, Literal

from app.services.bird_physical_confirmation import (
    MIN_DETECTOR_CONFIDENCE,
    STRONG_DETECTOR_CONFIDENCE,
    PhysicalBirdDecision,
    decide_physical_bird,
)
from app.utils.canonical_species import UNKNOWN_BIRD_DISPLAY_LABEL, should_hide_species_label


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
class BirdCountRegion:
    candidate_id: str
    box: tuple[float, float, float, float]
    detector_confidence: float | None
    reason: str


@dataclass(frozen=True)
class BirdObservationSelection:
    clip_variant: str | None
    frame_index: int | None
    full_frame_candidate_id: str | None
    birds: tuple[BirdObservation, ...]
    ambiguity_reason: str | None = None
    unconfirmed_regions: tuple[BirdCountRegion, ...] = ()
    excluded_regions: tuple[BirdCountRegion, ...] = ()
    count_status: Literal["legacy", "complete", "incomplete", "ambiguous", "not_measured"] = "legacy"


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


def _encloses_distinct_birds(box: tuple[float, ...], boxes: list[tuple[float, ...]]) -> bool:
    area = (box[2] - box[0]) * (box[3] - box[1])
    contained = [
        other
        for other in boxes
        if (other[2] - other[0]) * (other[3] - other[1]) <= area * 0.5 and _overlap_of_smaller_box(box, other) >= 0.9
    ]
    if len(contained) < 2:
        return False
    return any(
        _overlap_of_smaller_box(left, right) < DUPLICATE_BOX_OVERLAP for left, right in combinations(contained, 2)
    )


def _shares_pixels(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return min(left[2], right[2]) > max(left[0], right[0]) and min(left[3], right[3]) > max(left[1], right[1])


def select_confirmed_bird_observations(
    candidates: list[dict[str, Any]],
    *,
    selected_candidate: dict[str, Any] | None,
    finder_qualified: bool,
    physical_decisions: Mapping[str, PhysicalBirdDecision],
) -> BirdObservationSelection:
    """Partition one scene into confirmed individuals and explicitly uncounted regions.

    Decisions come from fresh, bound own-pixel evidence, never contextual photo
    names. Even positive presence cannot establish another individual when a
    mid-band proposal shares pixels with another unresolved proposal or bird.
    """
    if finder_qualified is not True:
        return BirdObservationSelection(None, None, None, (), count_status="not_measured")
    by_frame: dict[tuple[str, int], dict[tuple[float, ...], dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate.get("source_mode") not in {"model_crop", "model_observation"}:
            continue
        frame = _frame_key(candidate)
        box = _box(candidate.get("detector_box") or candidate.get("crop_box"))
        confidence = _finite_score(candidate.get("crop_confidence"))
        if frame is None or type(frame[1]) is not int or box is None:
            continue
        if confidence is not None and 0 <= confidence < MIN_DETECTOR_CONFIDENCE:
            continue
        entries = by_frame.setdefault(frame, {})
        previous = entries.get(box)

        # The same detector output appears as a photo crop and an observation.
        # Exact repeated geometry is one proposal, not an overlapping cluster.
        def preference(item: dict[str, Any]) -> tuple[bool, bool, float, str]:
            return (
                str(item.get("candidate_id") or "") in physical_decisions,
                item.get("source_mode") == "model_observation",
                _finite_score(item.get("crop_confidence")) or 0.0,
                str(item.get("candidate_id") or ""),
            )

        if previous is None or preference(candidate) > preference(previous):
            entries[box] = candidate

    outcomes = []
    for frame, entries in by_frame.items():
        decisions = {}
        for box, candidate in entries.items():
            name = str(candidate.get("candidate_id") or "")
            decision = physical_decisions.get(name)
            if decision is None:
                decision = decide_physical_bird(
                    candidate.get("crop_confidence"),
                    finder_qualified=True,
                    evidence=None,
                    expected_model_sha256=None,
                    expected_mapping_sha256=None,
                    expected_crop_sha256=None,
                )
            decisions[box] = decision
        active = [box for box, decision in decisions.items() if decision.verdict != "excluded"]
        ambiguous = any(_encloses_distinct_birds(box, active) for box in active)
        confirmed = []
        unconfirmed, excluded = [], []
        for box, candidate in sorted(entries.items()):
            decision = decisions[box]
            confidence = _finite_score(candidate.get("crop_confidence"))
            strong = confidence is not None and confidence >= STRONG_DETECTOR_CONFIDENCE
            if (
                decision.verdict != "excluded"
                and not strong
                and any(other != box and _shares_pixels(box, other) for other in active)
            ):
                shares_counted = any(
                    other != box
                    and _shares_pixels(box, other)
                    and decisions[other].verdict == "counted"
                    and (_finite_score(entries[other].get("crop_confidence")) or 0) >= STRONG_DETECTOR_CONFIDENCE
                    for other in active
                )
                decision = PhysicalBirdDecision(
                    "unconfirmed", "shares_counted_pixels" if shares_counted else "individuality_unresolved"
                )
            if decision.verdict == "counted":
                confirmed.append(candidate)
            else:
                region = BirdCountRegion(str(candidate.get("candidate_id") or ""), box, confidence, decision.reason)
                (excluded if decision.verdict == "excluded" else unconfirmed).append(region)
        full = [item for item in candidates if item.get("source_mode") == "full_frame" and _frame_key(item) == frame]
        selected = select_bird_observations(confirmed + full, selected_candidate=selected_candidate)
        if selected.clip_variant is None:
            selected = replace(
                selected,
                clip_variant=frame[0],
                frame_index=frame[1],
                full_frame_candidate_id=str(full[0].get("candidate_id") or "") if full else None,
            )
        if ambiguous or selected.ambiguity_reason:
            selected = replace(selected, birds=(), ambiguity_reason="ambiguous_localization", count_status="ambiguous")
        else:
            selected = replace(selected, count_status="incomplete" if unconfirmed else "complete")
        outcomes.append(replace(selected, unconfirmed_regions=tuple(unconfirmed), excluded_regions=tuple(excluded)))
    if not outcomes:
        full = next((item for item in candidates if item.get("source_mode") == "full_frame" and _frame_key(item)), None)
        return BirdObservationSelection(
            full.get("clip_variant") if full else None,
            full.get("frame_index") if full else None,
            str(full.get("candidate_id") or "") if full else None,
            (),
            count_status="complete",
        )
    clear = [item for item in outcomes if not item.ambiguity_reason and item.birds]
    unresolved = [item for item in outcomes if item.ambiguity_reason or item.unconfirmed_regions]
    selected_frame = _frame_key(selected_candidate) if selected_candidate else None
    return max(
        clear or unresolved or outcomes,
        key=lambda item: (
            len(item.birds),
            item.count_status == "complete",
            (item.clip_variant, item.frame_index) == selected_frame,
            str(item.clip_variant),
            item.frame_index or 0,
        ),
    )


def select_scene_birds(
    candidates: list[dict[str, Any]],
    *,
    selected_candidate: dict[str, Any] | None,
    confirmed_finder: bool,
) -> BirdObservationSelection:
    """Count confirmed birds when the finder is validated for it; otherwise keep the earlier count.

    Confirmation reads only the finder's whole-scene boxes. Photo-choice crops can
    come from a fallback detector, and own-pixel classifier evidence is not wired
    yet, so a box below the strong detector floor is disclosed instead of counted.
    """
    if not confirmed_finder:
        return select_bird_observations(candidates, selected_candidate=selected_candidate)
    scene_evidence = [item for item in candidates if item.get("source_mode") in {"model_observation", "full_frame"}]
    return select_confirmed_bird_observations(
        scene_evidence, selected_candidate=selected_candidate, finder_qualified=True, physical_decisions={}
    )


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

    # Guided inference can localize a bird the whole-scene scan misses. Both are
    # detector evidence; combine them before removing duplicate boxes.
    for frame, observations in observations_by_frame.items():
        by_frame.setdefault(frame, []).extend(observations)
    if not by_frame:
        by_frame = hint_by_frame
    if not by_frame:
        return BirdObservationSelection(None, None, None, ())

    distinct_by_frame: dict[tuple[str, int], list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {}
    ambiguous_frames: set[tuple[str, int]] = set()
    for frame, items in by_frame.items():
        boxes = [box for _, box in items]
        # The same geometry can be two birds inside a group box or two parts of
        # one bird. Neither detector nor contextual species scores resolve it.
        if any(_encloses_distinct_birds(box, boxes) for box in boxes):
            ambiguous_frames.add(frame)
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
    clear_frames = [frame for frame, items in distinct_by_frame.items() if items and frame not in ambiguous_frames]
    anchor = max(
        clear_frames or distinct_by_frame,
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
    if anchor in ambiguous_frames:
        return BirdObservationSelection(
            anchor[0],
            anchor[1],
            str(full_frame.get("candidate_id") or "") if full_frame else None,
            (),
            "ambiguous_localization",
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
