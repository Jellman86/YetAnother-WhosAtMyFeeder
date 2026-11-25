from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BeforeValidator


def utc_naive_now() -> datetime:
    """Return current UTC time without tzinfo for SQLite storage consistency."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive_from_timestamp(timestamp: float) -> datetime:
    """Convert a UNIX timestamp to naive UTC for storage consistency."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


def utc_naive_datetime(value: datetime) -> datetime:
    """Normalize a datetime to the repository's naive-UTC storage convention."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def serialize_storage_datetime(value: datetime) -> str:
    """Serialize a datetime for lexically sortable, timezone-stable SQLite storage."""
    return utc_naive_datetime(value).isoformat(sep=" ")


def serialize_api_datetime(value: datetime | None) -> str | None:
    """Serialize datetimes as explicit UTC ISO-8601 strings for API clients."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def parse_storage_datetime(value: object) -> datetime:
    """Parse datetime from SQLite storage format."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO format first, then common SQLite formats
        for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                if fmt is None:
                    return datetime.fromisoformat(value)
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    # Return current time as fallback (shouldn't happen with valid data)
    return utc_naive_now()


# A calendar date, `T`, hours and minutes, optional seconds and up to six fraction digits, then
# `Z` or a `±HH:MM` offset. A date alone, a clock with no offset or an epoch number is refused,
# because each would be read on some clock the caller never named. Every component is held to
# its range here, because Python reads an offset of `+01:60` as `+02:00` instead of refusing it.
_EXACT_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)


def _with_utc_time(value: datetime) -> datetime:
    """Refuse an instant at the edge of the calendar that has no UTC date, rather than fail later."""
    try:
        value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as error:
        raise ValueError("An exact time must fall between the years 1 and 9999 in UTC") from error
    return value


def parse_exact_instant(value: object) -> datetime:
    """Read an ISO 8601 date and time that states its offset, or refuse it."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("An exact time must state its offset, such as Z or +01:00")
        return _with_utc_time(value)
    if not isinstance(value, str) or not _EXACT_INSTANT.fullmatch(value):
        raise ValueError("An exact time must be an ISO 8601 date and time with an offset, such as 2026-11-24T10:15:30Z")
    return _with_utc_time(datetime.fromisoformat(value))


ExactInstant = Annotated[datetime, BeforeValidator(parse_exact_instant)]
