import numpy as np
import pytest

from app.services.video_classification_policy import (
    SourceTemporalConsensus,
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
