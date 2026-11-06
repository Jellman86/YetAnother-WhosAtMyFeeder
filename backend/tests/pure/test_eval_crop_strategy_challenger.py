import pytest

from scripts.eval_crop_strategy_challenger import (
    compare_expected_outcomes,
    select_guarded_crop_prediction,
    summarize_rows,
    validate_manifest,
)


def _prediction(label: str, score: float) -> dict:
    return {"label": label, "score": score}


def test_expected_outcome_comparison_requires_real_model_improvement():
    expected = ["Columba palumbus", "Wood Pigeon"]

    assert compare_expected_outcomes(
        frigate_prediction=_prediction("Columba palumbus", 0.88),
        model_prediction=_prediction("Columba palumbus", 0.89),
        expected_labels=expected,
    ) == ("tie", "both_correct_within_margin")
    assert compare_expected_outcomes(
        frigate_prediction=_prediction("Columba palumbus", 0.84),
        model_prediction=_prediction("Columba palumbus", 0.90),
        expected_labels=expected,
    ) == ("win", "both_correct_model_confidence_gain")
    assert compare_expected_outcomes(
        frigate_prediction=_prediction("Columba palumbus", 0.90),
        model_prediction=_prediction("Accipiter nisus", 0.92),
        expected_labels=expected,
    ) == ("loss", "frigate_only_correct")


def test_expected_outcome_comparison_does_not_score_automatic_context():
    assert compare_expected_outcomes(
        frigate_prediction=_prediction("Columba palumbus", 0.80),
        model_prediction=_prediction("Columba palumbus", 0.95),
        expected_labels=[],
    ) == ("unscored", "no_owner_ground_truth")


def test_guarded_selection_only_promotes_same_identity_with_real_gain():
    frigate = _prediction("Columba palumbus", 0.80)
    improved = _prediction("Columba palumbus", 0.85)
    regressed = _prediction("Columba palumbus", 0.70)
    mismatch = _prediction("Accipiter nisus", 0.99)

    assert select_guarded_crop_prediction(
        frigate_prediction=frigate,
        model_prediction=improved,
    ) == (improved, "model_crop", "same_identity_model_gain")
    assert select_guarded_crop_prediction(
        frigate_prediction=frigate,
        model_prediction=regressed,
    ) == (frigate, "frigate_hint_crop", "insufficient_model_gain")
    assert select_guarded_crop_prediction(
        frigate_prediction=frigate,
        model_prediction=mismatch,
    ) == (frigate, "frigate_hint_crop", "identity_mismatch")


def test_strategy_summary_separates_quality_evidence_from_false_crops():
    summary = summarize_rows(
        [
            {
                "is_negative": False,
                "outcome": "win",
                "guarded_outcome": "win",
                "guarded_selected_source": "model_crop",
                "guarded_selection_reason": "same_identity_model_gain",
                "model_strategy": "frigate_guided",
                "detector_ms": 10,
            },
            {
                "is_negative": False,
                "outcome": "tie",
                "guarded_outcome": "tie",
                "guarded_selected_source": "frigate_hint_crop",
                "guarded_selection_reason": "insufficient_model_gain",
                "model_strategy": "native",
                "detector_ms": 20,
            },
            {"is_negative": False, "outcome": "unscored", "model_strategy": None, "detector_ms": 30},
            {
                "is_negative": True,
                "model_crop_found": True,
                "model_prediction": _prediction("Foliage", 0.30),
                "model_strategy": "sliced_2x2",
                "detector_ms": 40,
            },
            {"is_negative": True, "model_crop_found": False, "model_strategy": None, "detector_ms": 50},
        ]
    )

    assert summary["scored_positive_cases"] == 2
    assert summary["wins"] == 1
    assert summary["ties"] == 1
    assert summary["losses"] == 0
    assert summary["negative_cases"] == 2
    assert summary["negative_model_crop_count"] == 1
    assert summary["negative_high_confidence_crop_count"] == 0
    assert summary["guarded_model_promotions"] == 1
    assert summary["guarded_frigate_retentions"] == 1
    assert summary["guarded_wins"] == 1
    assert summary["guarded_ties"] == 1
    assert summary["guarded_losses"] == 0
    assert summary["strategies"] == {"frigate_guided": 1, "native": 1, "sliced_2x2": 1}
    assert summary["detector_latency_ms"] == {"p50": 30.0, "p95": 48.0, "max": 50.0}


def test_manifest_validation_requires_owner_provenance_and_independent_visits():
    valid_case = {
        "id": "positive-1",
        "visit_id": "event-1",
        "image_path": "/private/frame.jpg",
        "boxes": [[1, 2, 30, 40]],
        "expected_labels": ["Robin"],
        "label_source": "owner_manual",
    }
    assert validate_manifest({"version": "3", "cases": [valid_case]}) == [valid_case]

    with pytest.raises(ValueError, match="owner_manual"):
        validate_manifest(
            {
                "version": "3",
                "cases": [{**valid_case, "label_source": "automatic_context_only"}],
            }
        )

    with pytest.raises(ValueError, match="Duplicate positive visit"):
        validate_manifest(
            {
                "version": "3",
                "cases": [valid_case, {**valid_case, "id": "positive-2"}],
            }
        )


def test_manifest_validation_rejects_stale_or_ambiguous_panels():
    with pytest.raises(ValueError, match="manifest version 3"):
        validate_manifest({"version": "2", "cases": []})

    with pytest.raises(ValueError, match="zero or one"):
        validate_manifest(
            {
                "version": "3",
                "cases": [
                    {
                        "id": "positive-1",
                        "visit_id": "event-1",
                        "image_path": "/private/frame.jpg",
                        "boxes": [[1, 2, 30, 40], [2, 3, 31, 41]],
                    }
                ],
            }
        )
