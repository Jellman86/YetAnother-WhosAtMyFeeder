import sys
import zoneinfo

import pytest
from starlette.requests import Request

from app.utils.timezone import get_user_timezone


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("", "UTC"),
        ("Not/A/Zone", "UTC"),
        (" Europe/London ", "Europe/London"),
        ("America/New_York", "America/New_York"),
    ],
)
def test_user_timezone_resolves_named_zones_and_defaults_on_invalid_headers(header, expected):
    request = Request({"type": "http", "headers": [(b"x-timezone", header.encode())]})
    assert get_user_timezone(request).key == expected


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
