"""Folding UTC hour counts into the viewer's weekday-by-hour grid, without a database or a clock."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.weekday_hour_grid import weekday_hour_grid


def _count_at(grid, day_of_week: int, hour: int) -> int:
    return next(cell.count for cell in grid.cells if cell.day_of_week == day_of_week and cell.hour == hour)


def test_grid_always_has_every_weekday_and_hour_with_sunday_first():
    grid = weekday_hour_grid([], ZoneInfo("UTC"))

    assert len(grid.cells) == 7 * 24
    assert (grid.cells[0].day_of_week, grid.cells[0].hour) == (0, 0)
    assert (grid.cells[-1].day_of_week, grid.cells[-1].hour) == (6, 23)
    assert grid.total_count == 0
    assert grid.max_cell_count == 0


def test_utc_hours_land_on_the_viewers_local_weekday_and_hour_across_an_offset():
    # Monday 2026-11-16 23:00 UTC is already Tuesday 12:00 in Auckland (UTC+13 in November),
    # and Tuesday 01:00 UTC is still Monday 20:00 in New York (UTC-5).
    counts = [(datetime(2026, 11, 16, 23, 0), 4), (datetime(2026, 11, 17, 1, 0), 2)]

    auckland = weekday_hour_grid(counts, ZoneInfo("Pacific/Auckland"))
    assert _count_at(auckland, 2, 12) == 4  # Tuesday noon
    assert _count_at(auckland, 2, 14) == 2  # Tuesday 14:00
    assert _count_at(auckland, 1, 23) == 0  # nothing left on the UTC Monday slot

    new_york = weekday_hour_grid(counts, ZoneInfo("America/New_York"))
    assert _count_at(new_york, 1, 18) == 4  # Monday 18:00
    assert _count_at(new_york, 1, 20) == 2  # Monday 20:00


def test_hours_that_meet_in_one_local_slot_are_added_and_the_peak_and_total_follow():
    # The same UTC hour on two different Mondays falls in one weekday slot.
    counts = [
        (datetime(2026, 11, 9, 8, 0), 3),
        (datetime(2026, 11, 16, 8, 0), 5),
        (datetime(2026, 11, 17, 9, 0), 1),
    ]

    grid = weekday_hour_grid(counts, ZoneInfo("UTC"))

    assert _count_at(grid, 1, 8) == 8
    assert grid.max_cell_count == 8
    assert grid.total_count == 9


def test_a_zero_or_negative_bucket_counts_nothing():
    grid = weekday_hour_grid([(datetime(2026, 11, 16, 8, 0), 0), (datetime(2026, 11, 16, 9, 0), -3)], ZoneInfo("UTC"))

    assert grid.total_count == 0
    assert grid.max_cell_count == 0


def test_london_spring_forward_skips_the_missing_hour_and_autumn_fall_back_adds_the_repeated_one():
    london = ZoneInfo("Europe/London")

    # Sunday 29 March 2026: 00:00 UTC is 00:00 GMT, then 01:00 UTC is already 02:00 BST.
    spring = weekday_hour_grid([(datetime(2026, 3, 29, 0, 0), 2), (datetime(2026, 3, 29, 1, 0), 5)], london)
    assert _count_at(spring, 0, 0) == 2
    assert _count_at(spring, 0, 1) == 0  # 01:00 never happened that night
    assert _count_at(spring, 0, 2) == 5

    # Sunday 25 October 2026: 00:00 UTC is 01:00 BST and 01:00 UTC is 01:00 GMT, one local hour twice.
    autumn = weekday_hour_grid([(datetime(2026, 10, 25, 0, 0), 3), (datetime(2026, 10, 25, 1, 0), 4)], london)
    assert _count_at(autumn, 0, 1) == 7
    assert _count_at(autumn, 0, 0) == 0
    assert _count_at(autumn, 0, 2) == 0
    assert autumn.total_count == 7
    assert autumn.max_cell_count == 7


def test_a_quarter_hour_bucket_in_a_half_hour_zone_lands_in_the_hour_it_was_heard():
    # 18:30 and 18:45 UTC on Tuesday are 00:00 and 00:15 on Wednesday in India (UTC+5:30); 18:15 is 23:45 on Tuesday.
    counts = [
        (datetime(2026, 11, 24, 18, 15), 1),
        (datetime(2026, 11, 24, 18, 30), 2),
        (datetime(2026, 11, 24, 18, 45), 4),
    ]

    grid = weekday_hour_grid(counts, ZoneInfo("Asia/Kolkata"))

    cell = {(c.day_of_week, c.hour): c.count for c in grid.cells}
    assert cell[(3, 0)] == 6
    assert cell[(2, 23)] == 1
