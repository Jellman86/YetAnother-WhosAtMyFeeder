"""The windows a leaderboard span counts over, and when one is fairly compared with the one before."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Literal

from app.services.daily_history import local_midnight_utc
from app.utils.calendar_day import clamp_window, today_so_far

BoundedSpan = Literal["today", "day", "week", "month"]
# Why a window cannot be fairly compared with the one before it, whatever the history holds.
WindowMismatch = Literal["clock_change", "shared_window", "cleanup"]

LEADERBOARD_SPAN_DESCRIPTION = (
    "`today`: local midnight to now, in the zone `X-Timezone` names, else the instance's `TZ`, else UTC. "
    "`day`: the last 24 hours. `week`: the last 7 days. `month`: the last 30 days."
)

_ROLLING: dict[str, timedelta] = {
    "day": timedelta(hours=24),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


@dataclass(frozen=True)
class LeaderboardWindows:
    """Naive-UTC bounds of a span's window and of the window its trend is measured against."""

    start: datetime
    end: datetime
    prev_start: datetime
    prev_end: datetime
    # Why the two windows do not cover the same stretch of the clock: a clock change between
    # yesterday and today, or a guest's allowance cutting either short. None when they do.
    mismatch: WindowMismatch | None
    # Whether a guest's allowance moved this window's start later than the span asks for.
    shortened: bool

    @property
    def comparable(self) -> bool:
        return self.mismatch is None


def leaderboard_windows(
    span: BoundedSpan,
    *,
    now: datetime,
    zone: tzinfo,
    floor: datetime | None = None,
    ceiling: datetime | None = None,
) -> LeaderboardWindows:
    """The windows for ``span`` at ``now``, intersected with a guest's ``floor`` and ``ceiling``.

    ``today`` runs from local midnight in ``zone`` to now and is compared with yesterday up to the
    same local time; the rolling spans end now and are compared with the same length before them.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Leaderboard windows are resolved from an aware instant")
    clocks_agree = True
    if span == "today":
        start, end = today_so_far(now=now, zone=zone)
        local_now = now.astimezone(zone)
        yesterday = local_now.date() - timedelta(days=1)
        today_midnight = datetime.combine(local_now.date(), time.min)
        yesterday_midnight = datetime.combine(yesterday, time.min)
        # The same time yesterday: at 02:30 the day after the clocks went forward it never existed,
        # and in the hour after they went back it happened twice, so neither is a fair comparison.
        same_time_yesterday = datetime.combine(yesterday, local_now.time().replace(fold=0))
        prev_start = _local_utc(yesterday_midnight, zone)
        prev_end = _local_utc(same_time_yesterday, zone)
        clocks_agree = all(
            _happens_once(wall, zone) for wall in (today_midnight, yesterday_midnight, same_time_yesterday)
        )
    else:
        end = now.astimezone(timezone.utc).replace(tzinfo=None)
        start = end - _ROLLING[span]
        prev_start, prev_end = start - _ROLLING[span], start

    clocks_agree = clocks_agree and (end - start) == (prev_end - prev_start)
    clamped_start, clamped_end = clamp_window(start, end, floor=floor, ceiling=ceiling)
    clamped_prev_start, clamped_prev_end = clamp_window(prev_start, prev_end, floor=floor, ceiling=ceiling)
    assert clamped_start is not None and clamped_end is not None
    assert clamped_prev_start is not None and clamped_prev_end is not None
    cut = (clamped_start, clamped_end, clamped_prev_start, clamped_prev_end) != (start, end, prev_start, prev_end)
    mismatch: WindowMismatch | None = None
    if not clocks_agree:
        mismatch = "clock_change"
    elif cut:
        mismatch = "shared_window"
    return LeaderboardWindows(
        start=clamped_start,
        end=clamped_end,
        prev_start=clamped_prev_start,
        prev_end=clamped_prev_end,
        mismatch=mismatch,
        shortened=clamped_start > start,
    )


def _local_utc(local: datetime, zone: tzinfo) -> datetime:
    # fold=0 takes the first of a repeated time and the instant after a skipped one, as midnight does.
    return local.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def _happens_once(wall: datetime, zone: tzinfo) -> bool:
    """Whether a naive local wall time names exactly one instant: not skipped, not repeated."""
    first, second = wall.replace(tzinfo=zone, fold=0), wall.replace(tzinfo=zone, fold=1)
    return first.utcoffset() == second.utcoffset()


def sealed_history_cuts(
    start: datetime,
    end: datetime,
    sealed_days: Collection[date],
    zone: tzinfo,
    *,
    totals_count: bool,
) -> bool:
    """Whether a sealed day overlaps ``[start, end)`` without its daily total standing in for it.

    Cleanup keeps a sealed day's total and may delete its captures, so a window that takes part of
    a sealed day, or a whole one when ``totals_count`` is false, counts only what survived.
    """
    for day in sealed_days:
        day_start, day_end = local_midnight_utc(day, zone), local_midnight_utc(day + timedelta(days=1), zone)
        if day_end <= start or day_start >= end:
            continue
        if not (totals_count and start <= day_start and day_end <= end):
            return True
    return False


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
