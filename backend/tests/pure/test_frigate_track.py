"""Frigate's tracked path is untrusted input: parse what is well formed, skip the rest."""

import pytest

from app.utils.frigate_track import (
    box_at_path_point,
    compact_frigate_path_data,
    frigate_path_points,
    nearest_path_point,
)

RAW_PATH = [
    [[0.2, 0.3], 100.0],
    [[1.2, 0.3], 101.0],
    [[0.2, float("nan")], 102.0],
    [[0.4], 103.0],
    ["not a point", 104.0],
    [[0.5, 0.6], "late"],
    [[0.7, 0.8], 105],
    [[0.1, 0.1]],
]


def test_path_points_keep_only_finite_positions_inside_the_frame_by_default():
    assert frigate_path_points(RAW_PATH) == [(100.0, 0.2, 0.3), (105.0, 0.7, 0.8)]


def test_path_points_outside_the_frame_are_kept_when_asked():
    assert frigate_path_points(RAW_PATH, within_frame=False) == [
        (100.0, 0.2, 0.3),
        (101.0, 1.2, 0.3),
        (105.0, 0.7, 0.8),
    ]


@pytest.mark.parametrize("raw", [None, [], "path", {"x": 1}])
def test_a_missing_or_malformed_path_has_no_points(raw):
    assert frigate_path_points(raw) == []


def test_the_nearest_point_must_be_close_enough_in_time():
    points = [(100.0, 0.2, 0.3), (102.0, 0.8, 0.9)]

    assert nearest_path_point(points, 101.9, max_distance_seconds=0.75) == (102.0, 0.8, 0.9)
    assert nearest_path_point(points, 101.0, max_distance_seconds=0.75) is None
    assert nearest_path_point(points, 101.0, max_distance_seconds=1.0) == (100.0, 0.2, 0.3)
    assert nearest_path_point([], 100.0, max_distance_seconds=10.0) is None


def test_the_box_sits_on_its_bottom_centre_and_stays_inside_the_frame():
    assert box_at_path_point((0.0, 0.5, 0.6), width=0.2, height=0.2) == pytest.approx([0.4, 0.4, 0.2, 0.2])
    assert box_at_path_point((0.0, 0.05, 0.1), width=0.2, height=0.2) == [0.0, 0.0, 0.2, 0.2]
    assert box_at_path_point((0.0, 0.99, 1.0), width=0.2, height=0.2) == pytest.approx([0.8, 0.8, 0.2, 0.2])


def test_compaction_keeps_raw_values_of_well_shaped_entries_up_to_the_limit():
    raw = [[[0.1, 0.2, 9], "t1"], ["junk"], [(0.3, 0.4), 2.0], [[0.5, 0.6], 3.0]]

    assert compact_frigate_path_data(raw, limit=3) == [[[0.1, 0.2], "t1"], [[0.3, 0.4], 2.0]]
