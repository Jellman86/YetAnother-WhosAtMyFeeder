"""Per-day species totals that outlive the detection rows they were counted from (#949).

A day is either *live*, with every one of its rows still stored and read from them, or
*sealed*, with its captures and visits written here from those rows just before automatic
cleanup (or Frigate losing an event) removes any of them. Reads take sealed days from here
and live days from the rows, so the same capture is never counted twice and a sealed day
never changes again. That is the whole contract:

- Ingest never writes here. Re-processing an event cannot change a sealed day, and a live day
  is counted from rows whose ``frigate_event`` is unique.
- Retention cleanup seals and commits before it deletes, and does not delete if sealing fails,
  so it can never reduce history.
- Hiding, relabelling or deleting a capture is the owner correcting the record. On a live day it
  changes the counts, because they are read from the rows. On a sealed day it does not: the
  rows the correction would be checked against are gone, so the totals stay as counted.
- Deleting all history deletes these totals with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from collections.abc import Collection

import structlog

from app.repositories.detection_repository import DetectionRepository
from app.utils.api_datetime import utc_naive_datetime
from app.utils.calendar_day import calendar_window, local_date

log = structlog.get_logger()

# A visit that opens just before midnight is still running after it. Grouping from the day
# before means each visit is counted once, on the day it opened.
_VISIT_LOOKBACK = timedelta(days=1)
_LAST_INSTANT = timedelta(microseconds=1)


@dataclass(frozen=True)
class SpeciesDayTotal:
    day: date
    species_key: str
    species_id: int | None
    taxa_id: int | None
    scientific_name: str | None
    common_name: str | None
    display_name: str
    capture_count: int
    visit_count: int


@dataclass(frozen=True)
class SealedDay:
    day: date
    complete: bool


def _day_bounds(day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """Naive-UTC ``[start, end)`` of one instance-local day."""
    start, last = calendar_window(day, day, now=datetime.now(timezone.utc), zone=zone)
    assert start is not None and last is not None
    return start, last + _LAST_INSTANT


class DailyTotalsRepository(DetectionRepository):
    async def sealed_days(self, start: date | None = None, end: date | None = None) -> dict[date, SealedDay]:
        conditions, params = ["1 = 1"], []
        if start is not None:
            conditions.append("day >= ?")
            params.append(start.isoformat())
        if end is not None:
            conditions.append("day <= ?")
            params.append(end.isoformat())
        async with self.db.execute(
            f"SELECT day, complete FROM daily_totals_days WHERE {' AND '.join(conditions)}", params
        ) as cursor:
            rows = await cursor.fetchall()
        return {
            date.fromisoformat(str(day)): SealedDay(date.fromisoformat(str(day)), bool(complete))
            for day, complete in rows
        }

    async def first_sealed_day(self, start: date | None = None) -> date | None:
        async with self.db.execute(
            "SELECT MIN(day) FROM daily_totals_days WHERE day >= ?", ((start or date.min).isoformat(),)
        ) as cursor:
            row = await cursor.fetchone()
        return date.fromisoformat(str(row[0])) if row and row[0] else None

    async def totals(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        species_names: Collection[str] = (),
        taxa_id: int | None = None,
    ) -> list[SpeciesDayTotal]:
        """Sealed totals, optionally for one species named any of the ways a detection names it."""
        conditions, params = ["1 = 1"], []
        if start is not None:
            conditions.append("day >= ?")
            params.append(start.isoformat())
        if end is not None:
            conditions.append("day <= ?")
            params.append(end.isoformat())
        names = sorted({name.strip().casefold() for name in species_names if name and name.strip()})
        if names or taxa_id is not None:
            matches = []
            if names:
                placeholders = ",".join("?" for _ in names)
                matches.extend(
                    f"LOWER({column}) IN ({placeholders})"
                    for column in ("scientific_name", "common_name", "display_name")
                )
                params.extend(names * 3)
            if taxa_id is not None:
                matches.append("taxa_id = ?")
                params.append(taxa_id)
            conditions.append(f"({' OR '.join(matches)})")
        async with self.db.execute(
            f"""SELECT day, species_key, species_id, taxa_id, scientific_name, common_name, display_name,
                    capture_count, visit_count
                FROM species_daily_totals WHERE {" AND ".join(conditions)} ORDER BY day, species_key""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [SpeciesDayTotal(date.fromisoformat(str(row[0])), *row[1:]) for row in rows]

    async def seal_before(self, cutoff: datetime, *, zone: tzinfo, now: datetime) -> int:
        """Seal every live day that has rows before ``cutoff``, the instant cleanup deletes up to.

        Call it in the cleanup, before the delete. Returns how many days were sealed.
        """
        cutoff = utc_naive_datetime(cutoff)
        async with self.db.execute(
            "SELECT DISTINCT date(detection_time) FROM detections WHERE detection_time < ?",
            (cutoff.isoformat(sep=" "),),
        ) as cursor:
            utc_days = [date.fromisoformat(str(row[0])) for row in await cursor.fetchall() if row[0]]
        last_day = local_date(cutoff, zone=zone)
        days = {
            local
            for utc_day in utc_days
            for local in self._local_days_of_utc_day(utc_day, zone)
            if last_day is not None and local <= last_day
        }
        return await self._seal(days, zone=zone, now=now, cleanup_cutoff=cutoff)

    async def seal_days_of_events(self, frigate_events: Collection[str], *, zone: tzinfo, now: datetime) -> int:
        """Seal the days of events about to be removed because Frigate no longer has them."""
        events = list(dict.fromkeys(frigate_events))
        if not events:
            return 0
        placeholders = ",".join("?" for _ in events)
        async with self.db.execute(
            f"SELECT detection_time FROM detections WHERE frigate_event IN ({placeholders})", events
        ) as cursor:
            moments = [row[0] for row in await cursor.fetchall() if row[0]]
        days = {
            local_date(datetime.fromisoformat(str(moment)), zone=zone)
            for moment in moments
            if local_date(datetime.fromisoformat(str(moment)), zone=zone) is not None
        }
        return await self._seal({day for day in days if day is not None}, zone=zone, now=now, cleanup_cutoff=None)

    @staticmethod
    def _local_days_of_utc_day(utc_day: date, zone: tzinfo) -> set[date]:
        start = datetime.combine(utc_day, datetime.min.time())
        first = local_date(start, zone=zone)
        last = local_date(start + timedelta(days=1) - _LAST_INSTANT, zone=zone)
        assert first is not None and last is not None
        return {first + timedelta(days=offset) for offset in range((last - first).days + 1)}

    async def _seal(self, days: set[date], *, zone: tzinfo, now: datetime, cleanup_cutoff: datetime | None) -> int:
        # Today is still being recorded; sealing it would hide every capture that follows.
        today = local_date(utc_naive_datetime(now), zone=zone)
        days = {day for day in days if today is not None and day < today}
        if not days:
            return 0
        await self.db.execute("BEGIN IMMEDIATE")
        try:
            already = await self.sealed_days(min(days), max(days))
            # Before the first tracked cleanup, older rows may already have been removed by an
            # untracked one, so those days cannot be called complete.
            async with self.db.execute(
                "SELECT 1 FROM daily_totals_days WHERE cleanup_cutoff IS NOT NULL LIMIT 1"
            ) as cursor:
                tracked_before = await cursor.fetchone() is not None
            sealed = 0
            for day in sorted(days - set(already)):
                await self.db.execute(
                    "INSERT INTO daily_totals_days (day, sealed_at, complete, cleanup_cutoff) VALUES (?, ?, ?, ?)",
                    (
                        day.isoformat(),
                        utc_naive_datetime(now).isoformat(sep=" "),
                        1 if tracked_before else 0,
                        cleanup_cutoff.isoformat(sep=" ") if cleanup_cutoff else None,
                    ),
                )
                await self._write_day_totals(day, zone)
                sealed += 1
            await self.db.commit()
            return sealed
        except BaseException:
            await self.db.rollback()
            raise

    async def _write_day_totals(self, day: date, zone: tzinfo) -> None:
        start, end = _day_bounds(day, zone)
        key_sql = self._canonical_key_sql()
        join_sql = self._taxonomy_join_sql()
        async with self.db.execute(
            f"""SELECT {key_sql} AS species_key,
                    MAX(d.species_id),
                    COALESCE(MAX(d.taxa_id), MAX(tc.taxa_id)),
                    COALESCE(MAX(d.scientific_name), MAX(tc.scientific_name)),
                    COALESCE(MAX(d.common_name), MAX(tc.common_name)),
                    MAX(d.display_name),
                    COUNT(DISTINCT d.id)
                FROM detections d {join_sql}
                WHERE d.detection_time >= ? AND d.detection_time < ?
                    AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                GROUP BY species_key""",
            (start.isoformat(sep=" "), end.isoformat(sep=" ")),
        ) as cursor:
            captures = await cursor.fetchall()
        if not captures:
            return
        visits = await self._visits_opened_by_key(key_sql, join_sql, start, end)
        for key, species_id, taxa_id, scientific, common, display, capture_count in captures:
            visit_count = visits.get(key, 0)
            if visit_count > capture_count:
                log.warning("daily_totals_visits_exceed_captures", day=day.isoformat(), species_key=key)
                visit_count = capture_count
            await self.db.execute(
                """INSERT INTO species_daily_totals
                    (day, species_key, species_id, taxa_id, scientific_name, common_name, display_name,
                     capture_count, visit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    day.isoformat(),
                    key,
                    species_id,
                    taxa_id,
                    scientific,
                    common,
                    display or key,
                    int(capture_count),
                    int(visit_count),
                ),
            )

    async def _visits_opened_by_key(
        self, key_sql: str, join_sql: str, start: datetime, end: datetime
    ) -> dict[str, int]:
        from app.repositories.visit_repository import VisitRepository

        cte, params = await VisitRepository(self.db).grouping_cte(
            start=start - _VISIT_LOOKBACK, end=end - _LAST_INSTANT
        )
        async with self.db.execute(
            f"""WITH {cte} SELECT {key_sql} AS key, COUNT(DISTINCT d.visit_id)
                FROM visit_members d {join_sql}
                WHERE d.visit_position = 1 AND d.detection_time >= ?
                GROUP BY key""",
            [*params, start.isoformat(sep=" ")],
        ) as cursor:
            return {str(key): int(count) for key, count in await cursor.fetchall()}
