import sys
import zoneinfo
from datetime import datetime

import pytest
from starlette.requests import Request

from app.utils.timezone import calendar_timezone


@pytest.mark.parametrize(
    ("header", "instance_zone", "expected"),
    [
        ("", "", "UTC"),
        ("Not/A/Zone", "", "UTC"),
        (" Europe/London ", "", "Europe/London"),
        ("America/New_York", "Europe/London", "America/New_York"),
        ("", "Europe/London", "Europe/London"),
        ("Not/A/Zone", "Asia/Tokyo", "Asia/Tokyo"),
    ],
)
def test_calendar_timezone_prefers_the_header_then_the_instance_zone_then_utc(
    monkeypatch, header, instance_zone, expected
):
    monkeypatch.setenv("TZ", instance_zone)
    request = Request({"type": "http", "headers": [(b"x-timezone", header.encode())]})
    zone = calendar_timezone(request)
    assert datetime(2026, 1, 15, 12, tzinfo=zone).utcoffset() == datetime(
        2026, 1, 15, 12, tzinfo=zoneinfo.ZoneInfo(expected)
    ).utcoffset()
    assert getattr(zone, "key", "UTC") == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows uses packaged timezone data")
def test_windows_timezone_resolution_does_not_require_a_system_database():
    original = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(())
    zoneinfo.ZoneInfo.clear_cache()
    try:
        assert zoneinfo.ZoneInfo("UTC").key == "UTC"
        assert zoneinfo.ZoneInfo("Europe/London").key == "Europe/London"
    finally:
        zoneinfo.reset_tzpath(original)
        zoneinfo.ZoneInfo.clear_cache()
