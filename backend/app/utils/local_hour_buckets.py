"""UTC hour buckets that begin where the viewer's local hours begin.

SQLite knows no time zones, so history is grouped in SQL and moved into the viewer's zone after.
A zone whose offset is not a whole hour (India, UTC+5:30; Nepal, UTC+5:45) starts each local hour
part way through a UTC hour, so a bucket cut at the top of the UTC hour would put 00:10 local time
in the hour before midnight. Each bucket here starts that many minutes past the UTC hour instead.
Offsets are whole quarter hours, so every local hour is exactly one bucket.
"""

from datetime import datetime, timedelta, timezone, tzinfo

_ALIGNMENTS = frozenset({0, 15, 30, 45})
_STEP = timedelta(days=1)


def hour_alignment(instant: datetime, zone: tzinfo) -> int:
    """Minutes past the UTC hour at which the local hour holding the naive-UTC ``instant`` begins."""
    offset = instant.replace(tzinfo=timezone.utc).astimezone(zone).utcoffset() or timedelta(0)
    fraction = int(offset.total_seconds() // 60) % 60
    return (60 - fraction) % 60


def hour_alignment_segments(start: datetime, end: datetime, zone: tzinfo) -> list[tuple[datetime, datetime, int]]:
    """``[start, end)`` split where the zone's hour alignment changes, each piece with its alignment.

    Almost every zone keeps one alignment all year, so this is one piece; Lord Howe Island moves its
    clocks by half an hour and so has two.
    """
    if end <= start:
        return [(start, end, hour_alignment(start, zone))]
    segments: list[tuple[datetime, datetime, int]] = []
    piece_start, alignment = start, hour_alignment(start, zone)
    cursor = start
    while cursor < end:
        step_end = min(cursor + _STEP, end)
        if hour_alignment(step_end, zone) != alignment:
            change = _first_change(cursor, step_end, zone, alignment)
            segments.append((piece_start, change, alignment))
            piece_start, alignment = change, hour_alignment(change, zone)
            cursor = change
            continue
        cursor = step_end
    segments.append((piece_start, end, alignment))
    return segments


def _first_change(low: datetime, high: datetime, zone: tzinfo, alignment: int) -> datetime:
    # ``low`` has the old alignment and ``high`` the new; a clock change is on a whole minute.
    while high - low > timedelta(minutes=1):
        middle = low + (high - low) / 2
        if hour_alignment(middle, zone) == alignment:
            low = middle
        else:
            high = middle
    whole_minute = high.replace(second=0, microsecond=0)
    return whole_minute if whole_minute > low else high


def utc_hour_bucket_sql(column: str, alignment: int) -> str:
    """SQL for the ISO-8601 UTC start (``…Z``) of the aligned hour bucket holding ``column``."""
    if alignment not in _ALIGNMENTS:
        raise ValueError(f"Hour alignment must be one of {sorted(_ALIGNMENTS)}, not {alignment}")
    return (
        f"strftime('%Y-%m-%dT%H:%M:00Z', strftime('%Y-%m-%d %H:00:00', {column}, '-{alignment} minutes'), "
        f"'+{alignment} minutes')"
    )
