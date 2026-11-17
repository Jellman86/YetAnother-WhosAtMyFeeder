"""Timezone detection utility for extracting user timezone from HTTP headers."""

import zoneinfo
from datetime import tzinfo

from fastapi import Request

from app.utils.calendar_day import resolve_zone


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


def calendar_timezone(request: Request) -> tzinfo:
    """The zone a requested calendar day is read in: a valid ``X-Timezone``, else ``TZ``, else UTC."""
    return resolve_zone(request.headers.get("X-Timezone"))
