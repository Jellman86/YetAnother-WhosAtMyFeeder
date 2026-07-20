from types import SimpleNamespace

import pytest

from app.services.hq_classification_refinement import choose_hq_classification_refinement


def _candidate(
    frame_index: int,
    label: str,
    score: float,
    *,
    source_mode: str = "frigate_hint_crop",
    candidate_id: str | None = None,
    frame_offset_seconds: float | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id or f"{source_mode}-{frame_index}",
        "frame_index": frame_index,
        "frame_offset_seconds": (
            frame_offset_seconds if frame_offset_seconds is not None else float(frame_index) / 30.0
        ),
        "source_mode": source_mode,
        "classifier_label": label,
        "classifier_score": score,
        "classifier_index": frame_index + 100,
    }


def _detection(**overrides):
    values = {
        "display_name": "Unknown Bird",
        "category_name": "Unknown Bird",
        "scientific_name": None,
        "common_name": None,
        "score": 0.52,
        "manual_tagged": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_promotes_multi_frame_crop_consensus_over_unknown_detection():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.82),
            _candidate(20, "Columba palumbus", 0.80),
            _candidate(30, "Columba palumbus", 0.61),
            _candidate(10, "Aegithalos caudatus", 0.09, source_mode="full_frame"),
        ],
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.label == "Columba palumbus"
    assert decision.score == 0.82
    assert decision.supporting_frame_count == 3
    assert decision.reason == "upgrade_unknown_from_crop_consensus"


def test_rejects_single_frame_even_when_two_crop_sources_agree():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.94, source_mode="frigate_hint_crop"),
            _candidate(10, "Columba palumbus", 0.91, source_mode="model_crop"),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_rejects_adjacent_frames_as_correlated_evidence():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(0, "Columba palumbus", 0.94, frame_offset_seconds=0.0),
            _candidate(1, "Columba palumbus", 0.92, frame_offset_seconds=1 / 30),
            _candidate(2, "Columba palumbus", 0.90, frame_offset_seconds=2 / 30),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_accepts_only_the_temporally_independent_subset():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(0, "Columba palumbus", 0.94, frame_offset_seconds=0.0),
            _candidate(1, "Columba palumbus", 0.93, frame_offset_seconds=1 / 30),
            _candidate(30, "Columba palumbus", 0.82, frame_offset_seconds=1.0),
        ],
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.supporting_frame_count == 2
    assert decision.median_score == pytest.approx(0.88)


def test_rejects_candidates_without_temporal_provenance():
    candidate = _candidate(10, "Columba palumbus", 0.94)
    candidate.pop("frame_offset_seconds")
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[candidate, _candidate(20, "Columba palumbus", 0.92)],
        minimum_score=0.60,
    )

    assert decision is None


def test_rejects_low_confidence_multi_frame_crop_consensus():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Turdus fuscater", 0.14),
            _candidate(20, "Turdus fuscater", 0.13),
            _candidate(30, "Turdus fuscater", 0.12),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_never_replaces_manual_identification():
    decision = choose_hq_classification_refinement(
        detection=_detection(manual_tagged=True),
        candidates=[
            _candidate(10, "Columba palumbus", 0.96),
            _candidate(20, "Columba palumbus", 0.95),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_does_not_replace_a_conflicting_known_species():
    decision = choose_hq_classification_refinement(
        detection=_detection(
            display_name="Wood Pigeon",
            category_name="Columba palumbus",
            scientific_name="Columba palumbus",
            common_name="Wood Pigeon",
            score=0.87,
        ),
        candidates=[
            _candidate(10, "Turdus fuscater", 0.93),
            _candidate(20, "Turdus fuscater", 0.91),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_reinforces_same_known_species_only_when_score_materially_improves():
    detection = _detection(
        display_name="Wood Pigeon",
        category_name="Columba palumbus",
        scientific_name="Columba palumbus",
        common_name="Wood Pigeon",
        score=0.82,
    )
    candidates = [
        _candidate(10, "Columba_palumbus", 0.88),
        _candidate(20, "Columba palumbus", 0.86),
    ]

    decision = choose_hq_classification_refinement(
        detection=detection,
        candidates=candidates,
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.label == "Columba palumbus"
    assert decision.reason == "reinforce_existing_from_crop_consensus"


def test_rejects_ambiguous_competing_multi_frame_consensus():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.80),
            _candidate(20, "Columba palumbus", 0.78),
            _candidate(30, "Streptopelia decaocto", 0.76),
            _candidate(40, "Streptopelia decaocto", 0.75),
        ],
        minimum_score=0.60,
    )

    assert decision is None
