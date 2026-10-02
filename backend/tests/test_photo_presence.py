import pytest

from app.services.photo_presence import (
    DETECTOR_PHOTO_STRATEGY,
    attach_photo_presence,
    has_localized_bird,
    has_reusable_bird_presence,
)


def _evidence():
    return {
        "presence_source": "bird_crop_detector",
        "frame_width": 80,
        "frame_height": 60,
        "bird_box": [10, 20, 50, 50],
        "detector_confidence": 0.9,
        "crop_box": [10, 20, 50, 50],
        "input_is_cropped": True,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("presence_source", "species_classifier"),
        ("presence_source", None),
        ("detector_confidence", 0.03),
        ("detector_confidence", True),
        ("detector_confidence", float("nan")),
        ("frame_width", True),
        ("frame_height", 0),
        ("bird_box", [10, 20, 90, 50]),
        ("bird_box", [True, 20, 50, 50]),
        ("bird_box", [10, 20, 10, 50]),
        ("bird_box", [10, 20, float("nan"), 50]),
        ("crop_box", [0, 0, 10, 10]),
        ("crop_box", [10, 20, 19, 50]),
        ("crop_box", None),
    ],
)
def test_photo_presence_requires_valid_localization_inside_the_photo(field, value):
    assert not has_localized_bird({**_evidence(), field: value})


def test_localized_photo_can_include_the_whole_frame():
    assert has_localized_bird({**_evidence(), "crop_box": None, "input_is_cropped": False})
    assert has_localized_bird(_evidence())
    assert has_localized_bird({**_evidence(), "crop_box": [0, 0, 80, 60]})


@pytest.mark.parametrize("confidence", [None, True, -1, 0.02, float("nan"), float("inf"), 1.1])
def test_legacy_species_score_does_not_establish_reusable_presence(confidence):
    candidate = {
        "crop_box": [10, 20, 50, 50],
        "crop_confidence": confidence,
        "classifier_score": 0.999,
        "source_mode": "model_crop",
        "crop_strategy": "video_evidence",
    }
    assert not has_reusable_bird_presence(candidate)


def test_reusable_presence_accepts_saved_detector_evidence():
    candidate = {"crop_box": [10, 20, 50, 50], "source_mode": "model_crop", "crop_confidence": 0.9}
    assert has_reusable_bird_presence({**candidate, "crop_strategy": DETECTOR_PHOTO_STRATEGY})
    assert has_reusable_bird_presence({**candidate, "crop_confidence": 0.8})
    assert not has_reusable_bird_presence({**candidate, "crop_confidence": 0.8, "source_mode": "frigate_hint_crop"})
    assert not has_reusable_bird_presence({**candidate, "crop_strategy": DETECTOR_PHOTO_STRATEGY, "crop_box": None})
    assert not has_reusable_bird_presence(
        {**candidate, "crop_strategy": DETECTOR_PHOTO_STRATEGY, "crop_confidence": 0.03}
    )


def test_hq_presence_requires_the_same_moment_and_keeps_exploratory_boxes_unverified():
    common = {"clip_variant": "event", "frame_index": 2, "frame_width": 640, "frame_height": 480}
    bird = {
        **common,
        "candidate_id": "bird",
        "source_mode": "model_crop",
        "crop_box": [200, 100, 360, 260],
        "detector_box": [240, 140, 280, 180],
        "crop_confidence": 0.9,
    }
    whole = {**common, "candidate_id": "whole", "source_mode": "full_frame", "crop_box": None}
    other_moment = {**whole, "candidate_id": "other-moment", "frame_index": 3}
    empty_hint = {
        **common,
        "candidate_id": "empty-hint",
        "source_mode": "frigate_hint_crop",
        "crop_box": [0, 0, 160, 160],
    }
    weak = {**bird, "candidate_id": "weak", "crop_confidence": 0.03}
    missing_box = {**bird, "candidate_id": "missing-box", "detector_box": None}
    supported = attach_photo_presence([whole, other_moment, empty_hint, weak, missing_box, bird], [])
    assert {candidate["candidate_id"] for candidate in supported} == {"whole", "bird"}
    assert has_reusable_bird_presence(whole)
    assert has_reusable_bird_presence(bird)
    assert weak["crop_confidence"] == 0.03
    assert "crop_strategy" not in empty_hint


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.9, True),
        (0.55, False),
        (float("nan"), False),
        (float("inf"), False),
        (1.1, False),
        (True, False),
        ("0.9", False),
    ],
)
def test_photo_species_confidence_rejects_weak_or_invalid_scores(score, expected):
    from app.services.photo_presence import has_confident_photo_species

    assert has_confident_photo_species({"classifier_score": score}, threshold=0.7) is expected
