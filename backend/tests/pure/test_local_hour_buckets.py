"""Hour buckets that start where the viewer's local hours start, for zones off the whole hour."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.local_hour_buckets import hour_alignment, hour_alignment_segments, utc_hour_bucket_sql

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
