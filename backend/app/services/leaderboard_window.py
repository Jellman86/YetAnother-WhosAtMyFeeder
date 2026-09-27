"""Rules for comparing one leaderboard window with the one before it."""

from datetime import datetime, timezone


def previous_window_is_complete(*, history_start: datetime | None, prev_start: datetime) -> bool:
    """Whether the detection history covers the whole of the previous window.

    A window that began before the first detection was recorded is not a quiet
    period; it is one nobody was watching. Comparing against it turns every
    species into a riser (an install three weeks old showed "+475" for its most
    common bird), so a trend is only claimed when this holds.
    """
    if history_start is None:
        return False
    return _as_naive_utc(history_start) <= _as_naive_utc(prev_start)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
