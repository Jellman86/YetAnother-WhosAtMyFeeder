"""Persistence for the regional species list and the range filter's decisions (#696)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite

from app.utils.api_datetime import serialize_storage_datetime


@dataclass(frozen=True)
class StoredRangeList:
    source: str
    region_code: str
    region_codes: tuple[str, ...]
    region_name: str | None
    region_level: str
    location_key: str
    fetched_at: datetime
    region_species_total: int
    note: str | None


@dataclass(frozen=True)
class StoredTaxon:
    species_code: str
    scientific_name: str
    common_name: str | None
    in_region: bool


@dataclass(frozen=True)
class RangeDecisionRecord:
    frigate_event: str
    outcome: str
    camera: str | None
    detected_at: datetime | None
    decided_at: datetime
    original_label: str
    original_score: float
    original_species_id: int | None
    chosen_label: str | None
    chosen_score: float | None
    region_code: str
    source: str


@dataclass(frozen=True)
class SpeciesSighting:
    species_id: int
    detections: int
    last_seen: datetime


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


_DECISION_COLUMNS = (
    "frigate_event, outcome, camera, detected_at, decided_at, original_label, original_score, "
    "original_species_id, chosen_label, chosen_score, region_code, source"
)


def _decision(row: Sequence[Any]) -> RangeDecisionRecord:
    (
        frigate_event,
        outcome,
        camera,
        detected_at,
        decided_at,
        original_label,
        original_score,
        original_species_id,
        chosen_label,
        chosen_score,
        region_code,
        source,
    ) = row
    return RangeDecisionRecord(
        frigate_event=str(frigate_event),
        outcome=str(outcome),
        camera=str(camera) if camera is not None else None,
        detected_at=_parse_datetime(detected_at),
        decided_at=_parse_datetime(decided_at) or datetime.min,
        original_label=str(original_label),
        original_score=float(original_score),
        original_species_id=int(original_species_id) if original_species_id is not None else None,
        chosen_label=str(chosen_label) if chosen_label is not None else None,
        chosen_score=float(chosen_score) if chosen_score is not None else None,
        region_code=str(region_code),
        source=str(source),
    )


class RangeFilterRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def replace_list(self, stored: StoredRangeList, taxa: Sequence[StoredTaxon]) -> None:
        """Swap in a new list for its source in one transaction, so a reader never sees half of one."""
        try:
            if not self.db.in_transaction:
                await self.db.execute("BEGIN IMMEDIATE")
            async with self.db.execute("SELECT id FROM range_lists WHERE source = ?", (stored.source,)) as cursor:
                previous = [row[0] for row in await cursor.fetchall()]
            for list_id in previous:
                await self.db.execute("DELETE FROM range_list_taxa WHERE list_id = ?", (list_id,))
            await self.db.execute("DELETE FROM range_lists WHERE source = ?", (stored.source,))
            cursor = await self.db.execute(
                """INSERT INTO range_lists (
                       source, region_code, region_codes, region_name, region_level, location_key,
                       fetched_at, region_species_total, note
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    stored.source,
                    stored.region_code,
                    json.dumps(list(stored.region_codes)),
                    stored.region_name,
                    stored.region_level,
                    stored.location_key,
                    serialize_storage_datetime(stored.fetched_at),
                    stored.region_species_total,
                    stored.note,
                ),
            )
            list_id = cursor.lastrowid
            await cursor.close()
            await self.db.executemany(
                """INSERT OR IGNORE INTO range_list_taxa
                       (list_id, species_code, scientific_name, common_name, in_region)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (list_id, taxon.species_code, taxon.scientific_name, taxon.common_name, int(taxon.in_region))
                    for taxon in taxa
                ],
            )
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise

    async def load_list(self, source: str) -> tuple[StoredRangeList, list[StoredTaxon]] | None:
        async with self.db.execute(
            """SELECT id, source, region_code, region_codes, region_name, region_level, location_key,
                      fetched_at, region_species_total, note
               FROM range_lists WHERE source = ? LIMIT 1""",
            (source,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        list_id, source_value, region_code, region_codes, region_name, level, key, fetched, total, note = row
        fetched_at = _parse_datetime(fetched)
        try:
            codes = json.loads(region_codes)
        except (TypeError, ValueError):
            codes = None
        if fetched_at is None or not isinstance(codes, list):
            return None
        stored = StoredRangeList(
            source=str(source_value),
            region_code=str(region_code),
            region_codes=tuple(str(code) for code in codes),
            region_name=str(region_name) if region_name is not None else None,
            region_level=str(level),
            location_key=str(key),
            fetched_at=fetched_at,
            region_species_total=int(total),
            note=str(note) if note is not None else None,
        )
        async with self.db.execute(
            "SELECT species_code, scientific_name, common_name, in_region FROM range_list_taxa WHERE list_id = ?",
            (list_id,),
        ) as cursor:
            taxa = [
                StoredTaxon(
                    species_code=str(code),
                    scientific_name=str(scientific),
                    common_name=str(common) if common is not None else None,
                    in_region=bool(in_region),
                )
                for code, scientific, common, in_region in await cursor.fetchall()
            ]
        return stored, taxa

    async def heard_species(self, since: datetime) -> list[tuple[int | None, str | None]]:
        """Distinct identities BirdNET-Go reported at this site since a time, hidden rows excluded."""
        async with self.db.execute(
            """SELECT DISTINCT species_id, scientific_name FROM audio_detections
               WHERE timestamp >= ? AND COALESCE(is_hidden, 0) = 0
                 AND (species_id IS NOT NULL OR scientific_name IS NOT NULL)
               LIMIT 5000""",
            (serialize_storage_datetime(since),),
        ) as cursor:
            return [
                (int(species_id) if species_id is not None else None, str(name) if name is not None else None)
                for species_id, name in await cursor.fetchall()
            ]

    async def recent_species_sightings(self, since: datetime, *, limit: int = 2000) -> list[SpeciesSighting]:
        async with self.db.execute(
            """SELECT species_id, COUNT(*) AS detections, MAX(detection_time) AS last_seen
               FROM detections
               WHERE detection_time >= ? AND COALESCE(is_hidden, 0) = 0 AND species_id IS NOT NULL
               GROUP BY species_id ORDER BY detections DESC LIMIT ?""",
            (serialize_storage_datetime(since), limit),
        ) as cursor:
            return [
                SpeciesSighting(
                    species_id=int(species_id),
                    detections=int(detections),
                    last_seen=_parse_datetime(last_seen) or since,
                )
                for species_id, detections, last_seen in await cursor.fetchall()
            ]

    async def record_decision(self, record: RangeDecisionRecord) -> None:
        await self.db.execute(
            """INSERT INTO range_filter_decisions (
                   frigate_event, outcome, camera, detected_at, decided_at, original_label, original_score,
                   original_species_id, chosen_label, chosen_score, region_code, source
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(frigate_event) DO UPDATE SET
                   outcome = excluded.outcome,
                   camera = COALESCE(excluded.camera, range_filter_decisions.camera),
                   detected_at = COALESCE(excluded.detected_at, range_filter_decisions.detected_at),
                   decided_at = excluded.decided_at,
                   original_label = excluded.original_label,
                   original_score = excluded.original_score,
                   original_species_id = excluded.original_species_id,
                   chosen_label = excluded.chosen_label,
                   chosen_score = excluded.chosen_score,
                   region_code = excluded.region_code,
                   source = excluded.source""",
            (
                record.frigate_event,
                record.outcome,
                record.camera,
                serialize_storage_datetime(record.detected_at) if record.detected_at else None,
                serialize_storage_datetime(record.decided_at),
                record.original_label,
                record.original_score,
                record.original_species_id,
                record.chosen_label,
                record.chosen_score,
                record.region_code,
                record.source,
            ),
        )
        await self.db.commit()

    async def get_decision(self, frigate_event: str) -> RangeDecisionRecord | None:
        async with self.db.execute(
            f"SELECT {_DECISION_COLUMNS} FROM range_filter_decisions WHERE frigate_event = ?", (frigate_event,)
        ) as cursor:
            row = await cursor.fetchone()
        return _decision(row) if row else None

    async def recent_skips(self, *, limit: int) -> list[RangeDecisionRecord]:
        async with self.db.execute(
            f"SELECT {_DECISION_COLUMNS} FROM range_filter_decisions"
            " WHERE outcome = 'skipped' ORDER BY decided_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            return [_decision(row) for row in await cursor.fetchall()]

    async def count_decisions_since(self, since: datetime) -> dict[str, int]:
        counts = {"fallback": 0, "skipped": 0}
        async with self.db.execute(
            "SELECT outcome, COUNT(*) AS n FROM range_filter_decisions WHERE decided_at >= ? GROUP BY outcome",
            (serialize_storage_datetime(since),),
        ) as cursor:
            for outcome, count in await cursor.fetchall():
                counts[str(outcome)] = int(count)
        return counts

    async def prune_decisions(self, before: datetime) -> int:
        cursor = await self.db.execute(
            "DELETE FROM range_filter_decisions WHERE decided_at < ?", (serialize_storage_datetime(before),)
        )
        removed = cursor.rowcount or 0
        await cursor.close()
        await self.db.commit()
        return removed
