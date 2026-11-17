from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.daily_history import DayCoverage, coverage, local_midnight_utc, local_noon_utc, split_by_seal

BERLIN = ZoneInfo("Europe/Berlin")


def test_stored_hours_on_sealed_days_are_set_aside_so_no_capture_counts_twice() -> None:
    hours = [
        (datetime(2036, 2, 10, 8), 3),  # the 10th in Berlin
        (datetime(2036, 2, 10, 23), 1),  # 00:00 on the 11th in Berlin
        (datetime(2036, 2, 12, 9), 2),
    ]
    live, sealed_count = split_by_seal(hours, {date(2036, 2, 10), date(2036, 2, 11)}, zone=BERLIN)
    assert live == [(datetime(2036, 2, 12, 9), 2)]
    assert sealed_count == 4


def test_nothing_is_set_aside_without_sealed_days() -> None:
    hours = [(datetime(2036, 2, 10, 8), 3)]
    assert split_by_seal(hours, set(), zone=timezone.utc) == (hours, 0)


def test_coverage_names_the_last_day_read_from_totals() -> None:
    sealed = {date(2036, 2, 9): True, date(2036, 2, 10): True}
    assert coverage(sealed) == DayCoverage(totals_through=date(2036, 2, 10), complete_from=None, partial=False)


def test_coverage_says_from_when_the_totals_are_complete() -> None:
    sealed = {date(2036, 2, 8): False, date(2036, 2, 9): False, date(2036, 2, 10): True}
    assert coverage(sealed) == DayCoverage(
        totals_through=date(2036, 2, 10), complete_from=date(2036, 2, 10), partial=True
    )
    # Only incomplete days: nothing is complete yet, so there is no date to name.
    assert coverage({date(2036, 2, 8): False}) == DayCoverage(
        totals_through=date(2036, 2, 8), complete_from=None, partial=True
    )
    assert coverage({}) == DayCoverage(totals_through=None, complete_from=None, partial=False)


def test_a_day_total_is_placed_at_local_noon() -> None:
    assert local_noon_utc(date(2036, 2, 10), BERLIN) == datetime(2036, 2, 10, 11, 0)


def test_a_day_starts_at_local_midnight() -> None:
    assert local_midnight_utc(date(2036, 2, 10), BERLIN) == datetime(2036, 2, 9, 23, 0)
