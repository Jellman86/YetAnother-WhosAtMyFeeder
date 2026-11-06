from __future__ import annotations

from datetime import datetime, timezone


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
