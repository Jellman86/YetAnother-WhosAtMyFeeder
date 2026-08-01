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


@dataclass(frozen=True)
class TemporalClassEvidence:
    class_index: int
    score: float
    supporting_frame_count: int
    support_ratio: float


@dataclass(frozen=True)
class TemporalConsensus:
    winner_index: int
    score: float
    supporting_frame_count: int
    evaluated_frame_count: int
    required_supporting_frames: int
    ranked_classes: tuple[TemporalClassEvidence, ...]


@dataclass(frozen=True)
class TemporalConsensusAssessment:
    """Complete evidence summary, including conservative abstentions."""

    consensus: TemporalConsensus | None
    evaluated_frame_count: int
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
) -> TemporalConsensus | None:
    """Return robust class evidence only when independent frames agree.

    Each sufficiently confident frame contributes one vote, while a valid but
    low-confidence/non-species frame counts as an abstaining attempt. At least
    three frames must be evaluated and a class must own at least two votes plus
    60% of all evaluated frames. The reported confidence is the median of its
    supporting frames, so one extreme frame cannot determine the result.
    """
    return assess_temporal_consensus(
        frame_scores,
        minimum_frame_score=minimum_frame_score,
        excluded_class_indices=excluded_class_indices,
        minimum_evaluated_frames=minimum_evaluated_frames,
    ).consensus


def assess_temporal_consensus(
    frame_scores: Iterable[np.ndarray],
    *,
    minimum_frame_score: float,
    excluded_class_indices: set[int] | None = None,
    minimum_evaluated_frames: int = VIDEO_MIN_EVALUATED_FRAMES,
) -> TemporalConsensusAssessment:
    """Assess temporal evidence and retain why a source was rejected.

    Only frames that actually produced a score array count as evaluated. Callers
    can set a higher coverage floor for optional representations such as dynamic
    crops, preventing a tiny number of lucky crops from deciding a whole clip.
    """
    excluded = excluded_class_indices or set()
    minimum_score = min(1.0, max(0.0, float(minimum_frame_score)))
    required_evaluated_frames = max(VIDEO_MIN_EVALUATED_FRAMES, int(minimum_evaluated_frames))
    votes: list[tuple[int, float]] = []
    observations: list[tuple[int, float]] = []
    evaluated_count = 0

    expected_size: int | None = None
    for raw_scores in frame_scores:
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
        observations.append((top_index, top_score))
        if top_score < minimum_score:
            continue
        votes.append((top_index, top_score))

    def _rank_evidence(items: list[tuple[int, float]]) -> tuple[TemporalClassEvidence, ...]:
        counts = Counter(class_index for class_index, _score in items)
        evidence: list[TemporalClassEvidence] = []
        for class_index, support_count in counts.items():
            supporting_scores = [score for item_index, score in items if item_index == class_index]
            evidence.append(
                TemporalClassEvidence(
                    class_index=class_index,
                    score=float(statistics.median(supporting_scores)),
                    supporting_frame_count=support_count,
                    support_ratio=support_count / evaluated_count,
                )
            )
        evidence.sort(
            key=lambda item: (item.supporting_frame_count, item.score),
            reverse=True,
        )
        return tuple(evidence)

    ranked_evidence = _rank_evidence(votes)
    ranked_observations = _rank_evidence(observations)

    required_support = max(
        VIDEO_MIN_SUPPORTING_FRAMES,
        math.ceil(evaluated_count * VIDEO_CLASS_CONSENSUS_RATIO),
    )
    if evaluated_count < required_evaluated_frames:
        return TemporalConsensusAssessment(
            consensus=None,
            evaluated_frame_count=evaluated_count,
            confident_frame_count=len(votes),
            required_supporting_frames=required_support,
            ranked_classes=ranked_evidence,
            ranked_observations=ranked_observations,
            reason="insufficient_source_coverage",
        )
    if len(votes) < VIDEO_MIN_SUPPORTING_FRAMES:
        return TemporalConsensusAssessment(
            consensus=None,
            evaluated_frame_count=evaluated_count,
            confident_frame_count=len(votes),
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
            confident_frame_count=len(votes),
            required_supporting_frames=required_support,
            ranked_classes=ranked_evidence,
            ranked_observations=ranked_observations,
            reason="insufficient_class_agreement",
        )

    consensus = TemporalConsensus(
        winner_index=winner.class_index,
        score=winner.score,
        supporting_frame_count=winner.supporting_frame_count,
        evaluated_frame_count=evaluated_count,
        required_supporting_frames=required_support,
        ranked_classes=ranked_evidence,
    )
    return TemporalConsensusAssessment(
        consensus=consensus,
        evaluated_frame_count=evaluated_count,
        confident_frame_count=len(votes),
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
            item.consensus.supporting_frame_count / item.consensus.evaluated_frame_count,
            item.consensus.supporting_frame_count,
            item.consensus.score,
        ),
    )
