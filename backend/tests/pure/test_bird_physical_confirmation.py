from dataclasses import replace

import pytest

from app.services.bird_physical_confirmation import PhysicalGroupEvidence, decide_physical_bird


MODEL = "a" * 64
MAPPING = "b" * 64
CROP = "c" * 64


def evidence(**changes):
    base = PhysicalGroupEvidence(
        model_sha256=MODEL,
        mapping_sha256=MAPPING,
        crop_sha256=CROP,
        output_width=3,
        bird_outputs=1,
        nonbird_outputs=1,
        bird_mass=0.6,
        nonbird_mass=0.3,
        unknown_mass=0.1,
        top_group="bird",
    )
    return replace(base, **changes)


def decide(confidence, proof=None, **changes):
    arguments = {
        "finder_qualified": True,
        "evidence": proof,
        "expected_model_sha256": MODEL,
        "expected_mapping_sha256": MAPPING,
        "expected_crop_sha256": CROP,
    }
    arguments.update(changes)
    return decide_physical_bird(confidence, **arguments)


def test_strong_qualified_detector_does_not_need_a_species_name():
    result = decide(0.6)
    assert (result.verdict, result.reason) == ("counted", "strong_detector")


def test_unqualified_finder_cannot_publish_a_count_even_with_a_high_score():
    assert decide(0.99, evidence(), finder_qualified=False).verdict == "unconfirmed"


def test_mid_band_bird_mass_counts_without_confident_species_identity():
    # Mass belongs to the entire bird group; no individual species score is required.
    result = decide(0.35, evidence(bird_mass=0.5, nonbird_mass=0.4))
    assert (result.verdict, result.reason) == ("counted", "own_crop_bird")


def test_confident_own_pixel_nonbird_group_excludes_a_mid_band_fixture():
    result = decide(0.35, evidence(bird_mass=0.05, nonbird_mass=0.85, top_group="nonbird"))
    assert (result.verdict, result.reason) == ("excluded", "own_crop_nonbird")


def test_partial_bird_with_uncertain_nonbird_guess_is_not_excluded():
    result = decide(0.35, evidence(bird_mass=0.4, nonbird_mass=0.5, top_group="nonbird"))
    assert result.verdict == "unconfirmed"


def test_conflicting_strong_detector_and_own_pixel_nonbird_evidence_abstains():
    result = decide(0.9, evidence(bird_mass=0.05, nonbird_mass=0.85, top_group="nonbird"))
    assert (result.verdict, result.reason) == ("unconfirmed", "conflicting_confirmation")


@pytest.mark.parametrize("field", ["expected_model_sha256", "expected_mapping_sha256", "expected_crop_sha256"])
def test_confirmation_must_match_the_actual_model_mapping_and_own_pixels(field):
    assert decide(0.35, evidence(), **{field: "d" * 64}).verdict == "unconfirmed"


@pytest.mark.parametrize("value", [None, -0.1, 1.1, float("nan"), float("inf"), True, "0.9", 10**1000])
def test_malformed_detector_evidence_does_not_count(value):
    assert decide(value, evidence()).verdict == "unconfirmed"


def test_below_floor_box_is_not_rescued_by_classification():
    assert decide(0.07, evidence(bird_mass=0.9, nonbird_mass=0.0)).verdict == "unconfirmed"


def test_missing_confirmation_never_means_empty_or_a_confirmed_bird():
    assert decide(0.35).verdict == "unconfirmed"


@pytest.mark.parametrize(
    "changes",
    [
        {"bird_mass": float("nan")},
        {"nonbird_mass": -0.1},
        {"unknown_mass": 1.1},
        {"bird_mass": 0.9},
        {"bird_outputs": True},
        {"output_width": 0},
        {"nonbird_outputs": 4},
        {"model_sha256": "not-a-digest"},
        {"top_group": "animal"},
        {"top_group": []},
        {"bird_mass": 10**1000},
    ],
)
def test_invalid_mass_or_binding_is_unconfirmed(changes):
    assert decide(0.35, evidence(**changes)).verdict == "unconfirmed"


def test_bird_only_classifier_mass_is_not_presence_evidence():
    proof = evidence(bird_outputs=3, nonbird_outputs=0, bird_mass=1.0, nonbird_mass=0.0, unknown_mass=0.0)
    assert decide(0.35, proof).verdict == "unconfirmed"


def test_nonbird_only_classifier_cannot_establish_absence_either():
    proof = evidence(
        bird_outputs=0,
        nonbird_outputs=3,
        bird_mass=0.0,
        nonbird_mass=1.0,
        unknown_mass=0.0,
        top_group="nonbird",
    )
    assert decide(0.35, proof).verdict == "unconfirmed"


def test_unknown_mass_is_not_renormalized_into_bird_evidence():
    proof = evidence(bird_mass=0.49, nonbird_mass=0.31, unknown_mass=0.2)
    assert decide(0.35, proof).verdict == "unconfirmed"
