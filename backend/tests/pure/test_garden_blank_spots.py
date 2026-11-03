"""A known blank spot is a box where a recent automatic check found nothing."""

from app.models.garden_motion import MotionSource
from app.services.garden_automatic_policy import at_blank_spot


def source(box, *, camera="patio", detector="b" * 64):
    return MotionSource(
        camera=camera,
        clip_start=1.0,
        clip_end=11.0,
        frame_index=1,
        frame_offset=1,
        clip_sha256="a" * 64,
        image_sha256="c" * 64,
        detector_sha256=detector,
        detector_score=0.7,
        box_xywh=box,
    )


def test_a_candidate_matches_a_blank_spot_only_at_the_same_position_camera_and_detector():
    blanks = [source((0.1, 0.1, 0.2, 0.2))]
    assert at_blank_spot(source((0.11, 0.1, 0.2, 0.2)), blanks)
    assert not at_blank_spot(source((0.6, 0.6, 0.2, 0.2)), blanks)
    assert not at_blank_spot(source((0.1, 0.1, 0.2, 0.2), camera="lawn"), blanks)
    assert not at_blank_spot(source((0.1, 0.1, 0.2, 0.2), detector="d" * 64), blanks)
    assert not at_blank_spot(None, blanks)
    assert not at_blank_spot(source((0.1, 0.1, 0.2, 0.2)), [])
