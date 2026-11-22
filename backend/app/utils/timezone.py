"""The zone a request's calendar days and hours are read in."""

from datetime import tzinfo

from fastapi import Request

from app.utils.calendar_day import resolve_zone


def calendar_timezone(request: Request) -> tzinfo:
    """A valid ``X-Timezone``, else ``TZ``, else UTC.

    Every day, hour bucket and weekday grid uses this one rule, so a client that sends no header
    (curl, Home Assistant) gets hours that agree with the day it was given.
    """
    return resolve_zone(request.headers.get("X-Timezone"))
