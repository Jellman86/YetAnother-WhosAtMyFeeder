"""Motion selection cannot change bird routing or manufacture Frigate events."""

import math

import pytest

from app.services.garden_motion_policy import (
    MotionSource,
    camera_pressure,
    choose_segment,
    motion_key,
)


def recording(start, *, motion=10, end=None):
    return {"start_time": start, "end_time": end or start + 10, "motion": motion, "objects": 0}


def test_motion_selection_uses_completed_recent_motion_and_durable_cursor():
    records = [recording(920), recording(960), recording(940, motion=0), recording(990), recording(100)]
    assert choose_segment(records, after=925, now=1000) == (925, 930)
    assert choose_segment(records, after=970, now=1000) is None
    assert choose_segment(list(reversed(records)), after=925, now=1000) == (925, 930)


@pytest.mark.parametrize("bad", [None, {}, "recordings", [{"start_time": math.nan}], [recording(True)]])
def test_invalid_recordings_are_never_selected(bad):
    assert choose_segment(bad, after=900, now=1000) is None


def test_segment_download_window_is_bounded_even_for_long_recordings():
    assert choose_segment([recording(950, end=975)], after=900, now=1000) == (950, 960)


def test_recording_remainder_is_resumed_after_cursor_instead_of_skipped():
    assert choose_segment([recording(950, end=975)], after=960, now=1000) == (960, 970)
    assert choose_segment([recording(950, end=975)], after=970, now=1000) == (970, 975)


def test_queue_is_bounded_ordered_and_does_not_double_scan_overlapping_recordings():
    from app.services.garden_motion_policy import recording_queue

    records = [recording(900, end=975), recording(910, end=950), recording(900, end=975)]
    windows = recording_queue(records, after=900, now=1000)
    assert windows == [(900, 910), (910, 920), (920, 930), (930, 940), (940, 950), (950, 960), (960, 970), (970, 975)]
    assert recording_queue(list(reversed(records)), after=900, now=1000) == windows
    assert len(recording_queue([recording(1, end=9900)], after=0, now=10000)) == 24


def test_queue_catches_up_within_thirty_minutes_and_skips_tiny_tails():
    from app.services.garden_motion_policy import recording_queue

    assert recording_queue([recording(500)], after=0, now=2000) == [(500, 510)]
    assert recording_queue([recording(100)], after=0, now=2000) == []
    assert recording_queue([recording(1950, end=1960.05)], after=1960, now=2000) == []
    assert recording_queue([recording(950, motion=0)], after=900, now=1000) == []


def test_any_active_camera_pressure_refuses_collection_even_when_app_queues_are_empty():
    cameras = {
        "patio": {"detection_enabled": True, "camera_fps": 10, "process_fps": 10, "skipped_fps": 0},
        "birdcam": {"detection_enabled": True, "camera_fps": 10, "process_fps": 8.6, "skipped_fps": 1.2},
    }
    assert camera_pressure({"cameras": cameras}, "patio")
    cameras["birdcam"].update(process_fps=10, skipped_fps=0)
    assert not camera_pressure({"cameras": cameras}, "patio")
    for stats in (None, {}, {"cameras": {}}, {"cameras": {"patio": {}}}):
        assert camera_pressure(stats, "patio")
    cameras["birdcam"]["skipped_fps"] = math.nan
    assert camera_pressure({"cameras": cameras}, "patio")


def source(**update):
    return MotionSource.model_validate(
        dict(
            camera="patio",
            clip_start=950,
            clip_end=960,
            frame_index=25,
            frame_offset=1,
            clip_sha256="a" * 64,
            image_sha256="b" * 64,
            detector_sha256="c" * 64,
            detector_score=0.8,
            box_xywh=(0.1, 0.2, 0.3, 0.4),
            **update,
        )
    )


def test_source_identity_deduplicates_reprocessing_without_inventing_an_event_id():
    original = source()
    changed_model = original.model_copy(update={"detector_sha256": "d" * 64, "frame_index": 50})
    assert motion_key(original) == motion_key(changed_model)
    assert motion_key(original) != motion_key(original.model_copy(update={"camera": "other"}))
    assert len(motion_key(original)) == 64
    assert "frigate_event" not in MotionSource.model_fields


@pytest.mark.parametrize(
    "change",
    [
        {"camera": "../patio"},
        {"clip_end": 1000},
        {"frame_offset": 11},
        {"box_xywh": (0.9, 0, 0.2, 1)},
        {"image_sha256": "unknown"},
        {"detector_score": math.nan},
    ],
)
def test_provenance_rejects_unsafe_or_unbound_evidence(change):
    values = source().model_dump()
    values.update(change)
    with pytest.raises(ValueError):
        MotionSource.model_validate(values)
