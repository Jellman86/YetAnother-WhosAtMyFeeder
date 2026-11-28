"""Persisted BirdNET-Go detections: ingest, hiding, history, context and public sharing.

Split out of the detection repository without changing a statement or a commit:
every method runs on the caller's connection and commits exactly where it did
before.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING, Any, Optional

import aiosqlite

from app.utils.api_datetime import parse_storage_datetime, serialize_api_datetime, serialize_storage_datetime
from app.utils.audio_source_identity import (
    AudioSourceDirectory,
    SourceKey,
    SourceObservation,
    StoredSource,
    read_stored_source,
    source_of_payload,
)
from app.utils.audio_source_links import AudioSourceLink, audio_source_links, literal_source_name
from app.utils.birdnet_payload import (
    extract_audio_mapping_keys,
    extract_birdnet_id,
    extract_birdnet_source_name,
    parse_mapping_filter_values,
)

if TYPE_CHECKING:
    from app.repositories.detection_repository import Detection


def _audio_species_matches(species: object, scientific_name: object, primary: object) -> bool:
    key = str(primary or "").strip().casefold()
    return bool(key) and key in {str(species or "").strip().casefold(), str(scientific_name or "").strip().casefold()}


async def public_audio_conditions_sql(db: aiosqlite.Connection, *, match_species: bool = True) -> tuple[str, list]:
    from app.config import settings
    from app.utils.public_access import public_events_window

    mappings = {
        camera: parse_mapping_filter_values(value)
        for camera, value in (settings.frigate.camera_audio_mapping or {}).items()
    }

    def mapping_matches(camera: str, sensor: str | None, raw: str | None) -> bool:
        wildcard, keys = mappings.get(camera, (False, set()))
        return wildcard or bool(keys.intersection(extract_audio_mapping_keys(sensor, raw)))

    def window_bound(stamp: str, seconds: int) -> str | None:
        try:
            return serialize_storage_datetime(datetime.fromisoformat(stamp) + timedelta(seconds=seconds))
        except (ValueError, TypeError):
            return None

    await db.create_function("public_audio_mapping_matches", 3, mapping_matches, deterministic=True)
    await db.create_function("public_audio_species_matches", 3, _audio_species_matches, deterministic=True)
    await db.create_function("public_audio_window_bound", 2, window_bound, deterministic=True)
    public_start, public_end = public_events_window()
    seconds = int(settings.frigate.audio_correlation_window_seconds)
    # Competing inequalities let SQLite seek the whole shared-history range and
    # evaluate the capture bound once per audio row. One intersected range makes
    # the timestamp index seek only this capture's authorized correlation window.
    sql = """a.is_hidden = 0
        AND a.timestamp >= MAX(?, public_audio_window_bound(d.detection_time, ?))"""
    params = [serialize_storage_datetime(public_start), -seconds]
    if public_end is None:
        sql += " AND a.timestamp <= public_audio_window_bound(d.detection_time, ?)"
        params.append(seconds)
    else:
        end = serialize_storage_datetime(public_end)
        sql += """ AND a.timestamp <= MIN(?, public_audio_window_bound(d.detection_time, ?))
            AND a.timestamp <> ?"""
        # MIN caps the inclusive seek at midnight; excluding that exact endpoint
        # retains the public window's exclusive end without a competing range.
        params.extend([end, seconds, end])
    sql += " AND public_audio_mapping_matches(d.camera_name, a.sensor_id, a.raw_data)"
    if match_species:
        sql += " AND public_audio_species_matches(a.species, a.scientific_name, d.audio_species)"
    return sql, params


_SOURCE_COLUMNS = ("source_node", "source_id", "source_name")


async def _distinct_source_values(
    db: aiosqlite.Connection, column: str, prefix: list[tuple[str, str | None]]
) -> list[str | None]:
    """Each value ``column`` takes under the fixed ``prefix``, by index seeks rather than a scan.

    The identity index orders calls by node, id and name, so each next value is one seek past the
    last: the work grows with the number of sources, never with the number of calls.
    """
    fixed = [f"{name} IS ?" for name, _ in prefix]
    params = [value for _, value in prefix]
    values: list[str | None] = []
    async with db.execute(
        f"SELECT 1 FROM audio_detections WHERE {' AND '.join([*fixed, f'{column} IS NULL'])} LIMIT 1", params
    ) as cursor:
        if await cursor.fetchone() is not None:
            values.append(None)
    last: str | None = None
    while True:
        bound = f"{column} > ?" if last is not None else f"{column} IS NOT NULL"
        async with db.execute(
            f"SELECT MIN({column}) FROM audio_detections WHERE {' AND '.join([*fixed, bound])}",
            [*params, *([last] if last is not None else [])],
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return values
        last = str(row[0])
        values.append(last)


async def load_audio_source_directory(
    db: aiosqlite.Connection,
    *,
    minimum_start: datetime | None = None,
    maximum_end: datetime | None = None,
    hidden: bool = False,
    owner_evidence: bool = False,
) -> AudioSourceDirectory:
    """Every source the history has heard, under each name it carried, read by index seeks.

    Names and the newest name come from the calls a view shows: visible ones, or hidden ones for
    the owner's hidden view. With ``owner_evidence``, every call the owner keeps also says which
    source carried which name, so hiding a call never moves an older id-less call to another
    source. A guest's view passes the shared window and no owner evidence, so no name or id from
    outside the shared calls reaches them, not even through a filter or an older call joining a
    renamed source.

    Each (node, id, name) a call carries is found by seeking the identity index, and its newest
    call in the view by one more seek, so a request costs the same however many calls are stored.
    """
    return AudioSourceDirectory(
        await _read_source_observations(
            db, minimum_start=minimum_start, maximum_end=maximum_end, hidden=hidden, owner_evidence=owner_evidence
        )
    )


async def _read_source_observations(
    db: aiosqlite.Connection,
    *,
    minimum_start: datetime | None,
    maximum_end: datetime | None,
    hidden: bool,
    owner_evidence: bool,
) -> list[SourceObservation]:
    """Each stored (node, id, name) with its newest call in the view, and as evidence when asked."""
    bounds, bound_params = [], []
    if minimum_start is not None:
        bounds.append("timestamp >= ?")
        bound_params.append(serialize_storage_datetime(minimum_start))
    if maximum_end is not None:
        bounds.append("timestamp < ?")
        bound_params.append(serialize_storage_datetime(maximum_end))

    async def newest(identity: tuple[str | None, ...], is_hidden: bool) -> str | None:
        clauses = [f"{column} IS ?" for column in _SOURCE_COLUMNS] + ["is_hidden = ?", *bounds]
        async with db.execute(
            f"SELECT MAX(timestamp) FROM audio_detections WHERE {' AND '.join(clauses)}",
            [*identity, int(is_hidden), *bound_params],
        ) as cursor:
            row = await cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else None

    observations: list[SourceObservation] = []
    for node in await _distinct_source_values(db, "source_node", []):
        for source_id in await _distinct_source_values(db, "source_id", [("source_node", node)]):
            names = await _distinct_source_values(db, "source_name", [("source_node", node), ("source_id", source_id)])
            for name in names:
                identity = (node, source_id, name)
                # The other visibility only ever serves as the owner's evidence of who carried a name.
                for is_hidden in (hidden, not hidden) if owner_evidence else (hidden,):
                    last_seen = await newest(identity, is_hidden)
                    if last_seen is not None:
                        observations.append(
                            SourceObservation(
                                node=node,
                                source_id=source_id,
                                name=name,
                                last_seen=last_seen,
                                shown=is_hidden == hidden,
                            )
                        )
    return observations


async def load_audio_source_links(db: aiosqlite.Connection) -> list[AudioSourceLink]:
    """Every source a camera can be linked to, one entry per stream, for the owner's Settings.

    Read as the owner's Audio history reads its sources, with every call the owner keeps as
    evidence of who carried which name, so a stream heard once months ago is listed beside a busy
    one. Each stored (node, id, name) costs an index seek for its newest visible and hidden call,
    and one more for each to read the name the matcher sees on that call, since stored names are
    cleaned for display: the work grows with the number of sources and names, never with the
    number of calls.
    """
    observations = await _read_source_observations(
        db, minimum_start=None, maximum_end=None, hidden=False, owner_evidence=True
    )
    literal_names: dict[tuple[str | None, str | None, str, bool], str] = {}
    for observation in observations:
        if not observation.name:
            continue
        async with db.execute(
            """SELECT sensor_id, raw_data FROM audio_detections
               WHERE source_node IS ? AND source_id IS ? AND source_name IS ? AND is_hidden = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (observation.node, observation.source_id, observation.name, int(not observation.shown)),
        ) as cursor:
            row = await cursor.fetchone()
        literal = literal_source_name(row[0], row[1]) if row else None
        if literal:
            literal_names[(observation.node, observation.source_id, observation.name, observation.shown)] = literal
    return audio_source_links(observations, literal_names)


def filter_names_a_source(source: str | None, search: str | None, search_include_source: bool) -> bool:
    """Whether a history filter can match a source by name or id, so its sources must be read."""
    return bool(source) or bool(search and search.strip() and search_include_source)


async def public_audio_evidence_sql(db: aiosqlite.Connection) -> tuple[str, list]:
    conditions, params = await public_audio_conditions_sql(db)
    return f"EXISTS (SELECT 1 FROM audio_detections a WHERE {conditions})", params


@dataclass
class _AudioContextWindow:
    event_id: str
    camera: str
    target: datetime
    start: str
    end: str


def _calendar_day(stored: object, zone: tzinfo) -> date | None:
    """The day a stored UTC timestamp falls on in ``zone``, or None for one that cannot be read."""
    if not isinstance(stored, str):
        return None
    try:
        instant = datetime.fromisoformat(stored)
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone).date()


def rank_audio_context(
    rows: list[tuple], target_time: datetime, mapping_value: str | None, limit: int
) -> tuple[list[dict], int]:
    # The same extractor /api/audio/recent uses, so payload key handling stays
    # in lockstep (`detectionId` / `id` / `detection_id`).
    wildcard_mapping, mapping_keys = parse_mapping_filter_values(mapping_value)
    results: list[dict] = []
    suppressed_by_mapping = 0
    for row in rows:
        if not wildcard_mapping:
            row_keys = extract_audio_mapping_keys(row[3], row[5])
            if not row_keys.intersection(mapping_keys):
                suppressed_by_mapping += 1
                continue
        det_time = parse_storage_datetime(row[0])
        if det_time.tzinfo is None:
            det_time = det_time.replace(tzinfo=timezone.utc)
        offset_seconds = int((det_time - target_time).total_seconds())

        # raw_data is stored as a JSON string; parse and pull the stable
        # BirdNET-Go id out so the detection modal can render the
        # spectrogram for the matched audio entry.
        birdnet_id: int | None = None
        if row[5]:
            try:
                payload = json.loads(row[5])
            except Exception:
                payload = None
            if isinstance(payload, dict):
                birdnet_id = extract_birdnet_id(payload)

        results.append(
            {
                "timestamp": det_time.isoformat(),
                "species": row[1],
                "confidence": row[2],
                "sensor_id": row[3],
                "scientific_name": row[4],
                "birdnet_id": birdnet_id,
                "offset_seconds": offset_seconds,
            }
        )

    results.sort(key=lambda item: (abs(item["offset_seconds"]), -item["confidence"]))
    return results[:limit], suppressed_by_mapping


class AudioHistoryRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def insert_audio_detection(
        self,
        timestamp: datetime,
        species: str,
        confidence: float,
        sensor_id: Optional[str],
        raw_data: Optional[dict],
        scientific_name: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> int:
        row_id, _inserted = await self.insert_audio_detection_idempotent(
            timestamp=timestamp,
            species=species,
            confidence=confidence,
            sensor_id=sensor_id,
            raw_data=raw_data,
            scientific_name=scientific_name,
            source_event_id=source_event_id,
        )
        return row_id

    async def insert_audio_detection_idempotent(
        self,
        timestamp: datetime,
        species: str,
        confidence: float,
        sensor_id: Optional[str],
        raw_data: Optional[dict],
        scientific_name: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> tuple[int, bool]:
        """Insert one BirdNET detection and report whether this call created it."""
        payload = json.dumps(raw_data or {}, ensure_ascii=True)
        from app.services.audio_identity import resolve_audio_identity

        # Catalogue freshness checks can stat and reload SQLite tables. Finish
        # them off-loop before beginning the history write transaction.
        species_id = await asyncio.to_thread(resolve_audio_identity, scientific_name)
        # The only change to ingest for #1111: record the source cleaned, beside the payload.
        source = source_of_payload(sensor_id, raw_data)
        cursor = await self.db.execute(
            """INSERT INTO audio_detections (
                   timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id,
                   species_id, source_node, source_id, source_name, source_resolved
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(source_event_id) DO NOTHING""",
            (
                serialize_storage_datetime(timestamp),
                species,
                confidence,
                sensor_id,
                payload,
                scientific_name,
                source_event_id,
                # Resolved at ingest so audio and visual detections of one bird
                # share an identity. Unresolvable names record nothing and keep
                # behaving exactly as they do today.
                species_id,
                # The id survives a rename in BirdNET-Go, so history keeps one source whole (#1111).
                source.node,
                source.source_id,
                source.name,
            ),
        )
        inserted = cursor.rowcount > 0
        row_id = cursor.lastrowid
        await cursor.close()
        if not inserted and source_event_id:
            async with self.db.execute(
                "SELECT id FROM audio_detections WHERE source_event_id = ?",
                (source_event_id,),
            ) as existing_cursor:
                existing = await existing_cursor.fetchone()
            row_id = existing[0] if existing else None
        await self.db.commit()
        if row_id is None:
            raise RuntimeError("Audio detection insert did not return a row id")
        return int(row_id), inserted

    async def delete_audio_detection(self, detection_id: int) -> bool:
        """Delete one diagnostic audio row immediately after its write was proven."""
        cursor = await self.db.execute("DELETE FROM audio_detections WHERE id = ?", (detection_id,))
        deleted = cursor.rowcount > 0
        await cursor.close()
        await self.db.commit()
        return deleted

    async def set_audio_hidden(self, detection_id: int, hidden: bool) -> bool:
        cursor = await self.db.execute(
            "UPDATE audio_detections SET is_hidden = ? WHERE id = ?", (int(hidden), detection_id)
        )
        found = cursor.rowcount > 0
        await cursor.close()
        await self.db.commit()
        return found

    async def set_audio_hidden_bulk(self, detection_ids: list[int], hidden: bool) -> list[int]:
        """Set visibility on many audio detections in one transaction, returning existing row ids."""
        unique_ids = list(dict.fromkeys(int(item) for item in detection_ids if int(item) >= 1))
        if not unique_ids:
            return []
        placeholders = ",".join("?" for _ in unique_ids)
        async with self.db.execute(
            f"SELECT id FROM audio_detections WHERE id IN ({placeholders})",
            unique_ids,
        ) as cursor:
            existing = [int(row[0]) for row in await cursor.fetchall()]
        if not existing:
            return []
        update_placeholders = ",".join("?" for _ in existing)
        cursor = await self.db.execute(
            f"UPDATE audio_detections SET is_hidden = ? WHERE id IN ({update_placeholders})",
            [int(hidden), *existing],
        )
        await cursor.close()
        await self.db.commit()
        return existing

    async def count_hidden_audio_detections(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM audio_detections WHERE is_hidden = 1") as cursor:
            row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0

    async def get_audio_detection_for_correlation(self, detection_id: int) -> dict | None:
        async with self.db.execute(
            """SELECT timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id
               FROM audio_detections WHERE id = ? AND is_hidden = 0""",
            (detection_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[4] or "{}")
        except (ValueError, TypeError):
            payload = {}
        return {
            "timestamp": parse_storage_datetime(row[0]),
            "species": row[1],
            "confidence": row[2],
            "sensor_id": row[3],
            "raw_data": payload if isinstance(payload, dict) else {},
            "scientific_name": row[5],
            "source_event_id": row[6],
            "database_id": detection_id,
        }

    async def audio_detection_is_visible(self, detection_id: int) -> bool:
        async with self.db.execute("SELECT is_hidden FROM audio_detections WHERE id = ?", (detection_id,)) as cursor:
            row = await cursor.fetchone()
        return row is not None and not bool(row[0])

    async def resolve_pending_sources(self, limit: int) -> int:
        """Read the source of up to ``limit`` calls stored without it, by the rule ingest uses.

        Only a release from before source tracking stores such a call, after a rollback. They are
        found through a partial index that holds nothing else, so with none to read this is one
        empty seek, and a call already read is never read again.
        """
        async with self.db.execute(
            "SELECT id, sensor_id, raw_data FROM audio_detections WHERE source_resolved = 0 ORDER BY id LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            return 0
        updates = []
        for row_id, sensor_id, raw_data in rows:
            try:
                payload = json.loads(raw_data) if raw_data else None
            except (TypeError, ValueError, RecursionError):
                payload = None
            source = source_of_payload(sensor_id, payload)
            updates.append((source.node, source.source_id, source.name, row_id))
        await self.db.executemany(
            """UPDATE audio_detections
               SET source_node = ?, source_id = ?, source_name = ?, source_resolved = 1
               WHERE id = ? AND source_resolved = 0""",
            updates,
        )
        await self.db.commit()
        return len(rows)

    @asynccontextmanager
    async def one_reading(self) -> AsyncIterator[None]:
        """Every read inside sees the same committed history.

        The sources a view names are read before the calls it counts. Without one reading, a call
        hidden in between could still lend its name to the calls that stay shown.
        """
        if self.db.in_transaction:
            yield
            return
        await self.db.execute("BEGIN")
        try:
            yield
        finally:
            if self.db.in_transaction:
                await self.db.rollback()

    async def load_audio_source_links(self) -> list[AudioSourceLink]:
        return await load_audio_source_links(self.db)

    async def load_audio_source_directory(
        self,
        *,
        minimum_start: datetime | None = None,
        maximum_end: datetime | None = None,
        hidden: bool = False,
        owner_evidence: bool = False,
    ) -> AudioSourceDirectory:
        """Every source the history has heard, keyed by BirdNET-Go's source id on its install."""
        return await load_audio_source_directory(
            self.db,
            minimum_start=minimum_start,
            maximum_end=maximum_end,
            hidden=hidden,
            owner_evidence=owner_evidence,
        )

    async def get_public_audio_for_detections(self, detections: list) -> dict[str, dict]:
        """Bound each page chunk to one primary and eight nearby rows per visual event.

        Mapping/species/window authorization stays in SQL, before pagination and
        ranking, rather than retaining all audio in a broad page-wide time range.
        """
        targets = [d for d in detections if d.audio_species]
        if not targets:
            return {}
        conditions, conditions_params = await public_audio_conditions_sql(self.db, match_species=False)
        result: dict[str, dict] = {}
        for offset in range(0, len(targets), 50):
            chunk = targets[offset : offset + 50]
            params: list = []
            for detection in chunk:
                params.extend(
                    (
                        detection.frigate_event,
                        detection.camera_name,
                        serialize_storage_datetime(detection.detection_time),
                        detection.audio_species,
                        int(detection.audio_confirmed),
                    )
                )
                result[detection.frigate_event] = {"primary": None, "context": []}
            values = ",".join("(?,?,?,?,?)" for _ in chunk)
            query = f"""WITH d(frigate_event,camera_name,detection_time,audio_species,audio_confirmed) AS
                (VALUES {values}), ranked AS (
                SELECT d.frigate_event, d.audio_confirmed, a.timestamp, a.species,
                    a.confidence, a.sensor_id, a.scientific_name,
                    public_audio_species_matches(a.species,a.scientific_name,d.audio_species) AS primary_match,
                    ROW_NUMBER() OVER (PARTITION BY d.frigate_event ORDER BY
                        public_audio_species_matches(a.species,a.scientific_name,d.audio_species) DESC,
                        a.confidence DESC, a.id DESC) AS primary_rank,
                    ROW_NUMBER() OVER (PARTITION BY d.frigate_event ORDER BY
                        ABS(julianday(a.timestamp)-julianday(d.detection_time)),
                        a.confidence DESC, a.id DESC) AS context_rank
                FROM d JOIN audio_detections a ON {conditions})
                SELECT frigate_event,timestamp,species,confidence,sensor_id,scientific_name,
                    primary_match,primary_rank,context_rank,audio_confirmed
                FROM ranked WHERE (primary_match=1 AND primary_rank=1)
                    OR (audio_confirmed=0 AND context_rank<=8)
                ORDER BY frigate_event,context_rank"""
            async with self.db.execute(query, [*params, *conditions_params]) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                item = {
                    "timestamp": row[1],
                    "species": row[2],
                    "confidence": row[3],
                    "sensor_id": row[4],
                    "scientific_name": row[5],
                }
                evidence = result[row[0]]
                if row[6] and row[7] == 1:
                    evidence["primary"] = item
                if not row[9] and row[8] <= 8:
                    evidence["context"].append(item)
        return result

    async def get_audio_contexts_for_detections(
        self,
        detections: list["Detection"],
        mapping: dict[str, str],
        window_seconds: int,
        limit: int = 8,
    ) -> dict[str, tuple[list[dict], int]]:
        """Coalesce owner context windows; retain mapping counts and per-event ranking.

        Rows are streamed in bounded chunks. Mapping is applied before truncation,
        so an unrelated microphone cannot crowd out a camera's relevant calls.
        """
        windows: list[_AudioContextWindow] = []
        delta = timedelta(seconds=window_seconds)
        result: dict[str, tuple[list[dict], int]] = {}
        for detection in detections:
            target = detection.detection_time
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            windows.append(
                _AudioContextWindow(
                    detection.frigate_event,
                    detection.camera_name,
                    target,
                    serialize_storage_datetime(target - delta),
                    serialize_storage_datetime(target + delta),
                )
            )
            result[detection.frigate_event] = ([], 0)
        windows.sort(key=lambda window: window.start)
        intervals: list[tuple[str, str, list[_AudioContextWindow]]] = []
        for window in windows:
            start, end = window.start, window.end
            if intervals and start <= intervals[-1][1]:
                previous_start, previous_end, members = intervals[-1]
                members.append(window)
                intervals[-1] = (previous_start, max(previous_end, end), members)
            else:
                intervals.append((start, end, [window]))

        for start, end, members in intervals:
            query = """SELECT timestamp, species, confidence, sensor_id, scientific_name, raw_data
                       FROM audio_detections
                       WHERE is_hidden = 0 AND timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp DESC"""
            params = [start, end]
            async with self.db.execute(query, params) as cursor:
                while rows := await cursor.fetchmany(512):
                    for window in members:
                        # Match SQLite's existing lexical bounds even for legacy
                        # rows whose timestamp carries an offset suffix.
                        event_rows = [row for row in rows if window.start <= str(row[0]) <= window.end]
                        nearby, suppressed = rank_audio_context(
                            event_rows, window.target, mapping.get(window.camera), limit
                        )
                        previous, previous_suppressed = result[window.event_id]
                        combined = previous + nearby
                        combined.sort(key=lambda item: (abs(item["offset_seconds"]), -item["confidence"]))
                        result[window.event_id] = (combined[:limit], previous_suppressed + suppressed)
        return result

    async def get_audio_context(
        self,
        target_time: datetime,
        window_seconds: int,
        mapping_value: Optional[str],
        limit: int,
        minimum_start: datetime | None = None,
        maximum_end: datetime | None = None,
    ) -> tuple[list[dict], int]:
        """Return audio near ``target_time`` plus how many rows the mapping excluded.

        The count lets a caller distinguish a silent window from one where audio was
        heard on a microphone this camera is not mapped to; both otherwise present as
        an empty list.
        """
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        start_dt = target_time - timedelta(seconds=window_seconds)
        if minimum_start is not None:
            start_dt = max(start_dt, minimum_start)
        end_dt = target_time + timedelta(seconds=window_seconds)
        query = """SELECT timestamp, species, confidence, sensor_id, scientific_name, raw_data
                   FROM audio_detections
                   WHERE is_hidden = 0 AND timestamp >= ? AND timestamp <= ?"""
        params: list = [serialize_storage_datetime(start_dt), serialize_storage_datetime(end_dt)]
        if maximum_end is not None:
            query += " AND timestamp < ?"
            params.append(serialize_storage_datetime(maximum_end))
        query += " ORDER BY timestamp DESC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return rank_audio_context(rows, target_time, mapping_value, limit)

    @staticmethod
    def _source_identity_clause(text: str, directory: AudioSourceDirectory) -> tuple[str, list]:
        """A term finding every call of each source ``text`` names, under any name it has carried.

        Text that names a source by its old name, its new name or its id finds the whole of its
        history, including the calls from before BirdNET-Go reported ids. The directory resolves
        which stored (node, id, name) belong to those sources, the same way the Sources list counts
        them. They reach the database as one JSON list, so the term has the same size however many
        there are, and the database runs no code per call.
        """
        identities = directory.stored_identities_of(directory.keys_matching_text(text))
        if not identities:
            return "0", []
        # A control character never survives cleaning, so it stands for an empty column.
        stored = [["\x01" if part is None else part for part in identity] for identity in identities]
        return (
            """(IFNULL(source_node, char(1)), IFNULL(source_id, char(1)), IFNULL(source_name, char(1))) IN (
                   SELECT json_extract(value, '$[0]'), json_extract(value, '$[1]'), json_extract(value, '$[2]')
                   FROM json_each(?)
               )""",
            [json.dumps(stored)],
        )

    async def _build_audio_history_filter(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        species: Optional[str],
        source: Optional[str],
        min_confidence: Optional[float],
        maximum_end: datetime | None = None,
        scientific_name: Optional[str] = None,
        only_hidden: bool = False,
        search: Optional[str] = None,
        search_include_source: bool = True,
        directory: AudioSourceDirectory | None = None,
    ) -> tuple[str, list]:
        clauses: list[str] = ["is_hidden = 1" if only_hidden else "is_hidden = 0"]
        params: list = []
        if filter_names_a_source(source, search, search_include_source) and directory is None:
            directory = await load_audio_source_directory(
                self.db, maximum_end=maximum_end, hidden=only_hidden, owner_evidence=True
            )

        if start_date is not None:
            clauses.append("timestamp >= ?")
            params.append(serialize_storage_datetime(start_date))
        if end_date is not None:
            clauses.append("timestamp <= ?")
            params.append(serialize_storage_datetime(end_date))
        if maximum_end is not None:
            clauses.append("timestamp < ?")
            params.append(serialize_storage_datetime(maximum_end))
        if species:
            clauses.append("LOWER(species) LIKE ?")
            params.append(f"%{species.strip().casefold()}%")
        if scientific_name and scientific_name.strip():
            # One species exactly. `species` above is a search over the stored common name, so it
            # also finds every name that contains the text, and it never matches a translated name.
            # The comparison is an expression, so idx_audio_detections_scientific is not used: ingest
            # stores BirdNET-Go's ScientificName as sent, untrimmed and in its own case, so a plain
            # `scientific_name = ?` would miss rows. The window's timestamp range bounds the scan.
            clauses.append("LOWER(TRIM(scientific_name)) = ?")
            params.append(scientific_name.strip().casefold())
        if source and directory is not None:
            # As before, the text also matches a call's own stored sensor and payload.
            source_like = f"%{source.strip().casefold()}%"
            named, named_params = self._source_identity_clause(source, directory)
            clauses.append(
                f"(LOWER(COALESCE(sensor_id, '')) LIKE ? OR LOWER(COALESCE(raw_data, '')) LIKE ? OR {named})"
            )
            params.extend([source_like, source_like, *named_params])
        if search and search.strip():
            search_like = f"%{search.strip().casefold()}%"
            if search_include_source and directory is not None:
                named, named_params = self._source_identity_clause(search, directory)
                clauses.append(
                    "(LOWER(species) LIKE ? OR LOWER(COALESCE(scientific_name, '')) LIKE ? "
                    f"OR LOWER(COALESCE(sensor_id, '')) LIKE ? OR LOWER(COALESCE(raw_data, '')) LIKE ? OR {named})"
                )
                params.extend([search_like, search_like, search_like, search_like, *named_params])
            else:
                clauses.append("(LOWER(species) LIKE ? OR LOWER(COALESCE(scientific_name, '')) LIKE ?)")
                params.extend([search_like, search_like])
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(float(min_confidence))

        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    async def get_audio_history(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        species: Optional[str] = None,
        source: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
        maximum_end: datetime | None = None,
        only_hidden: bool = False,
        search: Optional[str] = None,
        search_include_source: bool = True,
        directory: AudioSourceDirectory | None = None,
    ) -> dict:
        """Return persisted BirdNET detections for history browsing.

        A source filter finds every call of the source it names, under any name the source has
        carried (#1111). A guest's caller passes the ``directory`` read from the shared window only.
        """
        where_sql, params = await self._build_audio_history_filter(
            start_date=start_date,
            end_date=end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
            maximum_end=maximum_end,
            only_hidden=only_hidden,
            search=search,
            search_include_source=search_include_source,
            directory=directory,
        )

        async with self.db.execute(f"SELECT COUNT(*) FROM audio_detections{where_sql}", params) as cursor:
            total_row = await cursor.fetchone()
        total = int(total_row[0] or 0) if total_row else 0

        query = f"""SELECT id, timestamp, species, confidence, sensor_id, scientific_name, raw_data
                    FROM audio_detections
                    {where_sql}
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ? OFFSET ?"""
        async with self.db.execute(query, [*params, limit, offset]) as cursor:
            rows = await cursor.fetchall()

        items: list[dict] = []
        for row in rows:
            raw_data = row[6]
            birdnet_id: int | None = None
            if raw_data:
                try:
                    payload = json.loads(raw_data)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    birdnet_id = extract_birdnet_id(payload)

            items.append(
                {
                    "id": row[0],
                    "timestamp": serialize_api_datetime(parse_storage_datetime(row[1])),
                    "species": row[2],
                    "confidence": row[3],
                    "sensor_id": row[4],
                    "source_name": extract_birdnet_source_name(row[4], raw_data),
                    "scientific_name": row[5],
                    "birdnet_id": birdnet_id,
                    "_mapping_keys": extract_audio_mapping_keys(row[4], raw_data),
                }
            )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_audio_history_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        species: Optional[str] = None,
        source: Optional[str] = None,
        min_confidence: Optional[float] = None,
        maximum_end: datetime | None = None,
        only_hidden: bool = False,
        search: Optional[str] = None,
        search_include_source: bool = True,
        calendar_zone: tzinfo = timezone.utc,
        directory: AudioSourceDirectory | None = None,
    ) -> dict:
        """Return rollups over persisted BirdNET detections, with calls per day on ``calendar_zone``'s calendar.

        Sources are counted by BirdNET-Go's source id, so a renamed source is one entry under its
        latest name with all of its calls (#1111). A guest's caller passes the ``directory`` read
        from the shared window only.
        """
        if directory is None:
            directory = await load_audio_source_directory(
                self.db, maximum_end=maximum_end, hidden=only_hidden, owner_evidence=True
            )
        where_sql, params = await self._build_audio_history_filter(
            start_date=start_date,
            end_date=end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
            maximum_end=maximum_end,
            only_hidden=only_hidden,
            search=search,
            search_include_source=search_include_source,
            directory=directory,
        )

        async with self.db.execute(
            f"""SELECT COUNT(*), COUNT(DISTINCT COALESCE(NULLIF(scientific_name, ''), species))
                FROM audio_detections{where_sql}""",
            params,
        ) as cursor:
            totals = await cursor.fetchone()

        async with self.db.execute(
            f"""SELECT species, scientific_name, COUNT(*) AS count, AVG(confidence), MAX(confidence),
                       MIN(timestamp), MAX(timestamp)
                FROM audio_detections
                {where_sql}
                GROUP BY COALESCE(NULLIF(scientific_name, ''), species), species, scientific_name
                ORDER BY count DESC, MAX(timestamp) DESC
                LIMIT 20""",
            params,
        ) as cursor:
            top_species_rows = await cursor.fetchall()

        async with self.db.execute(
            f"""SELECT CAST(strftime('%H', timestamp) AS INTEGER), COUNT(*)
                FROM audio_detections
                {where_sql}
                GROUP BY CAST(strftime('%H', timestamp) AS INTEGER)
                ORDER BY CAST(strftime('%H', timestamp) AS INTEGER) ASC""",
            params,
        ) as cursor:
            hourly_rows = await cursor.fetchall()

        source_totals: dict[SourceKey, dict] = {}
        resolved: dict[tuple, tuple[StoredSource, SourceKey]] = {}
        # Days are the viewer's, not UTC's: SQLite knows no zones, so each call's day is read here, in
        # the same pass that totals the sources, which also stays exact for half-hour offsets and DST.
        daily_totals: dict[date, int] = {}
        async with self.db.execute(
            f"""SELECT timestamp, source_node, source_id, source_name
                FROM audio_detections
                {where_sql}
                ORDER BY timestamp DESC""",
            params,
        ) as cursor:
            while source_rows := await cursor.fetchmany(512):
                for row in source_rows:
                    day = _calendar_day(row[0], calendar_zone)
                    if day is not None:
                        daily_totals[day] = daily_totals.get(day, 0) + 1
                    stored = (row[1], row[2], row[3])
                    # Calls repeat a handful of sources: each stored identity is resolved once.
                    if stored not in resolved:
                        source = read_stored_source(*stored)
                        resolved[stored] = (source, directory.key_for(source.node, source.source_id, source.name))
                    source, source_key = resolved[stored]
                    if source_key not in source_totals:
                        source_totals[source_key] = {
                            "source_name": directory.display_name(source_key)
                            or source.name
                            or source.source_id
                            or "Unknown source",
                            "source_id": directory.source_id(source_key) or source.source_id,
                            "source_node": directory.source_node(source_key),
                            "count": 0,
                            "last_heard": serialize_api_datetime(parse_storage_datetime(row[0])),
                        }
                    source_totals[source_key]["count"] += 1

        top_species = [
            {
                "species": row[0],
                "scientific_name": row[1],
                "count": int(row[2] or 0),
                "avg_confidence": float(row[3] or 0),
                "max_confidence": float(row[4] or 0),
                "first_heard": serialize_api_datetime(parse_storage_datetime(row[5])) if row[5] else None,
                "last_heard": serialize_api_datetime(parse_storage_datetime(row[6])) if row[6] else None,
            }
            for row in top_species_rows
        ]

        sources = sorted(
            source_totals.values(),
            key=lambda item: (
                -int(item["count"]),
                str(item["source_name"]).casefold(),
                str(item["source_id"] or ""),
                str(item["source_node"] or ""),
            ),
        )

        return {
            "total": int(totals[0] or 0) if totals else 0,
            "species_count": int(totals[1] or 0) if totals else 0,
            "source_count": len(sources),
            "top_species": top_species,
            "daily_counts": [{"date": day.isoformat(), "count": count} for day, count in sorted(daily_totals.items())],
            "hourly_counts": [{"hour": int(row[0] or 0), "count": int(row[1] or 0)} for row in hourly_rows],
            "sources": sources,
        }

    async def get_audio_activity_utc_quarter_hour_counts(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        species: Optional[str] = None,
        source: Optional[str] = None,
        min_confidence: Optional[float] = None,
        maximum_end: datetime | None = None,
        scientific_name: Optional[str] = None,
        only_hidden: bool = False,
        search: Optional[str] = None,
        search_include_source: bool = True,
        directory: AudioSourceDirectory | None = None,
    ) -> list[tuple[datetime, int]]:
        """Visible calls per UTC quarter hour, under the summary's filters, optionally for one species exactly.

        Quarter hours, not hours: every zone's offset is a whole number of quarter hours, so each bucket
        lies inside one local hour. A UTC hour would not in India (UTC+5:30), where 18:40 UTC on Tuesday
        is 00:10 on Wednesday but its UTC hour starts at 23:30 on Tuesday.
        """
        where_sql, params = await self._build_audio_history_filter(
            start_date=start_date,
            end_date=end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
            maximum_end=maximum_end,
            scientific_name=scientific_name,
            only_hidden=only_hidden,
            search=search,
            search_include_source=search_include_source,
            directory=directory,
        )
        async with self.db.execute(
            f"""SELECT strftime('%Y-%m-%d %H:', timestamp)
                       || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 15) * 15)
                       || ':00' AS bucket_start,
                       COUNT(*)
                FROM audio_detections
                {where_sql}
                GROUP BY bucket_start
                ORDER BY bucket_start ASC""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [(datetime.fromisoformat(row[0]), int(row[1])) for row in rows if row[0] and int(row[1] or 0) > 0]

    async def pending_audio_scientific_names(self) -> list[tuple[str, int]]:
        """Distinct names on audio rows that carry no identity yet, with row counts."""
        async with self.db.execute(
            """
            SELECT scientific_name, COUNT(*) FROM audio_detections
            WHERE species_id IS NULL AND scientific_name IS NOT NULL AND TRIM(scientific_name) != ''
            GROUP BY scientific_name
            """
        ) as cursor:
            rows = await cursor.fetchall()
        return [(str(name), int(count or 0)) for name, count in rows]

    async def assign_audio_species_ids(
        self, pending: list[tuple[str, int]], identities: dict[str, Optional[int]]
    ) -> dict[str, int]:
        """Write resolved identities onto audio rows; names with no identity are counted and left."""
        identified = 0
        unresolved = 0
        for scientific_name, row_count in pending:
            species_id = identities.get(scientific_name)
            if species_id is None:
                unresolved += int(row_count or 0)
                continue
            await self.db.execute(
                """
                UPDATE audio_detections SET species_id = ?
                WHERE species_id IS NULL AND scientific_name = ?
                """,
                (species_id, scientific_name),
            )
            identified += await self._last_statement_changes()

        if identified:
            await self.db.commit()
        return {"identified": identified, "unresolved": unresolved, "names_seen": len(pending)}

    async def backfill_audio_species_ids(self, *, resolver: Any = None, batch_size: int = 500) -> dict[str, int]:
        """Give existing audio detections the identity new ones will carry.

        Required rather than optional: grouping audio by identity while older
        rows have none would split a species at the upgrade boundary, which is
        the exact failure this phase removes.

        Conservative and idempotent. Only rows with no identity are considered,
        a name is resolved once rather than per row, and anything the catalogue
        cannot pin to exactly one species is counted and left alone. Resolves
        on the caller's connection; the startup backfill resolves first and
        calls :meth:`assign_audio_species_ids` so the pool is not held meanwhile.
        """
        from app.services.audio_identity import resolve_audio_identity

        pending = await self.pending_audio_scientific_names()
        identities = {name: resolve_audio_identity(name, resolver=resolver) for name, _count in pending}
        return await self.assign_audio_species_ids(pending, identities)

    async def get_audio_history_start(
        self, minimum_start: datetime | None = None, maximum_end: datetime | None = None
    ) -> datetime | None:
        """When BirdNET-Go's stored history begins; it can start long after the camera's."""
        query = "SELECT MIN(timestamp) FROM audio_detections"
        params: list = []
        if minimum_start is not None:
            query += " WHERE is_hidden = 0 AND timestamp >= ?"
            params.append(serialize_storage_datetime(minimum_start))
        if maximum_end is not None:
            query += " AND timestamp < ?" if minimum_start is not None else " WHERE is_hidden = 0 AND timestamp < ?"
            params.append(serialize_storage_datetime(maximum_end))
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return parse_storage_datetime(row[0]) if row and row[0] else None

    async def public_birdnet_media_visible(
        self, birdnet_id: int, minimum_start: datetime, maximum_end: datetime | None = None
    ) -> bool:
        """Resolve the upstream identity, never the unrelated local row id.

        Resolve identity across retained rows before applying sharing bounds.
        A hidden tombstone or conflicting source/time cannot authorize a different
        numeric ID at the single upstream URL, even outside the public window.
        """
        if not 0 < birdnet_id <= 2**63 - 1:
            return False
        payload = "CASE WHEN json_valid(raw_data) THEN raw_data ELSE '{}' END"
        predicate = " OR ".join(
            f"CAST(json_extract({payload}, '$.{key}') AS INTEGER) = ?" for key in ("detectionId", "detection_id", "id")
        )
        async with self.db.execute(
            f"SELECT raw_data, is_hidden, sensor_id, timestamp FROM audio_detections WHERE {predicate}",
            (birdnet_id, birdnet_id, birdnet_id),
        ) as cursor:
            identity: tuple[str, str] | None = None
            lower = serialize_storage_datetime(minimum_start)
            upper = serialize_storage_datetime(maximum_end) if maximum_end is not None else None
            async for row in cursor:
                try:
                    data = json.loads(row[0])
                    resolved_id = extract_birdnet_id(data)
                except (ValueError, TypeError):
                    return False
                if resolved_id != birdnet_id:
                    continue
                source = extract_birdnet_source_name(row[2], row[0])
                source_fields = data.get("Source")
                source_fields = source_fields if isinstance(source_fields, dict) else {}
                # Stable device IDs distinguish equal display names and allow a
                # device to be renamed without making its media ambiguous.
                source_ids = [
                    value
                    for value in (data.get("sourceId"), data.get("src"), source_fields.get("id"))
                    if value is not None
                ]
                if any(not isinstance(value, str) or not value.strip() for value in source_ids):
                    return False
                if source_ids:
                    normalized_ids = {value.strip().casefold() for value in source_ids}
                    if len(normalized_ids) != 1:
                        return False
                    source_key = "id:" + normalized_ids.pop()
                elif source:
                    source_key = "name:" + source.strip().casefold()
                else:
                    return False
                if row[1]:
                    return False
                try:
                    stamp = serialize_storage_datetime(datetime.fromisoformat(row[3]))
                except (ValueError, TypeError):
                    return False
                if stamp < lower or (upper is not None and stamp >= upper):
                    return False
                candidate = (source_key, stamp)
                if identity is not None and identity != candidate:
                    return False
                identity = candidate
        return identity is not None

    async def get_audio_species_counts(
        self,
        window_start: datetime,
        window_end: datetime,
        prev_start: datetime,
        prev_end: datetime,
    ) -> list[dict]:
        """Heard-count rollups per species over a rolling window and the prior window.

        Mirrors ``get_species_leaderboard_window`` but over ``audio_detections`` so the
        Species leaderboard can show BirdNET-Go "heard" counts alongside camera "seen"
        counts. Rows are grouped by scientific name when available, else the species
        label, matching how the audio summary de-duplicates species. Timestamps are
        formatted the same way they are stored (``isoformat(sep=' ')``) so the string
        comparison lines up with the ``idx_audio_detections_time`` index.
        """

        ws, we = serialize_storage_datetime(window_start), serialize_storage_datetime(window_end)
        ps, pe = serialize_storage_datetime(prev_start), serialize_storage_datetime(prev_end)

        query = """
            SELECT
                -- Identity first, so one bird reported under two names counts
                -- once; the text keys stay underneath for rows the catalogue
                -- cannot identify. Namespaced for the same reason detections
                -- are: ids from different databases share number ranges.
                COALESCE(
                    'species:' || CAST(species_id AS TEXT),
                    'name:' || NULLIF(LOWER(scientific_name), ''),
                    'label:' || LOWER(species)
                ) AS unified_id,
                MAX(species) AS species,
                MAX(scientific_name) AS scientific_name,
                SUM(CASE WHEN timestamp >= ? AND timestamp < ? THEN 1 ELSE 0 END) AS window_count,
                SUM(CASE WHEN timestamp >= ? AND timestamp < ? THEN 1 ELSE 0 END) AS prev_count,
                AVG(CASE WHEN timestamp >= ? AND timestamp < ? THEN confidence ELSE NULL END) AS window_avg_confidence,
                MAX(CASE WHEN timestamp >= ? AND timestamp < ? THEN timestamp ELSE NULL END) AS window_last_heard
            FROM audio_detections
            WHERE is_hidden = 0 AND timestamp >= ? AND timestamp < ?
            GROUP BY unified_id
        """
        params = (ws, we, ps, pe, ws, we, ws, we, ps, we)
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        results: list[dict] = []
        for row in rows:
            window_count = int(row[3] or 0)
            prev_count = int(row[4] or 0)
            if window_count == 0 and prev_count == 0:
                continue
            results.append(
                {
                    "species": row[1],
                    "scientific_name": row[2],
                    "window_count": window_count,
                    "prev_count": prev_count,
                    "window_avg_confidence": float(row[5] or 0.0),
                    "window_last_heard": parse_storage_datetime(row[6]) if row[6] else None,
                }
            )
        return results

    async def heard_by_species(
        self, *, start: datetime | None = None, end: datetime | None = None
    ) -> dict[int, tuple[int, str]]:
        """Visible BirdNET-Go detections per catalogue species, with the newest one's time."""
        clauses, params = ["is_hidden = 0", "species_id IS NOT NULL"], []
        if start is not None:
            clauses.append("timestamp >= ?")
            params.append(serialize_storage_datetime(start))
        if end is not None:
            clauses.append("timestamp < ?")
            params.append(serialize_storage_datetime(end))
        async with self.db.execute(
            f"SELECT species_id, COUNT(*), MAX(timestamp) FROM audio_detections"
            f" WHERE {' AND '.join(clauses)} GROUP BY species_id",
            params,
        ) as cursor:
            return {int(species_id): (int(count), str(last)) for species_id, count, last in await cursor.fetchall()}

    async def _last_statement_changes(self) -> int:
        """Return rows changed by the most recent write statement on this connection."""
        cursor = await self.db.execute("SELECT changes()")
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row and row[0] is not None else 0
