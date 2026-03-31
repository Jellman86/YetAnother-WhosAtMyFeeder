from __future__ import annotations

from datetime import datetime, timezone


def utc_naive_now() -> datetime:
    """Return current UTC time without tzinfo for SQLite storage consistency."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive_from_timestamp(timestamp: float) -> datetime:
    """Convert a UNIX timestamp to naive UTC for storage consistency."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


def serialize_api_datetime(value: datetime | None) -> str | None:
    """Serialize datetimes as explicit UTC ISO-8601 strings for API clients."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
