import numpy as np
import pytest

from app.services.video_classification_policy import build_temporal_consensus


def test_temporal_consensus_rejects_single_high_confidence_outlier():
    scores = [
        np.array([0.79, 0.20, 0.01]),
        np.array([0.76, 0.22, 0.02]),
        np.array([0.73, 0.25, 0.02]),
        np.array([0.71, 0.27, 0.02]),
        np.array([0.005, 0.99, 0.005]),
    ]

    consensus = build_temporal_consensus(scores, minimum_frame_score=0.4)

    assert consensus is not None
    assert consensus.winner_index == 0
    assert consensus.supporting_frame_count == 4
    assert consensus.evaluated_frame_count == 5
    assert consensus.score == pytest.approx(0.745)


def test_temporal_consensus_abstains_without_sixty_percent_class_agreement():
    scores = [
        np.array([0.90, 0.08, 0.02]),
        np.array([0.85, 0.10, 0.05]),
        np.array([0.10, 0.85, 0.05]),
        np.array([0.15, 0.80, 0.05]),
        np.array([0.15, 0.10, 0.75]),
    ]

    assert build_temporal_consensus(scores, minimum_frame_score=0.4) is None


def test_temporal_consensus_counts_low_confidence_frames_as_abstentions():
    scores = [
        np.array([0.72, 0.20, 0.08]),
        np.array([0.68, 0.25, 0.07]),
        np.array([0.36, 0.34, 0.30]),
    ]

    consensus = build_temporal_consensus(scores, minimum_frame_score=0.45)

    assert consensus is not None
    assert consensus.winner_index == 0
    assert consensus.evaluated_frame_count == 3
    assert consensus.supporting_frame_count == 2
    assert consensus.score == pytest.approx(0.70)

    assert build_temporal_consensus([np.array([0.99, 0.01])], minimum_frame_score=0.45) is None


def test_temporal_consensus_requires_three_evaluated_frames():
    assert (
        build_temporal_consensus(
            [np.array([0.90, 0.10]), np.array([0.85, 0.15])],
            minimum_frame_score=0.45,
        )
        is None
    )


def test_temporal_consensus_masks_non_species_classes_before_voting():
    scores = [
        np.array([0.58, 0.41, 0.01]),
        np.array([0.63, 0.36, 0.01]),
        np.array([0.10, 0.82, 0.08]),
    ]

    consensus = build_temporal_consensus(
        scores,
        minimum_frame_score=0.25,
        excluded_class_indices={0},
    )

    assert consensus is not None
    assert consensus.winner_index == 1
    assert consensus.supporting_frame_count == 3
    assert consensus.score == pytest.approx(0.41)
