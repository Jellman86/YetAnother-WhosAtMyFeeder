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
class SourceTemporalConsensus:
    """Temporal evidence produced from one image representation per frame."""

    input_source: str
    consensus: TemporalConsensus | None


def build_temporal_consensus(
    frame_scores: Iterable[np.ndarray],
    *,
    minimum_frame_score: float,
    excluded_class_indices: set[int] | None = None,
) -> TemporalConsensus | None:
    """Return robust class evidence only when independent frames agree.

    Each sufficiently confident frame contributes one vote, while a valid but
    low-confidence/non-species frame counts as an abstaining attempt. At least
    three frames must be evaluated and a class must own at least two votes plus
    60% of all evaluated frames. The reported confidence is the median of its
    supporting frames, so one extreme frame cannot determine the result.
    """
    excluded = excluded_class_indices or set()
    minimum_score = min(1.0, max(0.0, float(minimum_frame_score)))
    votes: list[tuple[int, float]] = []
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
        if not math.isfinite(top_score) or top_score < minimum_score:
            continue
        votes.append((top_index, top_score))

    if evaluated_count < VIDEO_MIN_EVALUATED_FRAMES or len(votes) < VIDEO_MIN_SUPPORTING_FRAMES:
        return None

    vote_counts = Counter(class_index for class_index, _score in votes)
    evidence: list[TemporalClassEvidence] = []
    for class_index, support_count in vote_counts.items():
        supporting_scores = [score for vote_index, score in votes if vote_index == class_index]
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

    winner = evidence[0]
    required_support = max(
        VIDEO_MIN_SUPPORTING_FRAMES,
        math.ceil(evaluated_count * VIDEO_CLASS_CONSENSUS_RATIO),
    )
    if winner.supporting_frame_count < required_support:
        return None

    return TemporalConsensus(
        winner_index=winner.class_index,
        score=winner.score,
        supporting_frame_count=winner.supporting_frame_count,
        evaluated_frame_count=evaluated_count,
        required_supporting_frames=required_support,
        ranked_classes=tuple(evidence),
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
