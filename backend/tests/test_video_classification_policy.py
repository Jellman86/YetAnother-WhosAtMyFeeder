import numpy as np
import pytest

from app.services.video_classification_policy import (
    SourceTemporalConsensus,
    assess_temporal_consensus,
    build_temporal_consensus,
    select_temporal_source_consensus,
)


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


def test_temporal_consensus_uses_low_confidence_frames_for_coverage_not_species_agreement():
    scores = [
        np.array([0.72, 0.20, 0.08]),
        np.array([0.68, 0.25, 0.07]),
        *[np.array([0.36, 0.34, 0.30]) for _ in range(28)],
    ]

    consensus = build_temporal_consensus(scores, minimum_frame_score=0.45)

    assert consensus is not None
    assert consensus.winner_index == 0
    assert consensus.evaluated_frame_count == 30
    assert consensus.independent_frame_count == 30
    assert consensus.supporting_frame_count == 2
    assert consensus.confident_frame_count == 2
    assert consensus.required_supporting_frames == 2
    assert consensus.ranked_classes[0].support_ratio == pytest.approx(1.0)
    assert consensus.score == pytest.approx(0.70)

    assert build_temporal_consensus([np.array([0.99, 0.01])], minimum_frame_score=0.45) is None


def test_temporal_consensus_rejects_disagreement_between_confident_frames():
    assessment = assess_temporal_consensus(
        [
            np.array([0.91, 0.08, 0.01]),
            np.array([0.10, 0.88, 0.02]),
            np.array([0.12, 0.84, 0.04]),
            np.array([0.08, 0.10, 0.82]),
            *[np.array([0.36, 0.34, 0.30]) for _ in range(25)],
        ],
        minimum_frame_score=0.5,
    )

    assert assessment.consensus is None
    assert assessment.confident_frame_count == 4
    assert assessment.required_supporting_frames == 3
    assert assessment.ranked_classes[0].class_index == 1
    assert assessment.ranked_classes[0].supporting_frame_count == 2
    assert assessment.reason == "insufficient_class_agreement"


def test_temporal_consensus_requires_three_evaluated_frames():
    assert (
        build_temporal_consensus(
            [np.array([0.90, 0.10]), np.array([0.85, 0.15])],
            minimum_frame_score=0.45,
        )
        is None
    )


def test_temporal_assessment_explains_rejected_evidence_without_accepting_it():
    assessment = assess_temporal_consensus(
        [
            np.array([0.91, 0.08, 0.01]),
            np.array([0.82, 0.17, 0.01]),
            np.array([0.18, 0.80, 0.02]),
            np.array([0.18, 0.12, 0.70]),
            np.array([0.34, 0.33, 0.33]),
        ],
        minimum_frame_score=0.5,
    )

    assert assessment.consensus is None
    assert assessment.evaluated_frame_count == 5
    assert assessment.independent_frame_count == 5
    assert assessment.confident_frame_count == 4
    assert assessment.required_supporting_frames == 3
    assert assessment.reason == "insufficient_class_agreement"
    assert assessment.ranked_classes[0].class_index == 0
    assert assessment.ranked_classes[0].supporting_frame_count == 2


def test_temporal_consensus_can_require_source_coverage_before_accepting_votes():
    scores = [
        np.array([0.91, 0.09]),
        np.array([0.88, 0.12]),
        np.array([0.86, 0.14]),
    ]

    assessment = assess_temporal_consensus(
        scores,
        minimum_frame_score=0.5,
        minimum_evaluated_frames=5,
    )

    assert assessment.consensus is None
    assert assessment.reason == "insufficient_source_coverage"
    assert assessment.evaluated_frame_count == 3


def test_temporal_consensus_counts_only_separated_moments_as_independent_support():
    assessment = assess_temporal_consensus(
        [
            np.array([0.91, 0.09]),
            np.array([0.89, 0.11]),
            np.array([0.87, 0.13]),
            np.array([0.30, 0.70]),
        ],
        minimum_frame_score=0.5,
        frame_offsets_seconds=[0.0, 0.08, 0.16, 1.0],
    )

    assert assessment.evaluated_frame_count == 4
    assert assessment.independent_frame_count == 2
    assert assessment.confident_frame_count == 2
    assert assessment.consensus is None
    assert assessment.reason == "insufficient_source_coverage"


def test_temporal_consensus_accepts_sparse_votes_at_independent_moments():
    consensus = build_temporal_consensus(
        [
            np.array([0.91, 0.09]),
            np.array([0.88, 0.12]),
            np.array([0.36, 0.34]),
        ],
        minimum_frame_score=0.5,
        frame_offsets_seconds=[0.0, 0.5, 1.0],
    )

    assert consensus is not None
    assert consensus.winner_index == 0
    assert consensus.supporting_frame_count == 2
    assert consensus.independent_frame_count == 3


def test_temporal_consensus_uses_robust_top_five_pool_for_fleeting_evidence():
    consensus = build_temporal_consensus(
        [
            np.array([0.95, 0.05]),
            np.array([0.90, 0.10]),
            np.array([0.85, 0.15]),
            np.array([0.80, 0.20]),
            np.array([0.75, 0.25]),
            np.array([0.55, 0.45]),
            np.array([0.51, 0.49]),
        ],
        minimum_frame_score=0.5,
    )

    assert consensus is not None
    assert consensus.score == pytest.approx(0.85)
    assert consensus.ranked_classes[0].pooled_frame_count == 5


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


def test_source_consensus_uses_the_only_input_path_with_temporal_evidence():
    crop_consensus = build_temporal_consensus(
        [
            np.array([0.82, 0.18]),
            np.array([0.79, 0.21]),
            np.array([0.76, 0.24]),
        ],
        minimum_frame_score=0.45,
    )

    selected = select_temporal_source_consensus(
        [SourceTemporalConsensus(input_source="frigate_hint_crop", consensus=crop_consensus)]
    )

    assert selected is not None
    assert selected.input_source == "frigate_hint_crop"
    assert selected.consensus.winner_index == 0


def test_source_consensus_abstains_when_full_frame_and_crop_disagree():
    full_consensus = build_temporal_consensus(
        [np.array([0.91, 0.09]), np.array([0.88, 0.12]), np.array([0.84, 0.16])],
        minimum_frame_score=0.45,
    )
    crop_consensus = build_temporal_consensus(
        [np.array([0.08, 0.92]), np.array([0.11, 0.89]), np.array([0.14, 0.86])],
        minimum_frame_score=0.45,
    )

    selected = select_temporal_source_consensus(
        [
            SourceTemporalConsensus(input_source="full_frame", consensus=full_consensus),
            SourceTemporalConsensus(input_source="frigate_hint_crop", consensus=crop_consensus),
        ]
    )

    assert selected is None


def test_source_consensus_prefers_stronger_evidence_when_sources_agree():
    full_consensus = build_temporal_consensus(
        [np.array([0.70, 0.30]), np.array([0.68, 0.32]), np.array([0.20, 0.80])],
        minimum_frame_score=0.45,
    )
    crop_consensus = build_temporal_consensus(
        [np.array([0.86, 0.14]), np.array([0.83, 0.17]), np.array([0.80, 0.20])],
        minimum_frame_score=0.45,
    )

    selected = select_temporal_source_consensus(
        [
            SourceTemporalConsensus(input_source="full_frame", consensus=full_consensus),
            SourceTemporalConsensus(input_source="model_crop", consensus=crop_consensus),
        ]
    )

    assert selected is not None
    assert selected.input_source == "model_crop"
    assert selected.consensus.supporting_frame_count == 3
