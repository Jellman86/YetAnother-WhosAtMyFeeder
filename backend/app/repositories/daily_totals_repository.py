"""Per-day species totals that outlive the detection rows they were counted from (#949).

A day is either *live*, read from its stored rows plus any captures Frigate lost, or *sealed*,
read from the captures and visits written here from those rows just before an age cleanup removes
any of them. The boundary is an exact UTC range per day, so the same capture is never counted
twice. The contract:

- Every delete by age goes through ``seal_and_delete_older_than``: it seals, commits, then
  deletes, and deletes nothing if sealing fails. A test refuses any other caller.
- A capture deleted because Frigate no longer has its event is kept as a ``lost_captures`` row,
  written in the same transaction as its delete. Its day stays live, so corrections still apply
  to the rest of it, and the lost capture is folded into the day's total when the day is sealed.
- Ingest never writes here. Re-processing an event cannot change a sealed day, and a live day is
  counted from rows whose ``frigate_event`` is unique.
- Hiding, relabelling or deleting a capture by hand is the owner correcting the record. On a live
  day it changes the counts. A day is sealed as soon as an age cleanup starts removing its
  captures, and from then on a correction to one still stored on it does not change its totals.
- A day is complete only if it began after tracking started, the instant the migration recorded.
- Deleting all history deletes all of this with it.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

import structlog

from app.repositories.detection_repository import DetectionRepository
from app.services.daily_history import local_midnight_utc
from app.utils.api_datetime import utc_naive_datetime
from app.utils.calendar_day import local_date

log = structlog.get_logger()

# A visit that opens just before midnight is still running after it. Grouping from the day
# before means each visit is counted once, on the day it opened.
_VISIT_LOOKBACK = timedelta(days=1)
# Days sealed per transaction, so a first cleanup over a long history does not hold the write
# lock, and with it ingest, for the whole run. Each day is still written whole.
SEAL_BATCH_DAYS = 7
_HOUR_BUCKET = "strftime('%Y-%m-%dT%H:00:00Z', detection_time)"


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
class LostCapture:
    frigate_event: str
    detection_time: datetime
    species_key: str
    scientific_name: str | None
    display_name: str


@dataclass(frozen=True)
class SealedDay:
    day: date
    complete: bool


def _day_bounds(day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    return local_midnight_utc(day, zone), local_midnight_utc(day + timedelta(days=1), zone)


def _stamp(value: datetime) -> str:
    return utc_naive_datetime(value).isoformat(sep=" ")


class DailyTotalsRepository(DetectionRepository):
    async def tracking_started_at(self) -> datetime | None:
        async with self.db.execute("SELECT started_at FROM daily_totals_tracking WHERE id = 1") as cursor:
            row = await cursor.fetchone()
        return datetime.fromisoformat(str(row[0])) if row and row[0] else None

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
        species_keys: Collection[str] | None = None,
    ) -> list[SpeciesDayTotal]:
        """Sealed totals, optionally for the canonical species keys ``species_keys`` names."""
        conditions, params = ["1 = 1"], []
        if start is not None:
            conditions.append("day >= ?")
            params.append(start.isoformat())
        if end is not None:
            conditions.append("day <= ?")
            params.append(end.isoformat())
        if species_keys is not None:
            if not species_keys:
                return []
            conditions.append(f"species_key IN ({','.join('?' for _ in species_keys)})")
            params.extend(species_keys)
        async with self.db.execute(
            f"""SELECT day, species_key, species_id, taxa_id, scientific_name, common_name, display_name,
                    capture_count, visit_count
                FROM species_daily_totals WHERE {" AND ".join(conditions)} ORDER BY day, species_key""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [SpeciesDayTotal(date.fromisoformat(str(row[0])), *row[1:]) for row in rows]

    async def species_keys(
        self, names: Collection[str], *, species_ids: Collection[int], taxa_id: int | None = None
    ) -> set[str]:
        """Every canonical key one species is kept under, in totals or lost captures.

        A rename moves a species' name but not its catalogue identity, so sealed days stored under
        an older name are still found by ``species_id``.
        """
        ids = sorted({int(species_id) for species_id in species_ids})
        folded = sorted({name.strip().casefold() for name in names if name and name.strip()})
        keys = {f"species:{species_id}" for species_id in ids}
        matches, params = [], []
        if ids:
            matches.append(f"species_id IN ({','.join('?' for _ in ids)})")
            params.extend(ids)
        if taxa_id is not None:
            matches.append("taxa_id = ?")
            params.append(taxa_id)
        if folded:
            placeholders = ",".join("?" for _ in folded)
            for column in ("scientific_name", "common_name", "display_name"):
                matches.append(f"LOWER({column}) IN ({placeholders})")
                params.extend(folded)
        if not matches:
            return keys
        where = " OR ".join(matches)
        async with self.db.execute(
            f"""SELECT species_key FROM species_daily_totals WHERE {where}
                UNION SELECT species_key FROM lost_captures WHERE {where}""",
            [*params, *params],
        ) as cursor:
            keys.update(str(row[0]) for row in await cursor.fetchall())
        return keys

    async def species_ids_named(self, name: str) -> list[int]:
        """Catalogue identities stored rows carry under this name."""
        return await self._species_ids_for_name(name)

    async def unknown_species_keys(self, is_unknown: Callable[[str], bool]) -> set[str]:
        """Keys whose label the live count treats as Unknown bird, by the same rule."""
        async with self.db.execute(
            """SELECT species_key, display_name FROM species_daily_totals
                UNION SELECT species_key, display_name FROM lost_captures"""
        ) as cursor:
            return {str(key) for key, label in await cursor.fetchall() if is_unknown(str(label or ""))}

    async def lost_captures(
        self, start: datetime | None = None, end: datetime | None = None, *, species_keys: Collection[str] | None = None
    ) -> list[LostCapture]:
        where, params = self._lost_filter(start, end, species_keys)
        if where is None:
            return []
        async with self.db.execute(
            f"""SELECT frigate_event, detection_time, species_key, scientific_name, display_name
                FROM lost_captures WHERE {where} ORDER BY detection_time, frigate_event""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            LostCapture(str(event), datetime.fromisoformat(str(at)), str(key), scientific, str(display))
            for event, at, key, scientific, display in rows
        ]

    async def lost_hourly_counts(
        self, start: datetime | None = None, end: datetime | None = None, *, species_keys: Collection[str] | None = None
    ) -> dict[str, int]:
        """Captures Frigate lost from live days, by the same UTC hour buckets as stored captures."""
        where, params = self._lost_filter(start, end, species_keys)
        if where is None:
            return {}
        async with self.db.execute(
            f"SELECT {_HOUR_BUCKET} AS bucket, COUNT(*) FROM lost_captures WHERE {where} GROUP BY bucket", params
        ) as cursor:
            return {str(bucket): int(count) for bucket, count in await cursor.fetchall()}

    @staticmethod
    def _lost_filter(
        start: datetime | None, end: datetime | None, species_keys: Collection[str] | None
    ) -> tuple[str | None, list]:
        conditions, params = ["1 = 1"], []
        if start is not None:
            conditions.append("detection_time >= ?")
            params.append(_stamp(start))
        if end is not None:
            conditions.append("detection_time < ?")
            params.append(_stamp(end))
        if species_keys is not None:
            if not species_keys:
                return None, []
            conditions.append(f"species_key IN ({','.join('?' for _ in species_keys)})")
            params.extend(species_keys)
        return " AND ".join(conditions), params

    async def seal_and_delete_older_than(
        self,
        cutoff: datetime,
        *,
        zone: tzinfo,
        now: datetime,
        preserve_favorites: bool = True,
        species_floor: int = 0,
    ) -> int:
        """The only delete by age: seal every day it would touch, then delete. Returns rows deleted.

        If sealing raises, nothing is deleted and the error propagates.
        """
        cutoff = utc_naive_datetime(cutoff)
        await self.seal_before(cutoff, zone=zone, now=now)
        deleted = await self.delete_older_than(
            cutoff, preserve_favorites=preserve_favorites, species_floor=species_floor
        )
        # The last, empty chunk of the delete still opened a transaction; close it.
        await self.db.commit()
        return deleted

    async def seal_before(self, cutoff: datetime, *, zone: tzinfo, now: datetime) -> int:
        """Seal every live day with a stored or lost capture before ``cutoff``. Returns days sealed."""
        cutoff_stamp = _stamp(cutoff)
        # By the minute, so a day in a zone a half or three quarters of an hour off UTC is exact.
        async with self.db.execute(
            """SELECT DISTINCT substr(detection_time, 1, 16) FROM detections WHERE detection_time < ?
                UNION SELECT DISTINCT substr(detection_time, 1, 16) FROM lost_captures WHERE detection_time < ?""",
            (cutoff_stamp, cutoff_stamp),
        ) as cursor:
            minutes = [str(row[0]) for row in await cursor.fetchall() if row[0]]
        days = {local_date(datetime.fromisoformat(minute), zone=zone) for minute in minutes}
        return await self._seal({day for day in days if day is not None}, zone=zone, now=now)

    async def delete_lost_capture(
        self, frigate_event: str, *, zone: tzinfo, now: datetime, preserve_favorites: bool = True
    ) -> bool:
        """Delete a capture Frigate no longer has, keeping its count in the same transaction.

        Returns whether the row was deleted. A favourite kept by ``preserve_favorites`` records
        nothing, a hidden capture counted for nothing and records nothing, and a capture on an
        already sealed day is inside that day's total already.
        """
        keep_favourite = (
            " AND NOT EXISTS (SELECT 1 FROM detection_favorites f WHERE f.detection_id = d.id)"
            if preserve_favorites
            else ""
        )
        await self.db.execute("BEGIN IMMEDIATE")
        try:
            async with self.db.execute(
                "SELECT detection_time FROM detections WHERE frigate_event = ?", (frigate_event,)
            ) as cursor:
                row = await cursor.fetchone()
            day = local_date(datetime.fromisoformat(str(row[0])), zone=zone) if row and row[0] else None
            if day is not None and not await self.sealed_days(day, day):
                key_sql = self._canonical_key_sql()
                await self.db.execute(
                    f"""INSERT OR IGNORE INTO lost_captures
                        (frigate_event, detection_time, species_key, species_id, taxa_id, scientific_name,
                         common_name, display_name, lost_at)
                    SELECT d.frigate_event, MAX(d.detection_time), MAX({key_sql}), MAX(d.species_id),
                        COALESCE(MAX(d.taxa_id), MAX(tc.taxa_id)),
                        COALESCE(MAX(d.scientific_name), MAX(tc.scientific_name)),
                        COALESCE(MAX(d.common_name), MAX(tc.common_name)), MAX(d.display_name), ?
                    FROM detections d {self._taxonomy_join_sql()}
                    WHERE d.frigate_event = ? AND (d.is_hidden = 0 OR d.is_hidden IS NULL){keep_favourite}
                    GROUP BY d.frigate_event""",
                    (_stamp(now), frigate_event),
                )
            await self.db.execute(
                f"DELETE FROM detections AS d WHERE d.frigate_event = ?{keep_favourite}", (frigate_event,)
            )
            deleted = await self._last_statement_changes() > 0
            if not deleted:
                await self.db.rollback()
                return False
            await self.db.commit()
            return True
        except BaseException:
            await self.db.rollback()
            raise

    async def _seal(self, days: set[date], *, zone: tzinfo, now: datetime) -> int:
        # Today is still being recorded; sealing it would hide every capture that follows.
        today = local_date(utc_naive_datetime(now), zone=zone)
        pending = sorted(day for day in days if today is not None and day < today)
        started = await self.tracking_started_at()
        sealed = 0
        for offset in range(0, len(pending), SEAL_BATCH_DAYS):
            batch = pending[offset : offset + SEAL_BATCH_DAYS]
            await self.db.execute("BEGIN IMMEDIATE")
            try:
                already = await self.sealed_days(batch[0], batch[-1])
                for day in batch:
                    if day in already:
                        continue
                    # A day that began before tracking may have lost rows with no record of them.
                    complete = started is not None and local_midnight_utc(day, zone) >= started
                    await self.db.execute(
                        "INSERT INTO daily_totals_days (day, sealed_at, complete) VALUES (?, ?, ?)",
                        (day.isoformat(), _stamp(now), 1 if complete else 0),
                    )
                    await self._write_day_totals(day, zone)
                    sealed += 1
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
        return sealed

    async def _write_day_totals(self, day: date, zone: tzinfo) -> None:
        start, end = _day_bounds(day, zone)
        bounds = (_stamp(start), _stamp(end))
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
            bounds,
        ) as cursor:
            rows = await cursor.fetchall()
        async with self.db.execute(
            """SELECT species_key, MAX(species_id), MAX(taxa_id), MAX(scientific_name), MAX(common_name),
                    MAX(display_name), COUNT(*)
                FROM lost_captures WHERE detection_time >= ? AND detection_time < ? GROUP BY species_key""",
            bounds,
        ) as cursor:
            lost = await cursor.fetchall()
        counted: dict[str, list] = {str(row[0]): list(row[1:]) for row in rows}
        for key, *fields in lost:
            if key in counted:
                counted[key][5] += int(fields[5])
            else:
                counted[key] = list(fields)
        visits = await self._visits_opened_by_key(key_sql, join_sql, start, end) if rows else {}
        for key, (species_id, taxa_id, scientific, common, display, capture_count) in counted.items():
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
        # Folded into the day's total, the lost captures' own records have done their job.
        await self.db.execute("DELETE FROM lost_captures WHERE detection_time >= ? AND detection_time < ?", bounds)

    async def _visits_opened_by_key(
        self, key_sql: str, join_sql: str, start: datetime, end: datetime
    ) -> dict[str, int]:
        from app.repositories.visit_repository import VisitRepository

        cte, params = await VisitRepository(self.db).grouping_cte(
            start=start - _VISIT_LOOKBACK, end=end - timedelta(microseconds=1)
        )
        async with self.db.execute(
            f"""WITH {cte} SELECT {key_sql} AS key, COUNT(DISTINCT d.visit_id)
                FROM visit_members d {join_sql}
                WHERE d.visit_position = 1 AND d.detection_time >= ?
                GROUP BY key""",
            [*params, _stamp(start)],
        ) as cursor:
            return {str(key): int(count) for key, count in await cursor.fetchall()}

    async def live_species_keys(
        self, start: datetime, end: datetime, *, exclude: list[tuple[datetime, datetime]]
    ) -> set[str]:
        """Canonical keys of visible stored captures in ``[start, end)`` outside the sealed ranges."""
        conditions = ["d.detection_time >= ?", "d.detection_time < ?", "(d.is_hidden = 0 OR d.is_hidden IS NULL)"]
        params: list = [_stamp(start), _stamp(end)]
        for range_start, range_end in exclude:
            conditions.append("NOT (d.detection_time >= ? AND d.detection_time < ?)")
            params.extend([_stamp(range_start), _stamp(range_end)])
        async with self.db.execute(
            f"""SELECT DISTINCT {self._canonical_key_sql()} FROM detections d {self._taxonomy_join_sql()}
                WHERE {" AND ".join(conditions)}""",
            params,
        ) as cursor:
            keys = {str(row[0]) for row in await cursor.fetchall()}
        lost_where, lost_params = self._lost_filter(start, end, None)
        async with self.db.execute(
            f"SELECT DISTINCT species_key FROM lost_captures WHERE {lost_where}", lost_params
        ) as cursor:
            keys.update(str(row[0]) for row in await cursor.fetchall())
        return keys
