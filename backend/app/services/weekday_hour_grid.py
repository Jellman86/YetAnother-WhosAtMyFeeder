"""Folding UTC hour counts into the viewer's weekday-by-hour grid.

History is stored in UTC and grouped by UTC hour in SQL, because SQLite knows no time zones. Each
hour is then moved into the zone the viewer's browser named, so a grid reads in local time. A zone
whose offset is not a whole hour (India, UTC+5:30) puts each UTC hour in the local slot it starts
in. Pure, so the Leaderboard's camera grid and Audio history's call grid fold the same way and are
tested without a database or a clock.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Iterable


@dataclass(frozen=True)
class WeekdayHourCell:
    day_of_week: int  # 0=Sunday..6=Saturday
    hour: int  # 0..23
    count: int


@dataclass(frozen=True)
class WeekdayHourGrid:
    cells: list[WeekdayHourCell]
    total_count: int
    max_cell_count: int


def weekday_hour_grid(utc_hourly_counts: Iterable[tuple[datetime, int]], zone: tzinfo) -> WeekdayHourGrid:
    """Every weekday and hour, Sunday first, with the counts that fall in each in ``zone``.

    ``utc_hourly_counts`` holds naive UTC hour starts with the count in each.
    """
    counts: dict[tuple[int, int], int] = {}
    for bucket_start, count in utc_hourly_counts:
        if count <= 0:
            continue
        local = bucket_start.replace(tzinfo=timezone.utc).astimezone(zone)
        slot = ((local.weekday() + 1) % 7, local.hour)
        counts[slot] = counts.get(slot, 0) + int(count)

    cells = [
        WeekdayHourCell(day_of_week=day_of_week, hour=hour, count=counts.get((day_of_week, hour), 0))
        for day_of_week in range(7)
        for hour in range(24)
    ]
    return WeekdayHourGrid(
        cells=cells,
        total_count=sum(cell.count for cell in cells),
        max_cell_count=max((cell.count for cell in cells), default=0),
    )
