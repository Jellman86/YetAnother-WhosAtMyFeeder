"""The windows a leaderboard span counts over, and when its trend is a fair comparison."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.leaderboard_window import leaderboard_windows

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def naive(*parts: int) -> datetime:
    return datetime(*parts)


@pytest.mark.parametrize(
    ("span", "length"),
    [("day", timedelta(hours=24)), ("week", timedelta(days=7)), ("month", timedelta(days=30))],
)
def test_rolling_spans_end_now_and_compare_with_the_window_before(span: str, length: timedelta):
    now = utc(2026, 11, 25, 15, 30)
    windows = leaderboard_windows(span, now=now, zone=NEW_YORK)

    assert windows.end == naive(2026, 11, 25, 15, 30)
    assert windows.start == windows.end - length
    assert windows.prev_end == windows.start
    assert windows.prev_start == windows.start - length
    assert windows.comparable is True
    assert windows.shortened is False


def test_today_runs_from_local_midnight_to_now_in_the_given_zone():
    now = utc(2026, 11, 25, 15, 30)  # 10:30 in New York

    windows = leaderboard_windows("today", now=now, zone=NEW_YORK)

    assert windows.start == naive(2026, 11, 25, 5, 0)  # New York midnight in UTC
    assert windows.end == naive(2026, 11, 25, 15, 30)


def test_today_is_a_different_window_in_a_zone_already_on_tomorrow():
    now = utc(2026, 11, 25, 15, 30)  # 00:30 on 26 November in Tokyo

    windows = leaderboard_windows("today", now=now, zone=TOKYO)

    assert windows.start == naive(2026, 11, 25, 15, 0)
    assert windows.end == naive(2026, 11, 25, 15, 30)


def test_today_compares_with_yesterday_up_to_the_same_time_of_day():
    now = utc(2026, 11, 25, 15, 30)  # 10:30 in New York

    windows = leaderboard_windows("today", now=now, zone=NEW_YORK)

    assert windows.prev_start == naive(2026, 11, 24, 5, 0)
    assert windows.prev_end == naive(2026, 11, 24, 15, 30)
    assert windows.comparable is True


def test_today_withholds_the_trend_on_the_morning_the_clocks_go_forward():
    # London went to summer time at 01:00 UTC on 29 March 2026: the day so far is an hour short.
    now = utc(2026, 3, 29, 9, 0)  # 10:00 BST

    windows = leaderboard_windows("today", now=now, zone=LONDON)

    assert windows.start == naive(2026, 3, 29, 0, 0)
    assert windows.end - windows.start == timedelta(hours=9)
    assert windows.prev_end - windows.prev_start == timedelta(hours=10)
    assert windows.comparable is False


def test_today_withholds_the_trend_the_day_after_the_clocks_go_back():
    # London left summer time at 01:00 UTC on 25 October 2026; yesterday so far ran an hour long.
    now = utc(2026, 10, 26, 10, 0)  # 10:00 GMT on 26 October

    windows = leaderboard_windows("today", now=now, zone=LONDON)

    assert windows.end - windows.start == timedelta(hours=10)
    assert windows.prev_end - windows.prev_start == timedelta(hours=11)
    assert windows.comparable is False


def test_today_still_compares_on_an_ordinary_day_in_utc():
    windows = leaderboard_windows("today", now=utc(2026, 11, 25, 0, 0, 30), zone=timezone.utc)

    assert windows.start == naive(2026, 11, 25)
    assert windows.prev_start == naive(2026, 11, 24)
    assert windows.prev_end == naive(2026, 11, 24, 0, 0, 30)
    assert windows.comparable is True


def test_a_guest_floor_inside_today_shortens_it_and_withholds_the_trend():
    # Public today-only mode shares the UTC day; a New York evening began before it.
    now = utc(2026, 11, 26, 2, 0)  # 21:00 on 25 November in New York
    floor, ceiling = naive(2026, 11, 26), naive(2026, 11, 27)

    windows = leaderboard_windows("today", now=now, zone=NEW_YORK, floor=floor, ceiling=ceiling)

    assert windows.start == floor
    assert windows.end == naive(2026, 11, 26, 2, 0)
    assert windows.shortened is True
    assert windows.comparable is False
    assert windows.prev_start >= floor


def test_a_guest_floor_before_both_windows_changes_nothing():
    now = utc(2026, 11, 25, 15, 30)

    windows = leaderboard_windows("today", now=now, zone=NEW_YORK, floor=naive(2026, 11, 18))

    assert windows.start == naive(2026, 11, 25, 5, 0)
    assert windows.prev_start == naive(2026, 11, 24, 5, 0)
    assert windows.shortened is False
    assert windows.comparable is True


def test_a_guest_floor_inside_the_previous_window_withholds_a_rolling_trend():
    now = utc(2026, 11, 25, 15, 30)

    windows = leaderboard_windows("week", now=now, zone=timezone.utc, floor=naive(2026, 11, 15))

    assert windows.start == naive(2026, 11, 18, 15, 30)
    assert windows.prev_start == naive(2026, 11, 15)
    assert windows.shortened is False
    assert windows.comparable is False


def test_a_guest_ceiling_never_lets_a_window_end_past_it():
    now = utc(2026, 11, 25, 15, 30)

    windows = leaderboard_windows("day", now=now, zone=timezone.utc, ceiling=naive(2026, 11, 25, 12))

    assert windows.end == naive(2026, 11, 25, 12)
    assert windows.prev_end <= windows.end


def test_windows_need_an_aware_instant():
    with pytest.raises(ValueError):
        leaderboard_windows("today", now=datetime(2026, 11, 25, 12), zone=timezone.utc)
