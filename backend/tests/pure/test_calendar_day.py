from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.calendar_day import (
    TODAY,
    calendar_window,
    clamp_window,
    instance_timezone,
    local_date,
    resolve_calendar_day,
    today_so_far,
)

BERLIN = ZoneInfo("Europe/Berlin")  # UTC+1 in November
LONDON = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def test_instance_timezone_reads_tz_and_falls_back_to_utc() -> None:
    assert instance_timezone({"TZ": "Europe/London"}) == LONDON
    assert instance_timezone({"TZ": ":Europe/London"}) == LONDON
    assert instance_timezone({"TZ": "Not/AZone"}) == timezone.utc
    assert instance_timezone({"TZ": "../../etc/passwd"}) == timezone.utc
    assert instance_timezone({}) == timezone.utc


def test_today_is_the_local_calendar_day_not_the_utc_one() -> None:
    # 23:30 UTC is already 00:30 tomorrow in Berlin.
    late = datetime(2026, 11, 17, 23, 30, tzinfo=timezone.utc)
    assert resolve_calendar_day(TODAY, now=late, zone=BERLIN) == date(2026, 11, 18)
    assert resolve_calendar_day(TODAY, now=late, zone=timezone.utc) == date(2026, 11, 17)
    assert resolve_calendar_day(TODAY, now=datetime(2026, 11, 17, 22, 59, tzinfo=timezone.utc), zone=BERLIN) == date(
        2026, 11, 17
    )


def test_a_plain_date_is_kept_as_given() -> None:
    assert resolve_calendar_day(date(2026, 1, 2), now=NOW, zone=BERLIN) == date(2026, 1, 2)


def test_resolving_requires_an_aware_now() -> None:
    with pytest.raises(ValueError):
        resolve_calendar_day(TODAY, now=datetime(2026, 11, 17, 12, 0), zone=BERLIN)


def test_a_day_window_runs_from_local_midnight_to_the_last_instant_before_the_next() -> None:
    start, end = calendar_window(TODAY, TODAY, now=NOW, zone=BERLIN)
    assert start == datetime(2026, 11, 16, 23, 0)
    assert end == datetime(2026, 11, 17, 22, 59, 59, 999999)
    assert start.tzinfo is None and end.tzinfo is None


def test_a_capture_at_half_past_eleven_local_is_not_counted_in_the_next_day() -> None:
    start, end = calendar_window(date(2026, 11, 17), date(2026, 11, 17), now=NOW, zone=BERLIN)
    yesterday_late_local = datetime(2026, 11, 16, 22, 30)  # 23:30 Berlin on the 16th, stored as UTC
    today_early_local = datetime(2026, 11, 16, 23, 30)  # 00:30 Berlin on the 17th, still the 16th in UTC
    assert not start <= yesterday_late_local <= end
    assert start <= today_early_local <= end


def test_utc_days_keep_the_previous_whole_day_bounds() -> None:
    start, end = calendar_window(date(2026, 11, 17), date(2026, 11, 18), now=NOW, zone=timezone.utc)
    assert start == datetime(2026, 11, 17, 0, 0)
    assert end == datetime(2026, 11, 18, 23, 59, 59, 999999)


def test_a_daylight_saving_day_is_twenty_three_hours_long() -> None:
    start, end = calendar_window(date(2026, 3, 29), date(2026, 3, 29), now=NOW, zone=LONDON)
    assert start == datetime(2026, 3, 29, 0, 0)
    assert end == datetime(2026, 3, 29, 22, 59, 59, 999999)


def test_open_ended_windows_keep_their_open_side() -> None:
    assert calendar_window(None, None, now=NOW, zone=BERLIN) == (None, None)
    start, end = calendar_window(TODAY, None, now=NOW, zone=BERLIN)
    assert start == datetime(2026, 11, 16, 23, 0) and end is None
    start, end = calendar_window(None, TODAY, now=NOW, zone=BERLIN)
    assert start is None and end == datetime(2026, 11, 17, 22, 59, 59, 999999)


def test_today_so_far_runs_from_local_midnight_to_now() -> None:
    start, end = today_so_far(now=NOW, zone=BERLIN)
    assert start == datetime(2026, 11, 16, 23, 0)
    assert end == datetime(2026, 11, 17, 12, 0)


def test_clamping_never_widens_the_requested_window() -> None:
    requested = (datetime(2026, 11, 16, 23, 0), datetime(2026, 11, 17, 22, 59, 59, 999999))
    # A guest who may only see from UTC midnight keeps the later floor.
    floor = datetime(2026, 11, 17, 0, 0)
    assert clamp_window(*requested, floor=floor, ceiling=None) == (floor, requested[1])
    # A wider allowance changes nothing.
    assert clamp_window(*requested, floor=floor - timedelta(days=30), ceiling=None) == requested
    # An open request takes the allowance on both sides.
    ceiling = datetime(2026, 11, 17, 23, 59, 59, 999999)
    assert clamp_window(None, None, floor=floor, ceiling=ceiling) == (floor, ceiling)
    assert clamp_window(*requested, floor=None, ceiling=ceiling) == requested


def test_local_date_reads_a_stored_instant_on_the_instance_clock() -> None:
    assert local_date(datetime(2026, 11, 16, 23, 30), zone=BERLIN) == date(2026, 11, 17)
    assert local_date(datetime(2026, 11, 16, 23, 30), zone=timezone.utc) == date(2026, 11, 16)
    assert local_date(None, zone=BERLIN) is None
