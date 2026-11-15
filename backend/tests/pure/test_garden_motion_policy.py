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
    assert len(recording_queue([recording(9000, end=9900)], after=0, now=10000)) == 24


def test_queue_catches_up_within_ten_minutes_and_skips_tiny_tails():
    from app.services.garden_motion_policy import recording_queue

    assert recording_queue([recording(1500)], after=0, now=2000) == [(1500, 1510)]
    assert recording_queue([recording(1300)], after=0, now=2000) == []
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


@pytest.mark.parametrize("outcome", ["candidate", "no_candidate", "person_rejected", "unusable_recording"])
@pytest.mark.parametrize("remaining", [1, 2, 24])
def test_completed_windows_with_backlog_allow_bounded_five_second_catchup(outcome, remaining):
    from app.services.garden_motion_policy import motion_scan_interval

    assert motion_scan_interval(outcome, remaining, recent_scans=0) == 5


@pytest.mark.parametrize("outcome", [None, "failed", "paused", "storage_full", "no_recording", "not_stored"])
def test_incomplete_or_blocked_work_cannot_enable_fast_catchup(outcome):
    from app.services.garden_motion_policy import motion_scan_interval

    assert motion_scan_interval(outcome, 24, recent_scans=0) == 10


def test_drained_queue_returns_to_normal_interval():
    from app.services.garden_motion_policy import motion_scan_interval

    assert motion_scan_interval("no_candidate", 0, recent_scans=0) == 10


def test_fast_catchup_stops_once_the_cycle_budget_is_spent():
    from app.models.garden_motion import MOTION_CATCHUP_BUDGET
    from app.services.garden_motion_policy import motion_scan_interval

    # A long backlog drains at the normal pace after the budget, so a restart cannot hold a core.
    assert motion_scan_interval("no_candidate", 24, recent_scans=MOTION_CATCHUP_BUDGET - 1) == 5
    assert motion_scan_interval("no_candidate", 24, recent_scans=MOTION_CATCHUP_BUDGET) == 10


def test_recent_scans_count_only_starts_inside_the_budget_cycle():
    from app.services.garden_motion_policy import recent_scan_count

    assert recent_scan_count([100.0, 650.0, 651.0, 1249.0], now=1250.0) == 2
    assert recent_scan_count([], now=1250.0) == 0


def test_backlog_older_than_the_window_is_counted_once_as_skipped_windows():
    from app.services.garden_motion_policy import recording_queue, skipped_backlog_windows

    # The host was down; the saved cursor is an hour behind and the window keeps ten minutes.
    records = [recording(start) for start in range(400, 1800, 10)] + [recording(2900, end=2970)]
    assert skipped_backlog_windows(records, cursor=400.0, now=3000.0) == 140
    assert recording_queue(records, after=2400.0, now=3000.0) == [(2900 + i * 10, 2910 + i * 10) for i in range(7)]


def test_skipped_backlog_counts_merged_motion_up_to_the_window_floor_only():
    from app.services.garden_motion_policy import skipped_backlog_windows

    # Overlapping metadata is one interval; the part after the floor is still queued, not skipped.
    records = [recording(2300, end=2420), recording(2310, end=2350), recording(2200, motion=0)]
    assert skipped_backlog_windows(records, cursor=2250.0, now=3000.0) == 10


@pytest.mark.parametrize("cursor", [None, 2400.0, 2900.0])
def test_nothing_is_skipped_without_a_cursor_or_when_the_cursor_is_inside_the_window(cursor):
    from app.services.garden_motion_policy import skipped_backlog_windows

    assert skipped_backlog_windows([recording(start) for start in range(0, 2990, 10)], cursor=cursor, now=3000.0) == 0


@pytest.mark.parametrize("bad", [None, {}, [recording(True)], [recording(1, end=2)] * 2049])
def test_invalid_or_unbounded_recording_metadata_skips_nothing(bad):
    from app.services.garden_motion_policy import skipped_backlog_windows

    assert skipped_backlog_windows(bad, cursor=100.0, now=3000.0) == 0
