"""One displayed photo choice can stand for several candidate rows of one frame (#1107)."""

import pytest

from app.services.photo_choice_membership import (
    PhotoChoiceNotFound,
    PhotoChoiceRequestError,
    resolve_photo_choice,
)


def candidate(candidate_id, source_mode="model_crop", *, frame_index=3, clip_variant="event"):
    return {
        "candidate_id": candidate_id,
        "source_mode": source_mode,
        "frame_index": frame_index,
        "clip_variant": clip_variant,
    }


FRAME = [
    candidate("crop", "model_crop"),
    candidate("hint", "frigate_hint_crop"),
    candidate("scene", "full_frame"),
    candidate("hq-scene", "hq_candidate_full_frame"),
    candidate("other-frame", "model_crop", frame_index=9),
    candidate("other-clip", "model_crop", clip_variant="recording"),
    candidate("evidence", "model_observation"),
    candidate("earlier", "retained_photo"),
]


def test_a_folded_choice_resolves_every_framing_of_its_frame_with_the_shown_one_first():
    members = resolve_photo_choice(FRAME, "crop", ["hint", "scene", "hq-scene"])
    assert [member["candidate_id"] for member in members] == ["crop", "hint", "scene", "hq-scene"]


def test_a_single_candidate_without_companions_behaves_as_before():
    assert [member["candidate_id"] for member in resolve_photo_choice(FRAME, "crop", None)] == ["crop"]
    assert [member["candidate_id"] for member in resolve_photo_choice(FRAME, "earlier", [])] == ["earlier"]


def test_the_as_recorded_photo_has_no_candidate_rows():
    assert resolve_photo_choice(FRAME, "as-recorded", None) == []


@pytest.mark.parametrize(
    ("candidate_id", "companions"),
    [
        ("crop", ["crop"]),
        ("crop", ["hint", "hint"]),
        ("crop", ["  "]),
        ("as-recorded", ["crop"]),
        ("crop", ["as-recorded"]),
        ("earlier", ["crop"]),
        ("crop", ["earlier"]),
        ("evidence", None),
        ("crop", ["evidence"]),
        ("crop", ["other-frame"]),
        ("crop", ["other-clip"]),
    ],
)
def test_a_choice_that_is_not_one_frames_photographs_is_refused(candidate_id, companions):
    with pytest.raises(PhotoChoiceRequestError):
        resolve_photo_choice(FRAME, candidate_id, companions)


@pytest.mark.parametrize(("candidate_id", "companions"), [("missing", None), ("crop", ["another-capture"])])
def test_a_candidate_of_another_capture_is_not_found(candidate_id, companions):
    with pytest.raises(PhotoChoiceNotFound):
        resolve_photo_choice(FRAME, candidate_id, companions)
