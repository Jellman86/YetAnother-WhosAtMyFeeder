"""Pure policy for promoting classifications from high-quality crop candidates."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from app.utils.canonical_species import should_hide_species_label, unknown_species_labels
from app.utils.classifier_labels import normalize_classifier_label


HQ_REFINEMENT_MIN_SUPPORTING_FRAMES = 2
HQ_REFINEMENT_MIN_SCORE = 0.60
HQ_REFINEMENT_MIN_WINNER_MARGIN = 0.08
HQ_REFINEMENT_MIN_EXISTING_SCORE_GAIN = 0.02
# Adjacent frames from a 30 fps stream are effectively the same observation.
# Requiring a quarter-second gap keeps the evidence useful for short feeder
# visits while preventing decode neighbours from becoming independent votes.
HQ_REFINEMENT_MIN_TEMPORAL_SEPARATION_SECONDS = 0.25


@dataclass(frozen=True)
class HQClassificationRefinement:
    """A crop consensus that is safe to hand to the canonical detection service."""

    label: str
    score: float
    index: int
    candidate_id: str
    source_mode: str
    supporting_frame_count: int
    median_score: float
    reason: str


@dataclass(frozen=True)
class _Consensus:
    label: str
    key: str
    best_candidate: dict[str, Any]
    supporting_frame_count: int
    median_score: float


def _canonical_label(value: Any) -> str:
    label = normalize_classifier_label(str(value or "").strip())
    return " ".join(label.replace("_", " ").split())


def _label_key(value: Any) -> str:
    return _canonical_label(value).casefold()


def _valid_crop_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_mode = str(candidate.get("source_mode") or "full_frame").strip()
        if source_mode == "full_frame":
            continue
        label = _canonical_label(candidate.get("classifier_label"))
        if not label or should_hide_species_label(label, extra_unknown_labels=unknown_species_labels()):
            continue
        try:
            score = float(candidate.get("classifier_score"))
            frame_index = int(candidate.get("frame_index"))
            frame_offset_seconds = float(candidate.get("frame_offset_seconds"))
            index = int(candidate.get("classifier_index"))
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(score)
            or score < 0.0
            or score > 1.0
            or frame_index < 0
            or not math.isfinite(frame_offset_seconds)
            or frame_offset_seconds < 0.0
        ):
            continue
        valid.append(
            {
                **candidate,
                "classifier_label": label,
                "classifier_score": score,
                "frame_index": frame_index,
                "frame_offset_seconds": frame_offset_seconds,
                "classifier_index": index,
                "source_mode": source_mode,
            }
        )
    return valid


def _best_temporally_independent_candidates(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Choose the strongest largest subset with genuinely separated timestamps.

    Multiple crop sources from the same decoded frame are collapsed first. The
    remaining set is tiny (HQ generation currently evaluates at most three
    frames), so an exhaustive subset search is clearer and safer than a greedy
    approximation. Cardinality wins before confidence: temporal support must
    never be traded for two near-identical high-scoring frames.
    """

    best_by_frame: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        frame_index = int(candidate["frame_index"])
        current = best_by_frame.get(frame_index)
        if current is None or float(candidate["classifier_score"]) > float(current["classifier_score"]):
            best_by_frame[frame_index] = candidate

    unique = list(best_by_frame.values())
    best_subset: tuple[dict[str, Any], ...] = ()
    best_key: tuple[int, float, float] = (0, 0.0, 0.0)
    for subset_size in range(1, len(unique) + 1):
        for subset in combinations(unique, subset_size):
            ordered = sorted(subset, key=lambda item: float(item["frame_offset_seconds"]))
            if any(
                float(right["frame_offset_seconds"]) - float(left["frame_offset_seconds"])
                < HQ_REFINEMENT_MIN_TEMPORAL_SEPARATION_SECONDS
                for left, right in zip(ordered, ordered[1:])
            ):
                continue
            scores = [float(item["classifier_score"]) for item in ordered]
            key = (len(ordered), float(statistics.median(scores)), max(scores))
            if key > best_key:
                best_key = key
                best_subset = tuple(ordered)
    return list(best_subset)


def _build_consensus(candidates: Iterable[dict[str, Any]]) -> list[_Consensus]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in _valid_crop_candidates(candidates):
        grouped.setdefault(_label_key(candidate["classifier_label"]), []).append(candidate)

    consensus: list[_Consensus] = []
    for key, label_candidates in grouped.items():
        independent = _best_temporally_independent_candidates(label_candidates)
        if len(independent) < HQ_REFINEMENT_MIN_SUPPORTING_FRAMES:
            continue
        best = max(independent, key=lambda item: float(item["classifier_score"]))
        consensus.append(
            _Consensus(
                label=str(best["classifier_label"]),
                key=key,
                best_candidate=best,
                supporting_frame_count=len(independent),
                median_score=float(statistics.median(float(item["classifier_score"]) for item in independent)),
            )
        )
    return sorted(
        consensus,
        key=lambda item: (item.median_score, float(item.best_candidate["classifier_score"])),
        reverse=True,
    )


def crop_labels_with_independent_support(candidates: Iterable[dict[str, Any]]) -> set[str]:
    """Return canonical label keys backed by temporally independent crop evidence."""

    return {item.key for item in _build_consensus(candidates)}


def choose_hq_classification_refinement(
    *,
    detection: Any,
    candidates: Iterable[dict[str, Any]],
    minimum_score: float = HQ_REFINEMENT_MIN_SCORE,
) -> HQClassificationRefinement | None:
    """Return a conservative multi-frame crop refinement, or ``None``.

    Full frames never vote because this policy exists specifically to recover detail lost when
    the subject occupies a small portion of a distant camera frame. Multiple crop sources from the
    same frame count once. A crop consensus may upgrade Unknown or improve the score for the same
    canonical species, but it never replaces a manual or conflicting known identification.
    """

    if bool(getattr(detection, "manual_tagged", False)):
        return None

    ranked = _build_consensus(candidates)
    if not ranked:
        return None

    winner = ranked[0]
    score_floor = max(HQ_REFINEMENT_MIN_SCORE, float(minimum_score or 0.0))
    best_score = float(winner.best_candidate["classifier_score"])
    if winner.median_score < score_floor or best_score < score_floor:
        return None
    if len(ranked) > 1 and winner.median_score - ranked[1].median_score < HQ_REFINEMENT_MIN_WINNER_MARGIN:
        return None

    identity_values = (
        getattr(detection, "display_name", None),
        getattr(detection, "category_name", None),
        getattr(detection, "scientific_name", None),
        getattr(detection, "common_name", None),
    )
    populated_identity_values = [value for value in identity_values if str(value or "").strip()]
    existing_is_unknown = bool(populated_identity_values) and all(
        should_hide_species_label(value, extra_unknown_labels=unknown_species_labels())
        for value in populated_identity_values
    )
    existing_keys = {_label_key(value) for value in identity_values if _label_key(value)}

    if existing_is_unknown:
        reason = "upgrade_unknown_from_crop_consensus"
    elif winner.key in existing_keys:
        current_score = float(getattr(detection, "score", 0.0) or 0.0)
        if best_score < current_score + HQ_REFINEMENT_MIN_EXISTING_SCORE_GAIN:
            return None
        reason = "reinforce_existing_from_crop_consensus"
    else:
        return None

    best = winner.best_candidate
    return HQClassificationRefinement(
        label=winner.label,
        score=best_score,
        index=int(best["classifier_index"]),
        candidate_id=str(best.get("candidate_id") or ""),
        source_mode=str(best["source_mode"]),
        supporting_frame_count=winner.supporting_frame_count,
        median_score=winner.median_score,
        reason=reason,
    )
