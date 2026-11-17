from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.daily_history import (
    DayCoverage,
    coverage,
    first_whole_day,
    local_midnight_utc,
    local_noon_utc,
    sealed_ranges,
    subtract_counts,
)

BERLIN = ZoneInfo("Europe/Berlin")
KOLKATA = ZoneInfo("Asia/Kolkata")


def test_sealed_days_become_exact_utc_ranges_merged_where_they_touch() -> None:
    assert sealed_ranges({date(2036, 2, 10), date(2036, 2, 11), date(2036, 2, 13)}, BERLIN) == [
        (datetime(2036, 2, 9, 23, 0), datetime(2036, 2, 11, 23, 0)),
        (datetime(2036, 2, 12, 23, 0), datetime(2036, 2, 13, 23, 0)),
    ]
    # A half-hour zone's day starts on the half hour, not on an hour boundary.
    assert sealed_ranges({date(2036, 2, 11)}, KOLKATA) == [
        (datetime(2036, 2, 10, 18, 30), datetime(2036, 2, 11, 18, 30))
    ]
    assert sealed_ranges(set(), BERLIN) == []


def test_counts_inside_sealed_ranges_are_taken_out_exactly() -> None:
    every = {"2036-02-10T18:00:00Z": 3, "2036-02-10T19:00:00Z": 1}
    sealed = {"2036-02-10T18:00:00Z": 2, "2036-02-10T19:00:00Z": 1}
    assert subtract_counts(every, sealed) == {"2036-02-10T18:00:00Z": 1}
    assert subtract_counts(every, {}) == every


def test_a_guest_window_starts_at_the_first_local_day_wholly_inside_it() -> None:
    # Berlin's 10 Feb began at 23:00 UTC on the 9th, before a window opening at UTC midnight.
    assert first_whole_day(datetime(2036, 2, 10, 0, 0), BERLIN) == date(2036, 2, 11)
    assert first_whole_day(datetime(2036, 2, 9, 23, 0), BERLIN) == date(2036, 2, 10)


def test_coverage_names_the_last_day_read_from_totals() -> None:
    sealed = {date(2036, 2, 9): True, date(2036, 2, 10): True}
    assert coverage(sealed) == DayCoverage(totals_through=date(2036, 2, 10), complete_from=None, partial=False)


def test_coverage_says_from_when_the_totals_are_complete() -> None:
    sealed = {date(2036, 2, 8): False, date(2036, 2, 9): False, date(2036, 2, 10): True}
    assert coverage(sealed) == DayCoverage(
        totals_through=date(2036, 2, 10), complete_from=date(2036, 2, 10), partial=True
    )
    assert coverage({date(2036, 2, 8): False}) == DayCoverage(
        totals_through=date(2036, 2, 8), complete_from=None, partial=True
    )
    assert coverage({}) == DayCoverage(totals_through=None, complete_from=None, partial=False)


def test_a_day_total_is_placed_at_local_noon() -> None:
    assert local_noon_utc(date(2036, 2, 10), BERLIN) == datetime(2036, 2, 10, 11, 0)


def test_a_day_starts_at_local_midnight() -> None:
    assert local_midnight_utc(date(2036, 2, 10), BERLIN) == datetime(2036, 2, 9, 23, 0)
