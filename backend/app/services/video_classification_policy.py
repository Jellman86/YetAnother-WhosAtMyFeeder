"""Pure temporal-consensus policy for video classification."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import numpy as np


VIDEO_MIN_EVALUATED_FRAMES = 3
VIDEO_MIN_SUPPORTING_FRAMES = 2
VIDEO_CLASS_CONSENSUS_RATIO = 0.60
VIDEO_MIN_FRAME_SEPARATION_SECONDS = 0.25
VIDEO_SPARSE_POOL_MAX_FRAMES = 5


@dataclass(frozen=True)
class TemporalClassEvidence:
    class_index: int
    score: float
    supporting_frame_count: int
    support_ratio: float
    pooled_frame_count: int


@dataclass(frozen=True)
class TemporalConsensus:
    winner_index: int
    score: float
    supporting_frame_count: int
    confident_frame_count: int
    evaluated_frame_count: int
    independent_frame_count: int
    required_supporting_frames: int
    ranked_classes: tuple[TemporalClassEvidence, ...]


@dataclass(frozen=True)
class TemporalConsensusAssessment:
    """Complete evidence summary, including conservative abstentions."""

    consensus: TemporalConsensus | None
    evaluated_frame_count: int
    independent_frame_count: int
    confident_frame_count: int
    required_supporting_frames: int
    ranked_classes: tuple[TemporalClassEvidence, ...]
    ranked_observations: tuple[TemporalClassEvidence, ...]
    reason: str


@dataclass(frozen=True)
class SourceTemporalConsensus:
    """Temporal evidence produced from one image representation per frame."""

    input_source: str
    consensus: TemporalConsensus | None


def build_temporal_consensus(
    frame_scores: Iterable[np.ndarray],
    *,
    minimum_frame_score: float,
    excluded_class_indices: set[int] | None = None,
    minimum_evaluated_frames: int = VIDEO_MIN_EVALUATED_FRAMES,
    frame_offsets_seconds: Iterable[float | None] | None = None,
) -> TemporalConsensus | None:
    """Return robust class evidence only when independent frames agree.

    Each sufficiently confident frame contributes one vote. Valid low-confidence
    frames prove that the source was evaluated, but do not vote against a species:
    a fleeting visitor should not need to occupy most of a retained visit clip.
    At least three frames must be evaluated and a class must own at least two
    votes plus 60% of the confident votes. The reported confidence is the median
    of up to the five strongest independent supporting moments, so one extreme
    frame cannot determine the result and a long tail of empty frames does not
    dilute brief, repeated evidence.
    """
    return assess_temporal_consensus(
        frame_scores,
        minimum_frame_score=minimum_frame_score,
        excluded_class_indices=excluded_class_indices,
        minimum_evaluated_frames=minimum_evaluated_frames,
        frame_offsets_seconds=frame_offsets_seconds,
    ).consensus


def assess_temporal_consensus(
    frame_scores: Iterable[np.ndarray],
    *,
    minimum_frame_score: float,
    excluded_class_indices: set[int] | None = None,
    minimum_evaluated_frames: int = VIDEO_MIN_EVALUATED_FRAMES,
    frame_offsets_seconds: Iterable[float | None] | None = None,
) -> TemporalConsensusAssessment:
    """Assess temporal evidence and retain why a source was rejected.

    Only frames that actually produced a score array count as evaluated. Frames
    closer than 250 ms are one correlated moment and the strongest observation
    represents that moment. This prevents adjacent decodes from manufacturing
    temporal support without making a fleeting subject occupy a fixed fraction
    of a long recording.
    """
    excluded = excluded_class_indices or set()
    minimum_score = min(1.0, max(0.0, float(minimum_frame_score)))
    required_evaluated_frames = max(VIDEO_MIN_EVALUATED_FRAMES, int(minimum_evaluated_frames))
    votes: list[tuple[int, float, float | None, int]] = []
    observations: list[tuple[int, float, float | None, int]] = []
    evaluated_count = 0

    offsets = list(frame_offsets_seconds) if frame_offsets_seconds is not None else []

    expected_size: int | None = None
    for ordinal, raw_scores in enumerate(frame_scores):
        scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1)
        if scores.size == 0 or not np.all(np.isfinite(scores)):
            continue
        if expected_size is None:
            expected_size = int(scores.size)
        if scores.size != expected_size:
            continue
        evaluated_count += 1

        eligible_scores = scores.copy()
        for class_index in excluded:
            if 0 <= class_index < eligible_scores.size:
                eligible_scores[class_index] = -np.inf
        top_index = int(np.argmax(eligible_scores))
        top_score = float(eligible_scores[top_index])
        if not math.isfinite(top_score):
            continue
        raw_offset = offsets[ordinal] if ordinal < len(offsets) else None
        try:
            offset = float(raw_offset) if raw_offset is not None else None
        except (TypeError, ValueError):
            offset = None
        if offset is not None and (not math.isfinite(offset) or offset < 0):
            offset = None
        observations.append((top_index, top_score, offset, ordinal))
        if top_score < minimum_score:
            continue
        votes.append((top_index, top_score, offset, ordinal))

    def _independent(items: list[tuple[int, float, float | None, int]]) -> list[tuple[int, float]]:
        if not items:
            return []
        if not any(offset is not None for _class_index, _score, offset, _ordinal in items):
            return [(class_index, score) for class_index, score, _offset, _ordinal in items]

        selected: list[tuple[int, float, float | None, int]] = []
        for item in sorted(items, key=lambda value: (value[1], -value[3]), reverse=True):
            offset = item[2]
            if offset is None or all(
                selected_offset is None or abs(offset - selected_offset) >= VIDEO_MIN_FRAME_SEPARATION_SECONDS
                for _index, _score, selected_offset, _ordinal in selected
            ):
                selected.append(item)
        selected.sort(key=lambda value: value[3])
        return [(class_index, score) for class_index, score, _offset, _ordinal in selected]

    independent_observations = _independent(observations)
    independent_votes = _independent(votes)

    def _rank_evidence(
        items: list[tuple[int, float]],
        *,
        denominator: int,
    ) -> tuple[TemporalClassEvidence, ...]:
        counts = Counter(class_index for class_index, _score in items)
        evidence: list[TemporalClassEvidence] = []
        for class_index, support_count in counts.items():
            supporting_scores = sorted(
                (score for item_index, score in items if item_index == class_index),
                reverse=True,
            )
            pooled_scores = supporting_scores[:VIDEO_SPARSE_POOL_MAX_FRAMES]
            evidence.append(
                TemporalClassEvidence(
                    class_index=class_index,
                    score=float(statistics.median(pooled_scores)),
                    supporting_frame_count=support_count,
                    support_ratio=support_count / denominator,
                    pooled_frame_count=len(pooled_scores),
                )
            )
        evidence.sort(
            key=lambda item: (item.supporting_frame_count, item.score),
            reverse=True,
        )
        return tuple(evidence)

    ranked_evidence = _rank_evidence(independent_votes, denominator=max(1, len(independent_votes)))
    ranked_observations = _rank_evidence(
        independent_observations,
        denominator=max(1, len(independent_observations)),
    )

    required_support = max(
        VIDEO_MIN_SUPPORTING_FRAMES,
        math.ceil(len(independent_votes) * VIDEO_CLASS_CONSENSUS_RATIO),
    )
    if len(independent_observations) < required_evaluated_frames:
        return TemporalConsensusAssessment(
            consensus=None,
            evaluated_frame_count=evaluated_count,
            independent_frame_count=len(independent_observations),
            confident_frame_count=len(independent_votes),
            required_supporting_frames=required_support,
            ranked_classes=ranked_evidence,
            ranked_observations=ranked_observations,
            reason="insufficient_source_coverage",
        )
    if len(independent_votes) < VIDEO_MIN_SUPPORTING_FRAMES:
        return TemporalConsensusAssessment(
            consensus=None,
            evaluated_frame_count=evaluated_count,
            independent_frame_count=len(independent_observations),
            confident_frame_count=len(independent_votes),
            required_supporting_frames=required_support,
            ranked_classes=ranked_evidence,
            ranked_observations=ranked_observations,
            reason="insufficient_confident_frames",
        )

    winner = ranked_evidence[0]
    if winner.supporting_frame_count < required_support:
        return TemporalConsensusAssessment(
            consensus=None,
            evaluated_frame_count=evaluated_count,
            independent_frame_count=len(independent_observations),
            confident_frame_count=len(independent_votes),
            required_supporting_frames=required_support,
            ranked_classes=ranked_evidence,
            ranked_observations=ranked_observations,
            reason="insufficient_class_agreement",
        )

    consensus = TemporalConsensus(
        winner_index=winner.class_index,
        score=winner.score,
        supporting_frame_count=winner.supporting_frame_count,
        confident_frame_count=len(independent_votes),
        evaluated_frame_count=evaluated_count,
        independent_frame_count=len(independent_observations),
        required_supporting_frames=required_support,
        ranked_classes=ranked_evidence,
    )
    return TemporalConsensusAssessment(
        consensus=consensus,
        evaluated_frame_count=evaluated_count,
        independent_frame_count=len(independent_observations),
        confident_frame_count=len(independent_votes),
        required_supporting_frames=required_support,
        ranked_classes=ranked_evidence,
        ranked_observations=ranked_observations,
        reason="accepted",
    )


def select_temporal_source_consensus(
    source_consensuses: Iterable[SourceTemporalConsensus],
) -> SourceTemporalConsensus | None:
    """Choose a source only when every trustworthy representation agrees.

    Full frames, Frigate-box crops, and detector crops are alternate views of the
    same sampled frames, not independent votes. Each source must therefore reach
    temporal consensus on its own. If trustworthy sources disagree, abstaining is
    safer than choosing whichever transformation happened to be most confident.
    """
    candidates = [item for item in source_consensuses if item.consensus is not None]
    if not candidates:
        return None

    winner_indices = {item.consensus.winner_index for item in candidates if item.consensus is not None}
    if len(winner_indices) != 1:
        return None

    return max(
        candidates,
        key=lambda item: (
            item.consensus.supporting_frame_count / item.consensus.confident_frame_count,
            item.consensus.supporting_frame_count,
            item.consensus.score,
        ),
    )
