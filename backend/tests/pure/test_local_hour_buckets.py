"""Hour buckets that start where the viewer's local hours start, for zones off the whole hour."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.local_hour_buckets import (
    hour_alignment,
    hour_alignment_segments,
    local_hour_start,
    local_hour_starts,
    utc_hour_bucket_sql,
)

KOLKATA = ZoneInfo("Asia/Kolkata")
KATHMANDU = ZoneInfo("Asia/Kathmandu")
ST_JOHNS = ZoneInfo("America/St_Johns")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")
BERLIN = ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("zone", "alignment"),
    [(timezone.utc, 0), (BERLIN, 0), (KOLKATA, 30), (KATHMANDU, 15), (ST_JOHNS, 30)],
)
def test_each_local_hour_starts_its_offsets_minutes_past_the_utc_hour(zone, alignment):
    assert hour_alignment(datetime(2026, 11, 25, 12), zone) == alignment


def test_a_zone_off_the_whole_hour_all_year_is_one_piece():
    start, end = datetime(2026, 1, 1), datetime(2026, 12, 31)

    assert hour_alignment_segments(start, end, KOLKATA) == [(start, end, 30)]
    assert hour_alignment_segments(start, end, BERLIN) == [(start, end, 0)]


def test_a_half_hour_clock_change_splits_the_window_at_the_change():
    # Lord Howe Island goes from UTC+10:30 to UTC+11 at 02:00 local on 4 October 2026 (15:30 UTC).
    start, end = datetime(2026, 10, 1), datetime(2026, 10, 8)

    segments = hour_alignment_segments(start, end, LORD_HOWE)

    assert segments == [(start, datetime(2026, 10, 3, 15, 30), 30), (datetime(2026, 10, 3, 15, 30), end, 0)]


def test_the_bucket_sql_refuses_an_alignment_no_zone_has():
    with pytest.raises(ValueError):
        utc_hour_bucket_sql("detection_time", 20)


@pytest.mark.parametrize(
    ("instant", "zone", "start"),
    [
        (datetime(2026, 11, 25, 18, 40), KOLKATA, datetime(2026, 11, 25, 18, 30)),
        (datetime(2026, 11, 25, 18, 40), BERLIN, datetime(2026, 11, 25, 18, 0)),
        # Berlin's clocks went forward at 01:00 UTC on 29 March 2026: 03:10 local began at 01:00 UTC.
        (datetime(2026, 3, 29, 1, 10), BERLIN, datetime(2026, 3, 29, 1, 0)),
        # Lord Howe: 15:30 UTC on 3 October 2026 jumps 02:00 to 02:30, so 02:40 is in a half hour.
        (datetime(2026, 10, 3, 15, 40), LORD_HOWE, datetime(2026, 10, 3, 15, 30)),
        (datetime(2026, 10, 3, 15, 20), LORD_HOWE, datetime(2026, 10, 3, 14, 30)),
        (datetime(2026, 10, 3, 16, 5), LORD_HOWE, datetime(2026, 10, 3, 16, 0)),
        # Lord Howe: 15:00 UTC on 4 April 2026 goes back from 02:00 to 01:30, so 01:30 happens twice.
        (datetime(2026, 4, 4, 14, 50), LORD_HOWE, datetime(2026, 4, 4, 14, 0)),
        (datetime(2026, 4, 4, 15, 10), LORD_HOWE, datetime(2026, 4, 4, 15, 0)),
        (datetime(2026, 4, 4, 15, 40), LORD_HOWE, datetime(2026, 4, 4, 15, 30)),
    ],
)
def test_a_local_hour_starts_on_the_hour_or_at_the_clock_change_inside_it(instant, zone, start):
    assert local_hour_start(instant, zone) == start


def test_every_local_hour_of_a_window_is_touched_even_a_half_hour_one():
    # A rolling window whose hourly steps would jump from 01:50 to 03:20 across the change.
    start, end = datetime(2026, 10, 3, 14, 20), datetime(2026, 10, 3, 18, 20)

    hours = {local_hour_start(instant, LORD_HOWE) for instant in local_hour_starts(start, end, LORD_HOWE)}

    assert sorted(hours) == [
        datetime(2026, 10, 3, 13, 30),
        datetime(2026, 10, 3, 14, 30),
        datetime(2026, 10, 3, 15, 30),
        datetime(2026, 10, 3, 16, 0),
        datetime(2026, 10, 3, 17, 0),
        datetime(2026, 10, 3, 18, 0),
    ]
