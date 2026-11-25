"""The calendar day the API means by a date or by ``today``.

Detections are stored as naive UTC, but an owner asking for "today" or for a date
means a day on their own clock: the viewer's zone when the request names one, else the
instance's (``TZ``). Every bound is handed back as naive UTC so the repositories compare
like with like.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Final, Literal
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()

TODAY: Final = "today"
CalendarDay = date | Literal["today"]

_LAST_INSTANT = timedelta(microseconds=1)


# An IANA name: letters first, then letters, digits, `_`, `+`, `-`, in `/`-separated parts.
# Anything else, a path above all, never reaches ZoneInfo.
_ZONE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+)*")
_MAX_ZONE_NAME = 64
_warned: set[str] = set()


def zone_named(name: str | None) -> tzinfo | None:
    """The IANA zone ``name`` names, or None when it is not one."""
    name = (name or "").strip()
    if not name or len(name) > _MAX_ZONE_NAME or not _ZONE_NAME.fullmatch(name):
        return None
    try:
        return ZoneInfo(name)
    except (ValueError, OSError, KeyError):
        return None


def _warn_once(source: str, **context: object) -> None:
    # A request header is client-controlled: one warning per source, never one per request.
    if source in _warned:
        return
    _warned.add(source)
    log.warning("timezone_unresolved", source=source, **context)


def instance_timezone(environ: Mapping[str, str] | None = None) -> tzinfo:
    """The instance's zone: ``TZ``, or UTC when unset or unknown (the container's own default)."""
    name = (os.environ if environ is None else environ).get("TZ", "").strip().lstrip(":")
    if not name:
        return timezone.utc
    zone = zone_named(name)
    if zone is None:
        _warn_once("TZ", zone=name[:_MAX_ZONE_NAME], fallback="UTC")
        return timezone.utc
    return zone


def resolve_zone(header: str | None, environ: Mapping[str, str] | None = None) -> tzinfo:
    """The zone a calendar day is read in: the viewer's ``X-Timezone``, else ``TZ``, else UTC.

    The SPA sends the browser's zone, so its dates are the viewer's days; a client that sends
    none (curl, Home Assistant) gets the instance's day.
    """
    if header and header.strip():
        zone = zone_named(header)
        if zone is not None:
            return zone
        _warn_once("X-Timezone", fallback="TZ")
    return instance_timezone(environ)


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Calendar days are resolved from an aware instant")


def resolve_calendar_day(day: CalendarDay, *, now: datetime, zone: tzinfo) -> date:
    _require_aware(now)
    if day == TODAY:
        return now.astimezone(zone).date()
    return day


def _local_midnight_utc(day: date, zone: tzinfo) -> datetime:
    # fold=0 takes the first midnight on a repeated hour, and the first real instant after a skipped one.
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def calendar_window(
    start_day: CalendarDay | None,
    end_day: CalendarDay | None,
    *,
    now: datetime,
    zone: tzinfo,
) -> tuple[datetime | None, datetime | None]:
    """Inclusive naive-UTC bounds from local midnight of ``start_day`` to the last instant of ``end_day``."""
    start = (
        _local_midnight_utc(resolve_calendar_day(start_day, now=now, zone=zone), zone)
        if start_day is not None
        else None
    )
    end = (
        _local_midnight_utc(resolve_calendar_day(end_day, now=now, zone=zone) + timedelta(days=1), zone) - _LAST_INSTANT
        if end_day is not None
        else None
    )
    return start, end


def today_so_far(*, now: datetime, zone: tzinfo) -> tuple[datetime, datetime]:
    """Naive-UTC bounds from local midnight to ``now``."""
    start, _ = calendar_window(TODAY, None, now=now, zone=zone)
    assert start is not None
    return start, now.astimezone(timezone.utc).replace(tzinfo=None)


def yesterday_until_now(*, now: datetime, zone: tzinfo) -> tuple[datetime, datetime]:
    """Naive-UTC bounds of yesterday from its local midnight for as long as today has run so far.

    The fair comparison for "today so far": the same stretch of the day before, never past today's
    midnight on a day a clock change made short.
    """
    today_start, today_end = today_so_far(now=now, zone=zone)
    yesterday = resolve_calendar_day(TODAY, now=now, zone=zone) - timedelta(days=1)
    start = _local_midnight_utc(yesterday, zone)
    return start, min(start + (today_end - today_start), today_start)


def clamp_window(
    start: datetime | None,
    end: datetime | None,
    *,
    floor: datetime | None,
    ceiling: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Intersect a requested window with an allowance, so a request can only narrow what is visible."""
    if floor is not None:
        start = floor if start is None else max(start, floor)
    if ceiling is not None:
        end = ceiling if end is None else min(end, ceiling)
    return start, end


def local_date(value: datetime | None, *, zone: tzinfo) -> date | None:
    """The local calendar date of a naive-UTC instant."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(zone).date()
