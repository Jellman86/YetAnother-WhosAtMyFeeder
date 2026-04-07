"""Timezone detection utility for extracting user timezone from HTTP headers."""

import zoneinfo

from fastapi import Request


def get_user_timezone(request: Request) -> zoneinfo.ZoneInfo:
    """
    Extract user timezone from X-Timezone header.

    Returns a ZoneInfo object for the requested timezone.
    Falls back to UTC if the header is missing or contains an unknown zone.

    Args:
        request: FastAPI Request object

    Returns:
        zoneinfo.ZoneInfo: Timezone for the user's browser
    """
    tz_name = request.headers.get("X-Timezone", "").strip()
    if tz_name:
        try:
            return zoneinfo.ZoneInfo(tz_name)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            pass
    return zoneinfo.ZoneInfo("UTC")
