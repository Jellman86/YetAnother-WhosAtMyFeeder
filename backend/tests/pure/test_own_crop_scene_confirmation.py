"""Own-crop classifier evidence reaches the confirmed scene count only through bound decisions."""

import pytest

from app.services.bird_observation_selection import select_bird_observations, select_scene_birds
from app.services.bird_physical_confirmation import (
    PhysicalGroupEvidence,
    decide_physical_bird,
    physical_group_evidence,
)


MODEL = "a" * 64
MAPPING = "b" * 64
CROP = "c" * 64
OTHER = "d" * 64


def group_output(*, bird_mass, nonbird_mass, top_group, model=MODEL, mapping=MAPPING):
    """The shape the classifier attaches to each result as `taxonomic_evidence`."""
    return {
        "model_sha256": model,
        "mapping_sha256": mapping,
        "output_width": 3,
        "bird_outputs": 1,
        "nonbird_outputs": 1,
        "bird_mass": bird_mass,
        "nonbird_mass": nonbird_mass,
        "unknown_mass": round(1.0 - bird_mass - nonbird_mass, 10),
        "top_group": top_group,
    }


def own_crop_decision(confidence, output, *, crop_sha256=CROP, expected_crop_sha256=CROP):
    return decide_physical_bird(
        confidence,
        finder_qualified=True,
        evidence=physical_group_evidence(output, crop_sha256=crop_sha256),
        expected_model_sha256=MODEL,
        expected_mapping_sha256=MAPPING,
        expected_crop_sha256=expected_crop_sha256,
    )


def proposal(name, box, confidence):
    return {
        "candidate_id": name,
        "source_mode": "model_observation",
        "clip_variant": "recording",
        "frame_index": 1,
        "crop_box": box,
        "crop_confidence": confidence,
        "classifier_label": None,
        "classifier_score": 0.0,
    }


def scene(rows, decisions=None, *, confirmed_finder=True):
    return select_scene_birds(
        rows, selected_candidate=None, confirmed_finder=confirmed_finder, physical_decisions=decisions
    )


def test_group_output_and_crop_digest_become_bound_physical_evidence():
    output = group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird")
    assert physical_group_evidence(output, crop_sha256=CROP) == PhysicalGroupEvidence(
        model_sha256=MODEL,
        mapping_sha256=MAPPING,
        crop_sha256=CROP,
        output_width=3,
        bird_outputs=1,
        nonbird_outputs=1,
        bird_mass=0.7,
        nonbird_mass=0.2,
        unknown_mass=output["unknown_mass"],
        top_group="bird",
    )


@pytest.mark.parametrize(
    "output",
    [
        None,
        [],
        "bird",
        {},
        {
            key: value
            for key, value in group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird").items()
            if key != "bird_mass"
        },
    ],
)
def test_a_classification_without_group_output_gives_no_evidence(output):
    # A bird-only model attaches no group summary, so its crop stays unconfirmed, not unbound.
    assert physical_group_evidence(output, crop_sha256=CROP) is None
    assert own_crop_decision(0.45, output).reason == "confirmation_unavailable"


def test_stand_alone_mid_band_box_with_bird_mass_is_counted_from_its_own_crop():
    decisions = {"bird": own_crop_decision(0.45, group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird"))}
    result = scene([proposal("bird", (10, 10, 60, 60), 0.45)], decisions)
    assert [bird.candidate_id for bird in result.birds] == ["bird"]
    assert result.count_status == "complete"
    assert result.unconfirmed_regions == ()


def test_stand_alone_mid_band_box_the_classifier_calls_a_nonbird_is_excluded():
    decisions = {
        "fixture": own_crop_decision(0.45, group_output(bird_mass=0.05, nonbird_mass=0.9, top_group="nonbird"))
    }
    result = scene([proposal("fixture", (10, 10, 60, 60), 0.45)], decisions)
    assert result.birds == ()
    assert [(r.candidate_id, r.reason) for r in result.excluded_regions] == [("fixture", "own_crop_nonbird")]
    assert result.unconfirmed_regions == ()
    assert result.count_status == "complete"


@pytest.mark.parametrize(
    ("output", "crop_sha256"),
    [
        (group_output(bird_mass=0.95, nonbird_mass=0.0, top_group="bird"), CROP),
        (group_output(bird_mass=0.3, nonbird_mass=0.3, top_group="unknown"), CROP),
        (group_output(bird_mass=0.95, nonbird_mass=0.0, top_group="bird"), OTHER),
        (group_output(bird_mass=0.05, nonbird_mass=0.9, top_group="nonbird"), CROP),
        (None, CROP),
    ],
)
def test_mid_band_box_sharing_pixels_with_a_counted_bird_stays_uncounted_whatever_its_evidence(output, crop_sha256):
    rows = [proposal("bird", (0, 0, 100, 100), 0.9), proposal("part", (80, 20, 140, 80), 0.45)]
    result = scene(rows, {"part": own_crop_decision(0.45, output, crop_sha256=crop_sha256)})
    assert [bird.candidate_id for bird in result.birds] == ["bird"]
    assert [(r.candidate_id, r.reason) for r in result.unconfirmed_regions] == [("part", "shares_counted_pixels")]
    assert result.excluded_regions == ()
    assert result.count_status == "incomplete"


@pytest.mark.parametrize(
    ("output", "crop_sha256"),
    [
        (group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird", model=OTHER), CROP),
        (group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird", mapping=OTHER), CROP),
        (group_output(bird_mass=0.7, nonbird_mass=0.2, top_group="bird"), OTHER),
    ],
)
def test_evidence_bound_to_another_model_mapping_or_crop_is_unbound(output, crop_sha256):
    decision = own_crop_decision(0.45, output, crop_sha256=crop_sha256)
    result = scene([proposal("bird", (10, 10, 60, 60), 0.45)], {"bird": decision})
    assert result.birds == ()
    assert [(r.candidate_id, r.reason) for r in result.unconfirmed_regions] == [("bird", "unbound_confirmation")]
    assert result.count_status == "incomplete"


RECORDED_SCENE = [
    proposal("left", (1188, 543, 1424, 713), 0.840707),
    proposal("right", (1754, 476, 1932, 650), 0.794037),
    proposal("shared-foot", (1684, 573, 1802, 664), 0.463924),
    proposal("seed-port", (1605, 623, 1661, 659), 0.302040),
    proposal("alone", (100, 100, 160, 160), 0.41),
    {**proposal("photo-crop", (1188, 543, 1424, 713), 0.840707), "source_mode": "model_crop"},
    {**proposal("scene", (0, 0, 3840, 2160), None), "source_mode": "full_frame"},
]


@pytest.mark.parametrize("no_evidence", [None, {}])
def test_scene_count_without_evidence_is_exactly_the_strong_detector_count(no_evidence):
    without = select_scene_birds(RECORDED_SCENE, selected_candidate=None, confirmed_finder=True)
    assert scene(RECORDED_SCENE, no_evidence) == without
    assert [bird.candidate_id for bird in without.birds] == ["left", "right"]
    assert {r.candidate_id: r.reason for r in without.unconfirmed_regions} == {
        "shared-foot": "shares_counted_pixels",
        "seed-port": "confirmation_unavailable",
        "alone": "confirmation_unavailable",
    }


def test_unconfirmed_finder_ignores_evidence_and_keeps_the_earlier_count():
    decisions = {
        name: own_crop_decision(0.45, group_output(bird_mass=0.05, nonbird_mass=0.9, top_group="nonbird"))
        for name in ("left", "right", "shared-foot", "seed-port", "alone")
    }
    result = scene(RECORDED_SCENE, decisions, confirmed_finder=False)
    assert result == select_bird_observations(RECORDED_SCENE, selected_candidate=None)
    assert result == select_scene_birds(RECORDED_SCENE, selected_candidate=None, confirmed_finder=False)
    assert result.count_status == "legacy"
