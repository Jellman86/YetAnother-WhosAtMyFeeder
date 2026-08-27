from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, date, timezone
import aiosqlite
import asyncio
import json
import re
import unicodedata
import structlog
from app.utils.frigate import normalize_sub_label
from app.utils.canonical_species import (
    hidden_species_exact_labels,
    hidden_species_substrings,
    should_hide_species_label,
)
from app.utils.api_datetime import serialize_api_datetime, serialize_storage_datetime, utc_naive_now

log = structlog.get_logger()

DETECTION_SELECT_COLUMNS = """d.id, d.detection_time, d.detection_index, d.score, d.display_name, d.category_name, d.frigate_event, d.camera_name,
                      d.is_hidden, d.frigate_score, d.sub_label, d.audio_confirmed, d.audio_species, d.audio_score,
                      d.temperature, d.weather_condition, d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                      d.weather_precipitation, d.weather_rain, d.weather_snowfall, d.scientific_name, d.common_name, d.taxa_id,
                      d.video_classification_score, d.video_classification_label, d.video_classification_index,
                      d.video_classification_timestamp, d.video_classification_status, d.video_classification_error,
                      d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                      CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                      d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id, d.video_result_blocked,
                      d.frigate_status, d.frigate_missing_since, d.frigate_last_checked_at, d.frigate_last_error,
                      d.video_classification_input_source, d.video_classification_diagnostics,
                      d.species_id, d.model_artifact_id, d.model_output_index"""


@dataclass
class Detection:
    detection_time: datetime
    detection_index: int
    score: float
    display_name: str
    category_name: str
    frigate_event: str
    camera_name: str
    id: Optional[int] = None
    is_hidden: bool = False
    is_favorite: bool = False
    frigate_score: Optional[float] = None
    sub_label: Optional[str] = None
    manual_tagged: bool = False
    # Audio correlation fields
    audio_confirmed: bool = False
    audio_species: Optional[str] = None
    audio_score: Optional[float] = None
    # Weather fields
    temperature: Optional[float] = None
    weather_condition: Optional[str] = None
    weather_cloud_cover: Optional[float] = None
    weather_wind_speed: Optional[float] = None
    weather_wind_direction: Optional[float] = None
    weather_precipitation: Optional[float] = None
    weather_rain: Optional[float] = None
    weather_snowfall: Optional[float] = None
    # Taxonomy fields
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    taxa_id: Optional[int] = None
    # Canonical catalogue identity and artifact provenance (Phase 3)
    species_id: Optional[int] = None
    model_artifact_id: Optional[int] = None
    model_output_index: Optional[int] = None
    notified_at: Optional[datetime] = None
    frigate_status: str = "present"
    frigate_missing_since: Optional[datetime] = None
    frigate_last_checked_at: Optional[datetime] = None
    frigate_last_error: Optional[str] = None
    # Video classification fields
    video_classification_score: Optional[float] = None
    video_classification_label: Optional[str] = None
    video_classification_index: Optional[int] = None
    video_classification_timestamp: Optional[datetime] = None
    video_classification_status: Optional[str] = None
    video_classification_error: Optional[str] = None
    video_classification_provider: Optional[str] = None
    video_classification_backend: Optional[str] = None
    video_classification_model_id: Optional[str] = None
    video_classification_input_source: Optional[str] = None
    video_classification_diagnostics: Optional[dict] = None
    # AI naturalist analysis fields
    ai_analysis: Optional[str] = None
    ai_analysis_timestamp: Optional[datetime] = None
    # Blocked label flag
    video_result_blocked: bool = False


@dataclass
class TimezoneRepairRow:
    id: int
    detection_time: datetime
    frigate_event: str
    camera_name: str
    display_name: str


def _parse_datetime(value: object) -> datetime:
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


def _normalize_species_lookup_name(value: str | None) -> str:
    """Normalize species names for accent-insensitive fallback matching."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[_\-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_mapping_key(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().casefold()


def _parse_mapping_filter_values(mapping_value: str | None) -> tuple[bool, set[str]]:
    if not isinstance(mapping_value, str):
        return False, set()
    tokens = {_normalize_mapping_key(token) for token in re.split(r"[,\n;|]+", mapping_value)}
    tokens.discard("")
    if "*" in tokens:
        return True, set()
    return False, tokens


def _extract_audio_mapping_keys(sensor_id: str | None, raw_data: str | None) -> set[str]:
    keys: set[str] = set()
    normalized_sensor = _normalize_mapping_key(sensor_id)
    if normalized_sensor:
        keys.add(normalized_sensor)

    if not raw_data:
        return keys

    try:
        payload = json.loads(raw_data)
    except Exception:
        return keys

    if not isinstance(payload, dict):
        return keys

    source = payload.get("Source")
    source = source if isinstance(source, dict) else {}
    for candidate in (
        payload.get("nm"),
        payload.get("sourceName"),
        source.get("displayName"),
        payload.get("src"),
        payload.get("sourceId"),
        source.get("id"),
        payload.get("id"),
        payload.get("sensor_id"),
    ):
        normalized = _normalize_mapping_key(candidate)
        if normalized:
            keys.add(normalized)
    return keys


def _extract_birdnet_source_name(sensor_id: str | None, raw_data: str | None) -> str | None:
    """Return the best human-readable BirdNET source label for history views."""
    if raw_data:
        try:
            payload = json.loads(raw_data)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            source = payload.get("Source")
            source = source if isinstance(source, dict) else {}
            for candidate in (
                payload.get("nm"),
                payload.get("sourceName"),
                source.get("displayName"),
                sensor_id,
                payload.get("sourceId"),
                payload.get("src"),
                source.get("id"),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

    if isinstance(sensor_id, str) and sensor_id.strip():
        return sensor_id.strip()
    return None


def match_audio_history_visual_events(
    audio_items: list[dict],
    candidates: list[dict],
    *,
    window_seconds: int,
    camera_audio_mapping: dict[str, str],
) -> dict[int, str]:
    """Conservatively match audio rows to completed automatic video results."""
    resolved: dict[int, str] = {}
    bounded_window = max(0, int(window_seconds))

    for audio_item in audio_items:
        scientific_name = _normalize_species_lookup_name(audio_item.get("scientific_name"))
        audio_id = audio_item.get("id")
        if not scientific_name or not isinstance(audio_id, int):
            continue
        audio_time = _parse_datetime(audio_item.get("timestamp"))
        audio_time = (
            audio_time.replace(tzinfo=timezone.utc)
            if audio_time.tzinfo is None
            else audio_time.astimezone(timezone.utc)
        )
        audio_keys = {
            normalized
            for value in audio_item.get("_mapping_keys", set())
            if (normalized := _normalize_mapping_key(value))
        }

        ranked: list[tuple[float, float, float, str]] = []
        for candidate in candidates:
            if _normalize_species_lookup_name(candidate.get("video_classification_label")) != scientific_name:
                continue
            candidate_time = _parse_datetime(candidate.get("detection_time"))
            candidate_time = (
                candidate_time.replace(tzinfo=timezone.utc)
                if candidate_time.tzinfo is None
                else candidate_time.astimezone(timezone.utc)
            )
            delta = abs((candidate_time - audio_time).total_seconds())
            if delta > bounded_window:
                continue

            mapping_value = camera_audio_mapping.get(str(candidate.get("camera_name") or ""))
            wildcard_mapping, mapping_keys = _parse_mapping_filter_values(mapping_value)
            if not wildcard_mapping and not audio_keys.intersection(mapping_keys):
                continue

            event_id = str(candidate.get("frigate_event") or "").strip()
            if not event_id:
                continue
            score = float(candidate.get("video_classification_score") or 0.0)
            ranked.append((delta, -score, -candidate_time.timestamp(), event_id))

        if ranked:
            ranked.sort()
            resolved[audio_id] = ranked[0][3]

    return resolved


def _row_to_detection(row: aiosqlite.Row) -> Detection:
    """Convert a database row to a Detection object."""
    d = Detection(
        id=row[0],
        detection_time=_parse_datetime(row[1]),
        detection_index=row[2],
        score=row[3],
        display_name=row[4],
        category_name=row[5],
        frigate_event=row[6],
        camera_name=row[7],
        is_hidden=bool(row[8]) if len(row) > 8 else False,
        frigate_score=row[9] if len(row) > 9 else None,
        sub_label=normalize_sub_label(row[10]) if len(row) > 10 else None,
        audio_confirmed=bool(row[11]) if len(row) > 11 else False,
        audio_species=row[12] if len(row) > 12 else None,
        audio_score=row[13] if len(row) > 13 else None,
        temperature=row[14] if len(row) > 14 else None,
        weather_condition=row[15] if len(row) > 15 else None,
        weather_cloud_cover=row[16] if len(row) > 16 else None,
        weather_wind_speed=row[17] if len(row) > 17 else None,
        weather_wind_direction=row[18] if len(row) > 18 else None,
        weather_precipitation=row[19] if len(row) > 19 else None,
        weather_rain=row[20] if len(row) > 20 else None,
        weather_snowfall=row[21] if len(row) > 21 else None,
        scientific_name=row[22] if len(row) > 22 else None,
        common_name=row[23] if len(row) > 23 else None,
        taxa_id=row[24] if len(row) > 24 else None,
    )

    # Optional video fields (might not be in row if using older query)
    if len(row) > 25:
        d.video_classification_score = row[25]
        d.video_classification_label = row[26]
        d.video_classification_index = row[27]
        d.video_classification_timestamp = _parse_datetime(row[28]) if row[28] else None
        d.video_classification_status = row[29]
        d.video_classification_error = row[30] if len(row) > 30 else None

    # Optional AI analysis fields
    if len(row) > 31:
        d.ai_analysis = row[31]
        d.ai_analysis_timestamp = _parse_datetime(row[32]) if row[32] else None

    if len(row) > 33:
        d.manual_tagged = bool(row[33])

    if len(row) > 34:
        d.notified_at = _parse_datetime(row[34]) if row[34] else None

    if len(row) > 35:
        d.is_favorite = bool(row[35])

    if len(row) > 36:
        d.video_classification_provider = row[36]

    if len(row) > 37:
        d.video_classification_backend = row[37]

    if len(row) > 38:
        d.video_classification_model_id = row[38]

    if len(row) > 39:
        d.video_result_blocked = bool(row[39])

    if len(row) > 40:
        d.frigate_status = row[40] or "present"
    if len(row) > 41:
        d.frigate_missing_since = _parse_datetime(row[41]) if row[41] else None
    if len(row) > 42:
        d.frigate_last_checked_at = _parse_datetime(row[42]) if row[42] else None
    if len(row) > 43:
        d.frigate_last_error = row[43]
    if len(row) > 44:
        d.video_classification_input_source = row[44]
    if len(row) > 45 and row[45]:
        try:
            parsed_diagnostics = json.loads(row[45])
            d.video_classification_diagnostics = parsed_diagnostics if isinstance(parsed_diagnostics, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            d.video_classification_diagnostics = None

    if len(row) > 48:
        d.species_id = row[46]
        d.model_artifact_id = row[47]
        d.model_output_index = row[48]

    return d


class DetectionRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self._table_exists_cache: dict[str, bool] = {}

    async def replace_snapshot_candidates(
        self,
        frigate_event: str,
        candidates: list[dict],
    ) -> None:
        if not await self._table_exists("snapshot_candidates"):
            return
        await self.db.execute(
            "DELETE FROM snapshot_candidates WHERE frigate_event = ?",
            (frigate_event,),
        )
        for candidate in candidates:
            crop_box = candidate.get("crop_box")
            crop_box_json = json.dumps(crop_box) if crop_box is not None else None
            await self.db.execute(
                """
                INSERT INTO snapshot_candidates (
                    frigate_event,
                    candidate_id,
                    frame_index,
                    frame_offset_seconds,
                    source_mode,
                    clip_variant,
                    crop_box_json,
                    crop_confidence,
                    crop_strategy,
                    classifier_label,
                    classifier_score,
                    ranking_score,
                    selected,
                    thumbnail_ref,
                    image_ref,
                    snapshot_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frigate_event,
                    str(candidate.get("candidate_id") or ""),
                    int(candidate.get("frame_index") or 0),
                    candidate.get("frame_offset_seconds"),
                    str(candidate.get("source_mode") or "full_frame"),
                    str(candidate.get("clip_variant") or "event"),
                    crop_box_json,
                    candidate.get("crop_confidence"),
                    candidate.get("crop_strategy"),
                    candidate.get("classifier_label"),
                    candidate.get("classifier_score"),
                    float(candidate.get("ranking_score") or 0.0),
                    1 if bool(candidate.get("selected")) else 0,
                    candidate.get("thumbnail_ref"),
                    candidate.get("image_ref"),
                    candidate.get("snapshot_source"),
                ),
            )
        await self.db.commit()

    async def list_snapshot_candidates(self, frigate_event: str) -> list[dict]:
        if not await self._table_exists("snapshot_candidates"):
            return []
        async with self.db.execute(
            """
            SELECT
                candidate_id,
                frame_index,
                frame_offset_seconds,
                source_mode,
                clip_variant,
                crop_box_json,
                crop_confidence,
                crop_strategy,
                classifier_label,
                classifier_score,
                ranking_score,
                selected,
                thumbnail_ref,
                image_ref,
                snapshot_source
            FROM snapshot_candidates
            WHERE frigate_event = ?
            ORDER BY ranking_score DESC, frame_index ASC, candidate_id ASC
            """,
            (frigate_event,),
        ) as cursor:
            rows = await cursor.fetchall()

        result: list[dict] = []
        for row in rows:
            crop_box = None
            if row[5]:
                try:
                    crop_box = json.loads(row[5])
                except Exception:
                    crop_box = None
            result.append(
                {
                    "candidate_id": row[0],
                    "frame_index": row[1],
                    "frame_offset_seconds": row[2],
                    "source_mode": row[3],
                    "clip_variant": row[4],
                    "crop_box": crop_box,
                    "crop_confidence": row[6],
                    "crop_strategy": row[7],
                    "classifier_label": row[8],
                    "classifier_score": row[9],
                    "ranking_score": row[10],
                    "selected": bool(row[11]),
                    "thumbnail_ref": row[12],
                    "image_ref": row[13],
                    "snapshot_source": row[14],
                }
            )
        return result

    async def get_selected_snapshot_candidate(self, frigate_event: str) -> Optional[dict]:
        candidates = await self.list_snapshot_candidates(frigate_event)
        for candidate in candidates:
            if candidate.get("selected"):
                return candidate
        return candidates[0] if candidates else None

    async def mark_selected_snapshot_candidate(
        self,
        frigate_event: str,
        candidate_id: Optional[str],
    ) -> None:
        """Mark the currently applied snapshot candidate for an event.

        Passing None clears selection, which is used when reverting to the
        original Frigate snapshot.
        """
        if not await self._table_exists("snapshot_candidates"):
            return
        await self.db.execute(
            """
            UPDATE snapshot_candidates
            SET selected = 0, updated_at = CURRENT_TIMESTAMP
            WHERE frigate_event = ?
            """,
            (frigate_event,),
        )
        if candidate_id:
            await self.db.execute(
                """
                UPDATE snapshot_candidates
                SET selected = 1, updated_at = CURRENT_TIMESTAMP
                WHERE frigate_event = ? AND candidate_id = ?
                """,
                (frigate_event, candidate_id),
            )
        await self.db.commit()

    async def replace_video_top_frames(
        self,
        frigate_event: str,
        frames: list[dict],
    ) -> None:
        if not await self._table_exists("video_classification_top_frames"):
            return
        await self.db.execute(
            "DELETE FROM video_classification_top_frames WHERE frigate_event = ?",
            (frigate_event,),
        )
        for frame in frames:
            await self.db.execute(
                """
                INSERT INTO video_classification_top_frames (
                    frigate_event,
                    clip_variant,
                    frame_index,
                    frame_offset_seconds,
                    frame_score,
                    top_label,
                    top_score,
                    rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frigate_event,
                    str(frame.get("clip_variant") or "event"),
                    int(frame.get("frame_index") or 0),
                    frame.get("frame_offset_seconds"),
                    float(frame.get("frame_score") or 0.0),
                    frame.get("top_label"),
                    frame.get("top_score"),
                    int(frame.get("rank") or 0),
                ),
            )
        await self.db.commit()

    async def list_video_top_frames(self, frigate_event: str) -> list[dict]:
        if not await self._table_exists("video_classification_top_frames"):
            return []
        async with self.db.execute(
            """
            SELECT
                clip_variant,
                frame_index,
                frame_offset_seconds,
                frame_score,
                top_label,
                top_score,
                rank
            FROM video_classification_top_frames
            WHERE frigate_event = ?
            ORDER BY rank ASC, frame_index ASC
            """,
            (frigate_event,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "clip_variant": row[0],
                "frame_index": row[1],
                "frame_offset_seconds": row[2],
                "frame_score": row[3],
                "top_label": row[4],
                "top_score": row[5],
                "rank": row[6],
            }
            for row in rows
        ]

    @staticmethod
    def _canonical_key_sql(
        *,
        detection_alias: str = "d",
        taxonomy_alias: str | None = "tc",
    ) -> str:
        """The key that decides whether two detections are the same bird.

        Catalogue identity first, then the older text keys for rows the
        catalogue cannot identify, so nothing that groups today stops grouping.

        A scientific name is not stable. When a taxon is split, lumped or
        synonymised, `Parus caeruleus` and `Cyanistes caeruleus` become two
        different birds to anything keying on the text, and history divides with
        nothing to warn anyone. The catalogue's opaque `species_id` does not
        move when a name does.

        Each source is namespaced because `species_id` and `taxa_id` are
        integers from different databases with overlapping ranges: on a live
        install `taxa_id` spans 487 to 1,289,423 and `species_id` spans 1,391 to
        17,542. Cast bare into one key space they would merge unrelated species.
        `'species:' || NULL` is NULL, so an absent id still falls through.
        """
        taxon_id = (
            f"COALESCE({detection_alias}.taxa_id, {taxonomy_alias}.taxa_id)"
            if taxonomy_alias
            else f"{detection_alias}.taxa_id"
        )
        scientific = (
            f"COALESCE({detection_alias}.scientific_name, {taxonomy_alias}.scientific_name)"
            if taxonomy_alias
            else f"{detection_alias}.scientific_name"
        )
        return (
            f"COALESCE("
            f"'species:' || CAST({detection_alias}.species_id AS TEXT), "
            f"'taxon:' || CAST({taxon_id} AS TEXT), "
            f"'name:' || LOWER({scientific}), "
            f"'label:' || LOWER({detection_alias}.display_name))"
        )

    @staticmethod
    def _taxonomy_join_sql(*, detection_alias: str = "d", taxonomy_alias: str = "tc") -> str:
        return (
            f"LEFT JOIN taxonomy_cache {taxonomy_alias} "
            f"ON ("
            f"({detection_alias}.scientific_name IS NOT NULL AND LOWER({taxonomy_alias}.scientific_name) = LOWER({detection_alias}.scientific_name)) "
            f"OR ({detection_alias}.scientific_name IS NULL AND ("
            f"LOWER({taxonomy_alias}.scientific_name) = LOWER({detection_alias}.display_name) "
            f"OR LOWER({taxonomy_alias}.common_name) = LOWER({detection_alias}.display_name)"
            f")))"
        )

    async def _build_canonical_species_condition(
        self,
        *,
        detection_alias: str,
        species_name: str,
        has_taxonomy_cache: bool,
    ) -> tuple[str, list]:
        if should_hide_species_label(species_name):
            exact_labels = [str(label).strip().lower() for label in hidden_species_exact_labels() if str(label).strip()]
            exact_labels = list(dict.fromkeys(exact_labels))
            fragments = [
                str(fragment).strip().lower() for fragment in hidden_species_substrings() if str(fragment).strip()
            ]
            columns = (
                f"LOWER({detection_alias}.display_name)",
                f"LOWER({detection_alias}.category_name)",
                f"LOWER(COALESCE({detection_alias}.scientific_name, ''))",
                f"LOWER(COALESCE({detection_alias}.common_name, ''))",
            )
            clauses: list[str] = []
            params: list = []

            if exact_labels:
                placeholders = ",".join(["?"] * len(exact_labels))
                for column in columns:
                    clauses.append(f"{column} IN ({placeholders})")
                    params.extend(exact_labels)

            for fragment in fragments:
                pattern = f"%{fragment}%"
                for column in columns:
                    clauses.append(f"{column} LIKE ?")
                    params.append(pattern)

            if clauses:
                return "(" + " OR ".join(clauses) + ")", params

        alias_info = await self.resolve_species_aliases(species_name)
        clauses: list[str] = []
        params: list = []

        taxa_id = alias_info.get("taxa_id")
        if taxa_id is not None:
            if has_taxonomy_cache:
                clauses.append(f"COALESCE({detection_alias}.taxa_id, tc_filter.taxa_id) = ?")
            else:
                clauses.append(f"{detection_alias}.taxa_id = ?")
            params.append(taxa_id)

        scientific_name = alias_info.get("scientific_name")
        if scientific_name:
            if has_taxonomy_cache:
                clauses.append(
                    f"LOWER(COALESCE({detection_alias}.scientific_name, tc_filter.scientific_name)) = LOWER(?)"
                )
            else:
                clauses.append(f"LOWER({detection_alias}.scientific_name) = LOWER(?)")
            params.append(scientific_name)

        match_names = [str(name).strip() for name in (alias_info.get("match_names") or []) if str(name).strip()]
        lowered_names = []
        seen_names: set[str] = set()
        for name in match_names:
            lowered = name.lower()
            if lowered in seen_names:
                continue
            seen_names.add(lowered)
            lowered_names.append(lowered)

        if lowered_names:
            placeholders = ",".join(["?"] * len(lowered_names))
            if has_taxonomy_cache:
                clauses.append(
                    f"(LOWER({detection_alias}.display_name) IN ({placeholders}) "
                    f"OR LOWER(COALESCE({detection_alias}.scientific_name, tc_filter.scientific_name)) IN ({placeholders}) "
                    f"OR LOWER(COALESCE({detection_alias}.common_name, tc_filter.common_name)) IN ({placeholders}))"
                )
            else:
                clauses.append(
                    f"(LOWER({detection_alias}.display_name) IN ({placeholders}) "
                    f"OR LOWER({detection_alias}.scientific_name) IN ({placeholders}) "
                    f"OR LOWER({detection_alias}.common_name) IN ({placeholders}))"
                )
            params.extend(lowered_names)
            params.extend(lowered_names)
            params.extend(lowered_names)

        if not clauses:
            clauses.append(f"LOWER({detection_alias}.display_name) = LOWER(?)")
            params.append(species_name)

        return "(" + " OR ".join(clauses) + ")", params

    async def _canonical_species_query_parts(
        self,
        *,
        detection_alias: str,
        species_name: str,
    ) -> tuple[str, str, list]:
        # No join. Its only job was to reach a detection whose own scientific
        # name is absent, through its display name, to the species searched
        # for, and the alias resolver already produces those names. The join
        # cost a scan of the whole taxonomy cache per detection row, because
        # its conditions are ORs across different columns wrapped in LOWER(),
        # which no index can serve.
        join_sql = ""
        condition, params = await self._build_canonical_species_condition(
            detection_alias=detection_alias,
            species_name=species_name,
            has_taxonomy_cache=False,
        )

        # Grouping keys on catalogue identity, so filtering has to follow it or
        # the two disagree: the leaderboard merges a renamed taxon into one row,
        # and opening that row shows only the rows still carrying the name that
        # was searched for.
        #
        # Resolved to concrete ids first rather than left as a subquery. A
        # subquery here is evaluated once, but it still scans the whole
        # detections table, and this runs on the events list where a species
        # filter was already the slowest of the three filters. Measured on a
        # 96,108 row database: 54ms as a subquery against 16ms resolved.
        identity_ids = await self._species_ids_for_name(species_name)
        if identity_ids:
            placeholders = ",".join(["?"] * len(identity_ids))
            condition = f"(({condition}) OR {detection_alias}.species_id IN ({placeholders}))"
            params = [*params, *identity_ids]
        return join_sql, condition, params

    async def _species_ids_for_name(self, species_name: str) -> list[int]:
        """Catalogue identities already recorded against this name.

        Read from `detections` rather than the catalogue: the identity we want is
        the one history actually carries, and it keeps this inside one database
        (§3).

        Each arm is a bare `LOWER(column)` so the lowercased-name indexes can
        serve it. Wrapping `common_name` in `COALESCE` to tolerate NULL cost the
        index and took this from 7ms to 46ms on a 96,108 row database; a NULL
        simply does not match, which is the behaviour wanted anyway.
        """
        name = str(species_name or "").strip()
        if not name:
            return []
        async with self.db.execute(
            """
            SELECT DISTINCT species_id FROM detections
            WHERE species_id IS NOT NULL
              AND (LOWER(scientific_name) = LOWER(?) OR LOWER(display_name) = LOWER(?)
                   OR LOWER(common_name) = LOWER(?))
            """,
            (name, name, name),
        ) as cursor:
            rows = await cursor.fetchall()
        return [int(row[0]) for row in rows if row and row[0] is not None]

    async def _last_statement_changes(self) -> int:
        """Return rows changed by the most recent write statement on this connection."""
        cursor = await self.db.execute("SELECT changes()")
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row and row[0] is not None else 0

    async def _table_exists(self, table_name: str) -> bool:
        cached = self._table_exists_cache.get(table_name)
        if cached is not None:
            return cached
        async with self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,),
        ) as cursor:
            row = await cursor.fetchone()
        exists = row is not None
        self._table_exists_cache[table_name] = exists
        return exists

    _ALLOWED_PRAGMA_TABLES: frozenset[str] = frozenset(
        {
            "detections",
            "taxonomy_cache",
            "species_daily_rollup",
            "species_info_cache",
            "classification_feedback",
            "oauth_tokens",
            "snapshot_candidates",
            "video_classification_top_frames",
        }
    )

    async def _table_columns(self, table_name: str) -> set[str]:
        if table_name not in self._ALLOWED_PRAGMA_TABLES:
            raise ValueError(f"Unexpected table name passed to _table_columns: {table_name!r}")
        if not await self._table_exists(table_name):
            return set()
        async with self.db.execute(f"PRAGMA table_info({table_name})") as cursor:
            rows = await cursor.fetchall()
        return {row[1] for row in rows if row and len(row) > 1}

    async def get_by_frigate_event(self, frigate_event: str) -> Optional[Detection]:
        async with self.db.execute(
            f"""SELECT {DETECTION_SELECT_COLUMNS}
               FROM detections d
               LEFT JOIN detection_favorites f ON f.detection_id = d.id
               WHERE d.frigate_event = ?""",
            (frigate_event,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

    async def has_recent_detection_for_species(
        self,
        camera: str,
        display_name: str,
        within_minutes: int,
    ) -> bool:
        """Return True if a non-hidden detection of the same display_name exists
        on the given camera within the last `within_minutes` minutes.

        Used by the nest-mode dedupe guard so a continuously-present nesting
        bird does not produce a fresh detection per Frigate event.
        """
        if not camera or not display_name or within_minutes <= 0:
            return False
        async with self.db.execute(
            """SELECT 1 FROM detections
               WHERE camera_name = ?
                 AND LOWER(display_name) = LOWER(?)
                 AND COALESCE(is_hidden, 0) = 0
                 AND detection_time >= datetime('now', ?)
               LIMIT 1""",
            (camera, display_name, f"-{int(within_minutes)} minutes"),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def get_by_id(self, detection_id: int) -> Optional[Detection]:
        async with self.db.execute(
            f"""SELECT {DETECTION_SELECT_COLUMNS}
               FROM detections d
               LEFT JOIN detection_favorites f ON f.detection_id = d.id
               WHERE d.id = ?""",
            (detection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

    async def count_timezone_repair_rows(self, *, detected_after: datetime | None = None) -> int:
        query = """
            SELECT COUNT(*)
            FROM detections
            WHERE frigate_event IS NOT NULL
              AND frigate_event != ''
        """
        params: list[object] = []
        if detected_after is not None:
            query += " AND datetime(detection_time) >= datetime(?)"
            params.append(detected_after.strftime("%Y-%m-%d %H:%M:%S"))
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0

    async def list_timezone_repair_rows(
        self,
        *,
        detected_after: datetime | None = None,
        limit: int | None = None,
    ) -> list[TimezoneRepairRow]:
        query = """
            SELECT id, detection_time, frigate_event, camera_name, display_name
            FROM detections
            WHERE frigate_event IS NOT NULL
              AND frigate_event != ''
        """
        params: list[object] = []
        if detected_after is not None:
            query += " AND datetime(detection_time) >= datetime(?)"
            params.append(detected_after.strftime("%Y-%m-%d %H:%M:%S"))
        query += " ORDER BY detection_time DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            TimezoneRepairRow(
                id=int(row[0]),
                detection_time=_parse_datetime(row[1]),
                frigate_event=str(row[2]),
                camera_name=str(row[3] or ""),
                display_name=str(row[4] or ""),
            )
            for row in rows
        ]

    async def update_detection_time_by_id(self, detection_id: int, detection_time: datetime) -> int:
        await self.db.execute(
            "UPDATE detections SET detection_time = ? WHERE id = ?",
            (detection_time, detection_id),
        )
        await self.db.commit()
        return await self._last_statement_changes()

    async def get_recent_full_visit_candidates(
        self,
        *,
        detected_before: datetime,
        detected_after: datetime,
        limit: int = 100,
    ) -> list[Detection]:
        async with self.db.execute(
            f"""SELECT {DETECTION_SELECT_COLUMNS}
               FROM detections d
               LEFT JOIN detection_favorites f ON f.detection_id = d.id
               WHERE d.frigate_event IS NOT NULL
                 AND d.frigate_event != ''
                 AND d.camera_name IS NOT NULL
                 AND d.camera_name != ''
                 AND d.detection_time <= ?
                 AND d.detection_time >= ?
               ORDER BY d.detection_time DESC
               LIMIT ?""",
            (detected_before, detected_after, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_detection(row) for row in rows]

    async def update_video_classification(
        self,
        frigate_event: str,
        label: Optional[str],
        score: float,
        index: int,
        status: str = "completed",
        provider: Optional[str] = None,
        backend: Optional[str] = None,
        model_id: Optional[str] = None,
        input_source: Optional[str] = None,
        blocked: bool = False,
    ) -> None:
        """Update video classification results for an event."""
        now = utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET video_classification_label = ?,
                video_classification_score = ?,
                video_classification_index = ?,
                video_classification_timestamp = ?,
                video_classification_status = ?,
                video_classification_error = NULL,
                video_classification_provider = ?,
                video_classification_backend = ?,
                video_classification_model_id = ?,
                video_classification_input_source = ?,
                video_classification_diagnostics = NULL,
                video_result_blocked = ?
            WHERE frigate_event = ?
        """,
            (label, score, index, now, status, provider, backend, model_id, input_source, blocked, frigate_event),
        )
        await self.db.commit()

    async def update_primary_classification(
        self,
        *,
        frigate_event: str,
        display_name: str,
        category_name: str,
        score: float,
        detection_index: int,
        scientific_name: str | None,
        common_name: str | None,
        taxa_id: int | None,
        audio_confirmed: bool,
        audio_species: str | None,
        audio_score: float | None,
        manual_override: bool,
        species_id: int | None = None,
        model_artifact_id: int | None = None,
        model_output_index: int | None = None,
    ) -> bool:
        """Update the canonical identity without racing a manual correction.

        Automatic refinements may still be recorded in their source-specific
        columns, but they must never replace an identity a user has confirmed.
        The permission check belongs in the same SQL statement as the write so a
        concurrent manual tag cannot be lost between a service read and update.
        """
        await self.db.execute(
            """
            UPDATE detections
            SET display_name = ?,
                category_name = ?,
                score = ?,
                detection_index = ?,
                scientific_name = ?,
                common_name = ?,
                taxa_id = ?,
                species_id = ?,
                model_artifact_id = ?,
                model_output_index = ?,
                audio_confirmed = ?,
                audio_species = ?,
                audio_score = ?,
                manual_tagged = CASE WHEN ? = 1 THEN 1 ELSE manual_tagged END
            WHERE frigate_event = ?
              AND (? = 1 OR COALESCE(manual_tagged, 0) = 0)
            """,
            (
                display_name,
                category_name,
                score,
                detection_index,
                scientific_name,
                common_name,
                taxa_id,
                species_id,
                model_artifact_id,
                model_output_index,
                1 if audio_confirmed else 0,
                audio_species,
                audio_score,
                1 if manual_override else 0,
                frigate_event,
                1 if manual_override else 0,
            ),
        )
        changed = await self._last_statement_changes() > 0
        await self.db.commit()
        return changed

    async def update_video_status(
        self,
        frigate_event: str,
        status: str,
        error: Optional[str] = None,
        diagnostics: Optional[dict] = None,
    ) -> bool:
        """Update video classification status and report whether the detection exists."""
        now = utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET video_classification_status = ?,
                video_classification_error = ?,
                video_classification_diagnostics = ?,
                video_classification_timestamp = ?
            WHERE frigate_event = ?
        """,
            (
                status,
                error,
                json.dumps(diagnostics, separators=(",", ":"), sort_keys=True) if diagnostics else None,
                now,
                frigate_event,
            ),
        )
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed > 0

    async def reset_stale_video_statuses(self, max_age_minutes: int) -> int:
        """Mark pending/processing video classifications as failed if they are too old."""
        now = utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET video_classification_status = 'failed',
                video_classification_error = 'stale_timeout',
                video_classification_timestamp = ?
            WHERE video_classification_status IN ('pending', 'processing')
              AND (video_classification_timestamp IS NULL
                   OR video_classification_timestamp < datetime('now', ?))
        """,
            (now, f"-{max_age_minutes} minutes"),
        )
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed

    async def get_video_classification_recovery_candidates(self, limit: int = 1000) -> list[dict[str, str]]:
        """Return unfinished video jobs that must be reclaimed after a restart."""
        safe_limit = max(1, min(int(limit), 5000))
        async with self.db.execute(
            """
            SELECT frigate_event, camera_name, COALESCE(video_classification_status, 'pending')
            FROM detections
            WHERE video_classification_status IN ('pending', 'processing')
              AND (is_hidden = 0 OR is_hidden IS NULL)
            ORDER BY COALESCE(video_classification_timestamp, detection_time) ASC
            LIMIT ?
            """,
            (safe_limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"event_id": str(row[0]), "camera": str(row[1] or ""), "status": str(row[2])}
            for row in rows
            if row[0] and row[1]
        ]

    async def mark_notified(self, frigate_event: str, timestamp: Optional[datetime] = None) -> None:
        """Mark a detection as notified."""
        if timestamp is None:
            timestamp = utc_naive_now()
        await self.db.execute(
            "UPDATE detections SET notified_at = ? WHERE frigate_event = ?", (timestamp, frigate_event)
        )
        await self.db.commit()

    async def insert_classification_feedback(
        self,
        *,
        frigate_event: Optional[str],
        camera_name: str,
        model_id: str,
        predicted_label: str,
        corrected_label: str,
        predicted_score: Optional[float],
        source: str = "manual_tag",
    ) -> bool:
        """Insert a feedback row for personalization learning.

        Returns False (without raising) when table/schema support is unavailable.
        """
        if not await self._table_exists("classification_feedback"):
            return False

        if not camera_name or not model_id or not predicted_label or not corrected_label:
            log.warning(
                "Skipping classification feedback insert due to missing required fields",
                camera_name=bool(camera_name),
                model_id=bool(model_id),
                predicted_label=bool(predicted_label),
                corrected_label=bool(corrected_label),
            )
            return False

        try:
            await self.db.execute(
                """
                INSERT INTO classification_feedback (
                    frigate_event, camera_name, model_id, predicted_label, corrected_label, predicted_score, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frigate_event,
                    camera_name,
                    model_id,
                    predicted_label,
                    corrected_label,
                    predicted_score,
                    source,
                ),
            )
            return True
        except Exception as exc:
            log.warning(
                "Failed to insert classification feedback; continuing without personalization feedback",
                error=str(exc),
                frigate_event=frigate_event,
                camera_name=camera_name,
                model_id=model_id,
            )
            return False

    async def update_ai_analysis(self, frigate_event: str, analysis: str) -> datetime:
        """Update AI naturalist analysis for an event."""
        now = utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET ai_analysis = ?,
                ai_analysis_timestamp = ?
            WHERE frigate_event = ?
        """,
            (analysis, now, frigate_event),
        )
        await self.db.commit()
        return now

    async def toggle_hidden(self, frigate_event: str) -> Optional[bool]:
        """Toggle the hidden status of a detection. Returns new hidden status or None if not found."""
        detection = await self.get_by_frigate_event(frigate_event)
        if not detection:
            return None

        new_status = not detection.is_hidden
        await self.db.execute(
            "UPDATE detections SET is_hidden = ? WHERE frigate_event = ?", (1 if new_status else 0, frigate_event)
        )
        await self.db.commit()
        return new_status

    async def favorite_detection(self, frigate_event: str, created_by: Optional[str] = None) -> Optional[bool]:
        """Mark detection as favorite. Returns True if detection exists, None if not found."""
        detection = await self.get_by_frigate_event(frigate_event)
        if not detection or detection.id is None:
            return None

        await self.db.execute(
            "INSERT OR IGNORE INTO detection_favorites (detection_id, created_by) VALUES (?, ?)",
            (detection.id, created_by),
        )
        await self.db.commit()
        return True

    async def unfavorite_detection(self, frigate_event: str) -> Optional[bool]:
        """Remove favorite marker. Returns True if detection exists, None if not found."""
        detection = await self.get_by_frigate_event(frigate_event)
        if not detection or detection.id is None:
            return None

        await self.db.execute("DELETE FROM detection_favorites WHERE detection_id = ?", (detection.id,))
        await self.db.commit()
        return True

    async def clear_all_favorites(self) -> int:
        """Remove all favorite markers and return number of removed rows."""
        async with self.db.execute("DELETE FROM detection_favorites") as cursor:
            deleted = cursor.rowcount or 0
        await self.db.commit()
        return deleted

    async def clear_all_classification_feedback(self) -> int:
        """Remove all personalized re-ranking classification feedback and return number of removed rows."""
        if not await self._table_exists("classification_feedback"):
            return 0

        async with self.db.execute("DELETE FROM classification_feedback") as cursor:
            deleted = cursor.rowcount or 0
        await self.db.commit()
        return deleted

    async def get_hidden_count(self) -> int:
        """Get count of hidden detections."""
        async with self.db.execute("SELECT COUNT(*) FROM detections WHERE is_hidden = 1") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def delete_by_id(self, detection_id: int) -> bool:
        """Delete a detection by ID. Returns True if deleted."""
        await self.db.execute("DELETE FROM detections WHERE id = ?", (detection_id,))
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed > 0

    async def delete_by_frigate_event(self, frigate_event: str) -> bool:
        """Delete a detection by Frigate event ID. Returns True if deleted."""
        await self.db.execute("DELETE FROM detections WHERE frigate_event = ?", (frigate_event,))
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed > 0

    async def create(self, detection: Detection) -> None:
        sub_label = normalize_sub_label(detection.sub_label)
        checked_at = utc_naive_now()
        try:
            await self.db.execute(
                """
                INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, species_id, model_artifact_id, model_output_index, manual_tagged, frigate_status, frigate_missing_since, frigate_last_checked_at, frigate_last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    detection.detection_time,
                    detection.detection_index,
                    detection.score,
                    detection.display_name,
                    detection.category_name,
                    detection.frigate_event,
                    detection.camera_name,
                    1 if detection.is_hidden else 0,
                    detection.frigate_score,
                    sub_label,
                    1 if detection.audio_confirmed else 0,
                    detection.audio_species,
                    detection.audio_score,
                    detection.temperature,
                    detection.weather_condition,
                    detection.weather_cloud_cover,
                    detection.weather_wind_speed,
                    detection.weather_wind_direction,
                    detection.weather_precipitation,
                    detection.weather_rain,
                    detection.weather_snowfall,
                    detection.scientific_name,
                    detection.common_name,
                    detection.taxa_id,
                    detection.species_id,
                    detection.model_artifact_id,
                    detection.model_output_index,
                    1 if detection.manual_tagged else 0,
                    "present",
                    None,
                    checked_at,
                    None,
                ),
            )
            await self.db.commit()
        except aiosqlite.IntegrityError as e:
            if "UNIQUE constraint failed: detections.frigate_event" in str(e):
                log.debug(
                    "Duplicate frigate_event insert skipped (idempotent)",
                    frigate_event=detection.frigate_event,
                )
            else:
                raise

    async def update(self, detection: Detection) -> None:
        sub_label = normalize_sub_label(detection.sub_label)
        checked_at = utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET detection_time = ?, detection_index = ?, score = ?, display_name = ?, category_name = ?, frigate_score = ?, sub_label = ?, audio_confirmed = ?, audio_species = ?, audio_score = ?, temperature = ?, weather_condition = ?, weather_cloud_cover = ?, weather_wind_speed = ?, weather_wind_direction = ?, weather_precipitation = ?, weather_rain = ?, weather_snowfall = ?, scientific_name = ?, common_name = ?, taxa_id = ?, manual_tagged = ?, frigate_status = 'present', frigate_missing_since = NULL, frigate_last_checked_at = ?, frigate_last_error = NULL
            WHERE frigate_event = ?
        """,
            (
                detection.detection_time,
                detection.detection_index,
                detection.score,
                detection.display_name,
                detection.category_name,
                detection.frigate_score,
                sub_label,
                detection.audio_confirmed,
                detection.audio_species,
                detection.audio_score,
                detection.temperature,
                detection.weather_condition,
                detection.weather_cloud_cover,
                detection.weather_wind_speed,
                detection.weather_wind_direction,
                detection.weather_precipitation,
                detection.weather_rain,
                detection.weather_snowfall,
                detection.scientific_name,
                detection.common_name,
                detection.taxa_id,
                1 if detection.manual_tagged else 0,
                checked_at,
                detection.frigate_event,
            ),
        )
        await self.db.commit()

    async def list_for_weather_backfill(self, start: str, end: str, only_missing: bool = True) -> list[dict]:
        """Return detections within range for weather backfill."""
        query = """
            SELECT frigate_event, detection_time, temperature, weather_condition, weather_cloud_cover,
                   weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall
            FROM detections
            WHERE datetime(detection_time) >= datetime(?)
              AND datetime(detection_time) < datetime(?)
        """
        params = [start, end]
        if only_missing:
            query += """
                AND (
                    temperature IS NULL OR
                    weather_condition IS NULL OR
                    weather_cloud_cover IS NULL OR
                    weather_wind_speed IS NULL OR
                    weather_wind_direction IS NULL OR
                    weather_precipitation IS NULL OR
                    weather_rain IS NULL OR
                    weather_snowfall IS NULL
                )
            """
        cursor = await self.db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            {
                "frigate_event": row[0],
                "detection_time": row[1],
                "temperature": row[2],
                "weather_condition": row[3],
                "weather_cloud_cover": row[4],
                "weather_wind_speed": row[5],
                "weather_wind_direction": row[6],
                "weather_precipitation": row[7],
                "weather_rain": row[8],
                "weather_snowfall": row[9],
            }
            for row in rows
        ]

    async def update_weather_fields(
        self,
        frigate_event: str,
        temperature: float | None,
        weather_condition: str | None,
        cloud_cover: float | None,
        wind_speed: float | None,
        wind_direction: float | None,
        precipitation: float | None,
        rain: float | None,
        snowfall: float | None,
    ) -> None:
        await self.db.execute(
            """
            UPDATE detections
            SET temperature = ?,
                weather_condition = ?,
                weather_cloud_cover = ?,
                weather_wind_speed = ?,
                weather_wind_direction = ?,
                weather_precipitation = ?,
                weather_rain = ?,
                weather_snowfall = ?
            WHERE frigate_event = ?
        """,
            (
                temperature,
                weather_condition,
                cloud_cover,
                wind_speed,
                wind_direction,
                precipitation,
                rain,
                snowfall,
                frigate_event,
            ),
        )
        await self.db.commit()

    async def upsert_if_higher_score(self, detection: Detection) -> tuple[bool, bool]:
        """Insert if missing, otherwise update only when score/audio is better.

        Returns:
            Tuple of (was_inserted, was_updated)
        """
        sub_label = normalize_sub_label(detection.sub_label)
        checked_at = utc_naive_now()
        insert_params = (
            detection.detection_time,
            detection.detection_index,
            detection.score,
            detection.display_name,
            detection.category_name,
            detection.frigate_event,
            detection.camera_name,
            1 if detection.is_hidden else 0,
            detection.frigate_score,
            sub_label,
            1 if detection.audio_confirmed else 0,
            detection.audio_species,
            detection.audio_score,
            detection.temperature,
            detection.weather_condition,
            detection.weather_cloud_cover,
            detection.weather_wind_speed,
            detection.weather_wind_direction,
            detection.weather_precipitation,
            detection.weather_rain,
            detection.weather_snowfall,
            getattr(detection, "scientific_name", None),
            getattr(detection, "common_name", None),
            getattr(detection, "taxa_id", None),
            detection.species_id,
            detection.model_artifact_id,
            detection.model_output_index,
            1 if detection.manual_tagged else 0,
            "present",
            None,
            checked_at,
            None,
        )

        # Attempt insert first.
        await self.db.execute(
            """
            INSERT OR IGNORE INTO detections
            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, species_id, model_artifact_id, model_output_index, manual_tagged, frigate_status, frigate_missing_since, frigate_last_checked_at, frigate_last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            insert_params,
        )
        inserted = await self._last_statement_changes() > 0
        if inserted:
            await self.db.commit()
            return (True, False)

        # Existing row: update only when it improves quality.
        await self.db.execute(
            """
            UPDATE detections
            SET detection_time = :detection_time,
                detection_index = :detection_index,
                score = :score,
                display_name = :display_name,
                category_name = :category_name,
                frigate_score = CASE
                    WHEN :frigate_score IS NULL THEN frigate_score
                    WHEN frigate_score IS NULL THEN :frigate_score
                    ELSE MAX(:frigate_score, frigate_score)
                END,
                sub_label = COALESCE(:sub_label, sub_label),
                audio_confirmed = CASE
                    WHEN :audio_confirmed = 1 THEN 1
                    ELSE COALESCE(audio_confirmed, 0)
                END,
                audio_species = CASE
                    WHEN :audio_confirmed = 1
                     AND COALESCE(:audio_score, -1) >= COALESCE(audio_score, -1)
                    THEN COALESCE(:audio_species, audio_species)
                    ELSE audio_species
                END,
                audio_score = CASE
                    WHEN :audio_confirmed = 1
                     AND :audio_score IS NOT NULL
                     AND :audio_score >= COALESCE(audio_score, -1)
                    THEN :audio_score
                    ELSE audio_score
                END,
                temperature = COALESCE(:temperature, temperature),
                weather_condition = COALESCE(:weather_condition, weather_condition),
                weather_cloud_cover = COALESCE(:weather_cloud_cover, weather_cloud_cover),
                weather_wind_speed = COALESCE(:weather_wind_speed, weather_wind_speed),
                weather_wind_direction = COALESCE(:weather_wind_direction, weather_wind_direction),
                weather_precipitation = COALESCE(:weather_precipitation, weather_precipitation),
                weather_rain = COALESCE(:weather_rain, weather_rain),
                weather_snowfall = COALESCE(:weather_snowfall, weather_snowfall),
                scientific_name = CASE
                    WHEN LOWER(TRIM(:category_name)) = LOWER(TRIM(category_name))
                    THEN COALESCE(:scientific_name, scientific_name)
                    ELSE :scientific_name
                END,
                common_name = CASE
                    WHEN LOWER(TRIM(:category_name)) = LOWER(TRIM(category_name))
                    THEN COALESCE(:common_name, common_name)
                    ELSE :common_name
                END,
                taxa_id = CASE
                    WHEN LOWER(TRIM(:category_name)) = LOWER(TRIM(category_name))
                    THEN COALESCE(:taxa_id, taxa_id)
                    ELSE :taxa_id
                END,
                species_id = :species_id,
                model_artifact_id = :model_artifact_id,
                model_output_index = :model_output_index,
                manual_tagged = manual_tagged,
                frigate_status = 'present',
                frigate_missing_since = NULL,
                frigate_last_checked_at = :checked_at,
                frigate_last_error = NULL
            WHERE frigate_event = :frigate_event
              AND COALESCE(manual_tagged, 0) = 0
              AND (
                    :score > score
                    OR (
                        :audio_confirmed = 1
                        AND (
                            COALESCE(audio_confirmed, 0) = 0
                            OR COALESCE(:audio_score, -1) > COALESCE(audio_score, -1)
                        )
                    )
              )
        """,
            {
                "detection_time": detection.detection_time,
                "detection_index": detection.detection_index,
                "score": detection.score,
                "display_name": detection.display_name,
                "category_name": detection.category_name,
                "frigate_score": detection.frigate_score,
                "sub_label": sub_label,
                "audio_confirmed": 1 if detection.audio_confirmed else 0,
                "audio_species": detection.audio_species,
                "audio_score": detection.audio_score,
                "temperature": detection.temperature,
                "weather_condition": detection.weather_condition,
                "weather_cloud_cover": detection.weather_cloud_cover,
                "weather_wind_speed": detection.weather_wind_speed,
                "weather_wind_direction": detection.weather_wind_direction,
                "weather_precipitation": detection.weather_precipitation,
                "weather_rain": detection.weather_rain,
                "weather_snowfall": detection.weather_snowfall,
                "scientific_name": getattr(detection, "scientific_name", None),
                "common_name": getattr(detection, "common_name", None),
                "taxa_id": getattr(detection, "taxa_id", None),
                "species_id": detection.species_id,
                "model_artifact_id": detection.model_artifact_id,
                "model_output_index": detection.model_output_index,
                "checked_at": checked_at,
                "frigate_event": detection.frigate_event,
            },
        )
        updated = await self._last_statement_changes() > 0
        await self.db.commit()
        return (False, updated)

    async def distinct_scientific_names_without_identity(self) -> list[str]:
        """Every distinct scientific name on rows that have no canonical identity yet."""
        cursor = await self.db.execute(
            "SELECT DISTINCT scientific_name FROM detections"
            " WHERE species_id IS NULL AND scientific_name IS NOT NULL AND TRIM(scientific_name) != ''"
        )
        rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def assign_species_id_by_scientific_name(self, scientific_name: str, species_id: int) -> int:
        """Backfill one resolved name onto its identity-less rows; returns rows changed.

        Only `species_id` is written: name snapshots and artifact provenance
        are never touched, and an identity already present is never replaced.
        """
        await self.db.execute(
            "UPDATE detections SET species_id = ?"
            " WHERE species_id IS NULL AND LOWER(TRIM(scientific_name)) = LOWER(TRIM(?))",
            (species_id, scientific_name),
        )
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed

    async def insert_if_not_exists(self, detection: Detection) -> bool:
        """Atomically insert a detection only if it doesn't already exist.

        Uses SQLite's INSERT OR IGNORE to prevent race conditions.
        Useful for backfill operations where we don't want to update existing records.

        Args:
            detection: The detection to insert

        Returns:
            True if inserted, False if already existed
        """
        sub_label = normalize_sub_label(detection.sub_label)
        checked_at = utc_naive_now()
        await self.db.execute(
            """
            INSERT OR IGNORE INTO detections
            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, species_id, model_artifact_id, model_output_index, manual_tagged, frigate_status, frigate_missing_since, frigate_last_checked_at, frigate_last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                detection.detection_time,
                detection.detection_index,
                detection.score,
                detection.display_name,
                detection.category_name,
                detection.frigate_event,
                detection.camera_name,
                1 if detection.is_hidden else 0,
                detection.frigate_score,
                sub_label,
                1 if detection.audio_confirmed else 0,
                detection.audio_species,
                detection.audio_score,
                detection.temperature,
                detection.weather_condition,
                detection.weather_cloud_cover,
                detection.weather_wind_speed,
                detection.weather_wind_direction,
                detection.weather_precipitation,
                detection.weather_rain,
                detection.weather_snowfall,
                detection.scientific_name,
                detection.common_name,
                detection.taxa_id,
                detection.species_id,
                detection.model_artifact_id,
                detection.model_output_index,
                1 if detection.manual_tagged else 0,
                "present",
                None,
                checked_at,
                None,
            ),
        )
        changes = await self._last_statement_changes()
        await self.db.commit()
        return changes > 0

    async def get_all(
        self,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        species: str | None = None,
        species_any: list[str] | None = None,
        taxa_id: int | None = None,
        camera: str | None = None,
        sort: str = "newest",
        include_hidden: bool = False,
        favorite_only: bool = False,
        audio_confirmed_only: bool = False,
        frigate_event: str | None = None,
    ) -> list[Detection]:
        has_taxonomy_cache = await self._table_exists("taxonomy_cache")
        # The join is kept only for a `taxa_id` filter, which still reads the
        # cached taxon id for a detection that has none of its own. Species
        # filtering no longer needs it: the alias resolver supplies the names
        # the join used to reach, and the join cost a scan of the whole
        # taxonomy cache per detection row plus a DISTINCT over every column.
        needs_taxonomy_cache = bool(has_taxonomy_cache and taxa_id is not None)
        query = (
            """
            SELECT """
            + ("DISTINCT " if needs_taxonomy_cache else "")
            + DETECTION_SELECT_COLUMNS
            + """
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
        """
        )
        if needs_taxonomy_cache:
            query += """
            LEFT JOIN taxonomy_cache tc_filter
                ON ((d.scientific_name IS NOT NULL AND LOWER(tc_filter.scientific_name) = LOWER(d.scientific_name))
                    OR (d.scientific_name IS NULL AND (LOWER(tc_filter.scientific_name) = LOWER(d.display_name)
                        OR LOWER(tc_filter.common_name) = LOWER(d.display_name))))
            """
        params: list = []
        conditions = []

        # By default, exclude hidden detections
        if not include_hidden:
            conditions.append("(d.is_hidden = 0 OR d.is_hidden IS NULL)")

        if start_date:
            conditions.append("d.detection_time >= ?")
            params.append(start_date.isoformat(sep=" "))
        if end_date:
            conditions.append("d.detection_time <= ?")
            params.append(end_date.isoformat(sep=" "))
        if species:
            species_condition, species_params = await self._build_canonical_species_condition(
                detection_alias="d",
                species_name=species,
                has_taxonomy_cache=False,
            )
            conditions.append(species_condition)
            params.extend(species_params)
        if species_any:
            any_clauses: list[str] = []
            any_params: list = []
            for species_name in species_any:
                clause, clause_params = await self._build_canonical_species_condition(
                    detection_alias="d",
                    species_name=species_name,
                    has_taxonomy_cache=False,
                )
                any_clauses.append(clause)
                any_params.extend(clause_params)
            if any_clauses:
                conditions.append("(" + " OR ".join(any_clauses) + ")")
                params.extend(any_params)
        if taxa_id is not None:
            if needs_taxonomy_cache:
                conditions.append("COALESCE(d.taxa_id, tc_filter.taxa_id) = ?")
            else:
                conditions.append("d.taxa_id = ?")
            params.append(taxa_id)
        if camera:
            conditions.append("d.camera_name = ?")
            params.append(camera)
        if favorite_only:
            conditions.append("f.detection_id IS NOT NULL")
        if audio_confirmed_only:
            conditions.append("d.audio_confirmed = 1")
        if frigate_event:
            conditions.append("d.frigate_event = ?")
            params.append(frigate_event)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Apply sort order
        if sort == "oldest":
            query += " ORDER BY d.detection_time ASC"
        elif sort == "confidence":
            query += " ORDER BY d.score DESC, d.detection_time DESC"
        else:  # newest (default)
            query += " ORDER BY d.detection_time DESC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]

    async def get_count(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        species: str | None = None,
        species_any: list[str] | None = None,
        taxa_id: int | None = None,
        camera: str | None = None,
        include_hidden: bool = False,
        favorite_only: bool = False,
        exclude_favorites: bool = False,
        audio_confirmed_only: bool = False,
    ) -> int:
        """Get total count of detections, optionally filtered."""
        has_taxonomy_cache = await self._table_exists("taxonomy_cache")
        # The join is kept only for a `taxa_id` filter, which still reads the
        # cached taxon id for a detection that has none of its own. Species
        # filtering no longer needs it: the alias resolver supplies the names
        # the join used to reach, and the join cost a scan of the whole
        # taxonomy cache per detection row plus a DISTINCT over every column.
        needs_taxonomy_cache = bool(has_taxonomy_cache and taxa_id is not None)
        query = f"""
            SELECT {"COUNT(DISTINCT d.id)" if needs_taxonomy_cache else "COUNT(*)"}
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
        """
        if needs_taxonomy_cache:
            query += """
            LEFT JOIN taxonomy_cache tc_filter
                ON ((d.scientific_name IS NOT NULL AND LOWER(tc_filter.scientific_name) = LOWER(d.scientific_name))
                    OR (d.scientific_name IS NULL AND (LOWER(tc_filter.scientific_name) = LOWER(d.display_name)
                        OR LOWER(tc_filter.common_name) = LOWER(d.display_name))))
            """
        params: list = []
        conditions = []

        # By default, exclude hidden detections
        if not include_hidden:
            conditions.append("(d.is_hidden = 0 OR d.is_hidden IS NULL)")

        if start_date:
            conditions.append("d.detection_time >= ?")
            params.append(start_date.isoformat(sep=" "))
        if end_date:
            conditions.append("d.detection_time <= ?")
            params.append(end_date.isoformat(sep=" "))
        if species:
            species_condition, species_params = await self._build_canonical_species_condition(
                detection_alias="d",
                species_name=species,
                has_taxonomy_cache=False,
            )
            conditions.append(species_condition)
            params.extend(species_params)
        if species_any:
            any_clauses: list[str] = []
            any_params: list = []
            for species_name in species_any:
                clause, clause_params = await self._build_canonical_species_condition(
                    detection_alias="d",
                    species_name=species_name,
                    has_taxonomy_cache=False,
                )
                any_clauses.append(clause)
                any_params.extend(clause_params)
            if any_clauses:
                conditions.append("(" + " OR ".join(any_clauses) + ")")
                params.extend(any_params)
        if taxa_id is not None:
            if needs_taxonomy_cache:
                conditions.append("COALESCE(d.taxa_id, tc_filter.taxa_id) = ?")
            else:
                conditions.append("d.taxa_id = ?")
            params.append(taxa_id)
        if camera:
            conditions.append("d.camera_name = ?")
            params.append(camera)
        if favorite_only and exclude_favorites:
            conditions.append("1 = 0")
        elif favorite_only:
            conditions.append("f.detection_id IS NOT NULL")
        elif exclude_favorites:
            conditions.append("f.detection_id IS NULL")

        if audio_confirmed_only:
            conditions.append("d.audio_confirmed = 1")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_unique_species(self) -> list[str]:
        """Get list of unique species names, sorted alphabetically."""
        async with self.db.execute("SELECT DISTINCT display_name FROM detections ORDER BY display_name ASC") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_unique_species_with_taxonomy(
        self,
        start_date: datetime | None = None,
    ) -> list[tuple[str, str | None, str | None, int | None, int]]:
        """Get unique species, pre-grouped to avoid duplicates from display_name variants.

        Strategy:
        1. Join detections with taxonomy_cache to fill in missing taxa_id wherever
           scientific_name is known, so rows that share a scientific name but have
           inconsistent taxa_id storage are treated as the same species.
        2. Collect DISTINCT (display_name, scientific_name, common_name, taxa_id)
           combinations to keep the working set small before ranking.
        3. Use a window function to pick one canonical row per species group, ranked
           by: taxa_id present > scientific_name present > common_name present, then
           alphabetically by display_name for determinism.

        This means "Great tit", "Great tit (Parus major)", "Parus major (Great tit)"
        all collapse to a single row before Python taxonomy resolution runs, removing
        the source of duplicate entries in the Explorer species filter.
        """
        start_filter = "AND d.detection_time >= ?" if start_date else ""
        params = [start_date.isoformat(sep=" ")] if start_date else []
        async with self.db.execute(
            f"""
            WITH species_rows AS (
                -- Enrich taxa_id from taxonomy_cache when the detection is missing it
                -- but has a known scientific_name we can join on.
                SELECT
                    d.display_name,
                    d.scientific_name,
                    d.common_name,
                    COALESCE(d.taxa_id, tc.taxa_id) AS taxa_id
                FROM detections d
                LEFT JOIN taxonomy_cache tc
                    ON d.scientific_name IS NOT NULL
                    AND LOWER(tc.scientific_name) = LOWER(d.scientific_name)
                WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
                  {start_filter}
            ),
            -- The filter bar shows how many detections each option would return, so the
            -- count has to be taken over the same grouping the options are built from.
            group_counts AS (
                SELECT
                    COALESCE(
                        CAST(taxa_id AS TEXT),
                        LOWER(scientific_name),
                        LOWER(display_name)
                    ) AS species_key,
                    COUNT(*) AS detection_count
                FROM species_rows
                GROUP BY species_key
            ),
            species_distinct AS (
                SELECT DISTINCT display_name, scientific_name, common_name, taxa_id
                FROM species_rows
            ),
            ranked AS (
                SELECT
                    display_name,
                    scientific_name,
                    common_name,
                    taxa_id,
                    COALESCE(
                        CAST(taxa_id AS TEXT),
                        LOWER(scientific_name),
                        LOWER(display_name)
                    ) AS species_key,
                    ROW_NUMBER() OVER (
                        -- Group all name variants for the same species together:
                        -- first by taxa_id (most canonical), then by scientific_name,
                        -- then by the raw display_name as a last resort.
                        PARTITION BY COALESCE(
                            CAST(taxa_id AS TEXT),
                            LOWER(scientific_name),
                            LOWER(display_name)
                        )
                        ORDER BY
                            (taxa_id IS NOT NULL) DESC,
                            (scientific_name IS NOT NULL) DESC,
                            (common_name IS NOT NULL) DESC,
                            display_name ASC
                    ) AS rn
                FROM species_distinct
            )
            SELECT
                ranked.display_name,
                ranked.scientific_name,
                ranked.common_name,
                ranked.taxa_id,
                COALESCE(group_counts.detection_count, 0) AS detection_count
            FROM ranked
            LEFT JOIN group_counts ON group_counts.species_key = ranked.species_key
            WHERE ranked.rn = 1
            ORDER BY ranked.display_name ASC
            """,
            params,
        ) as cursor:
            return await cursor.fetchall()

    async def get_camera_counts(self, start_date: datetime | None = None) -> dict[str, int]:
        """Detections per camera, for the Explorer camera facet."""
        start_filter = "AND detection_time >= ?" if start_date else ""
        params = [start_date.isoformat(sep=" ")] if start_date else []
        async with self.db.execute(
            f"""
            SELECT camera_name, COUNT(*)
            FROM detections
            WHERE (is_hidden = 0 OR is_hidden IS NULL)
              {start_filter}
            GROUP BY camera_name
            ORDER BY camera_name ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows if row[0]}

    async def get_facet_totals(self, start_date: datetime | None = None) -> dict[str, int]:
        """Counts for the facets that are a flag rather than a value."""
        start_filter = "AND d.detection_time >= ?" if start_date else ""
        params = [start_date.isoformat(sep=" ")] if start_date else []
        async with self.db.execute(
            f"""
            SELECT
                COUNT(*),
                SUM(CASE WHEN f.detection_id IS NOT NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN d.audio_confirmed = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN d.video_classification_status = 'completed' THEN 1 ELSE 0 END)
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
              {start_filter}
            """,
            params,
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"total": 0, "favorites": 0, "audio_matched": 0, "video_analysed": 0}
            return {
                "total": row[0] or 0,
                "favorites": row[1] or 0,
                "audio_matched": row[2] or 0,
                "video_analysed": row[3] or 0,
            }

    async def get_unique_cameras(self, start_date: datetime | None = None) -> list[str]:
        """Get list of unique camera names, sorted alphabetically."""
        start_filter = "AND detection_time >= ?" if start_date else ""
        params = [start_date.isoformat(sep=" ")] if start_date else []
        async with self.db.execute(
            f"""
            SELECT DISTINCT camera_name
            FROM detections
            WHERE (is_hidden = 0 OR is_hidden IS NULL)
              {start_filter}
            ORDER BY camera_name ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_all_frigate_event_ids(self) -> list[str]:
        """Get all Frigate event IDs."""
        async with self.db.execute(
            "SELECT frigate_event FROM detections WHERE frigate_event NOT LIKE 'manual\\_%' ESCAPE '\\'"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def apply_manual_species_tag(
        self,
        *,
        frigate_event: str,
        display_name: str,
        category_name: str,
        scientific_name: str | None,
        common_name: str | None,
        taxa_id: int | None,
        audio_confirmed: bool,
        audio_species: str | None,
        audio_score: float | None,
    ) -> None:
        """Persist the database fields owned by a manual species correction."""
        await self.db.execute(
            """
            UPDATE detections
            SET display_name = ?, category_name = ?,
                scientific_name = ?, common_name = ?, taxa_id = ?,
                audio_confirmed = ?, audio_species = ?, audio_score = ?,
                manual_tagged = 1
            WHERE frigate_event = ?
            """,
            (
                display_name,
                category_name,
                scientific_name,
                common_name,
                taxa_id,
                int(audio_confirmed),
                audio_species,
                audio_score,
                frigate_event,
            ),
        )

    async def confirm_manual_species_tag(self, *, frigate_event: str) -> None:
        """Record a human confirmation without rewriting the stored species identity."""
        await self.db.execute(
            "UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?",
            (frigate_event,),
        )

    async def get_favorite_frigate_event_ids(self) -> set[str]:
        """Get Frigate event IDs that are marked as favorites."""
        async with self.db.execute(
            """
            SELECT d.frigate_event
            FROM detections d
            INNER JOIN detection_favorites f ON f.detection_id = d.id
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0] for row in rows}

    async def delete_by_frigate_events(self, event_ids: list[str]) -> int:
        """Delete detections by a list of Frigate event IDs."""
        if not event_ids:
            return 0
        total_deleted = 0
        chunk_size = 500
        for i in range(0, len(event_ids), chunk_size):
            chunk = event_ids[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"DELETE FROM detections WHERE frigate_event IN ({placeholders})"
            async with self.db.execute(query, chunk) as cursor:
                total_deleted += cursor.rowcount or 0
                await self.db.commit()
        return total_deleted

    # The scan re-checks what might have changed and skips what cannot have.
    # `manual_%` events are an owner's own records with no Frigate event behind
    # them: asking would 404 and mark their own observation missing. A row
    # already `missing` is skipped because Frigate does not un-retire an event,
    # so re-asking is a request that can only ever get the same answer — and on
    # a year of history against days of retention that is nearly every row.
    _STALE_FRIGATE_CANDIDATE_WHERE = """
        FROM detections
        WHERE frigate_event IS NOT NULL
          AND frigate_event NOT LIKE 'manual\\_%' ESCAPE '\\'
          AND COALESCE(frigate_status, 'present') != 'missing'
          AND (frigate_last_checked_at IS NULL OR frigate_last_checked_at < ?)
    """

    async def get_stale_frigate_check_candidates(
        self,
        *,
        limit: int,
        checked_before: datetime,
    ) -> list[dict]:
        """Detections whose upstream state has not been confirmed recently.

        Ordered so a NULL `frigate_last_checked_at` — never looked at — comes
        before a row merely checked long ago, then oldest first, so a bounded
        run always advances the least certain rows.
        """
        async with self.db.execute(
            f"""
            SELECT frigate_event, camera_name
            {self._STALE_FRIGATE_CANDIDATE_WHERE}
            ORDER BY frigate_last_checked_at IS NOT NULL, frigate_last_checked_at ASC
            LIMIT ?
            """,
            (checked_before.isoformat(sep=" "), int(limit)),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"frigate_event": row[0], "camera_name": row[1]} for row in rows]

    async def count_stale_frigate_check_candidates(self, *, checked_before: datetime) -> int:
        """How many detections a scan still has to get to."""
        async with self.db.execute(
            f"SELECT COUNT(*) {self._STALE_FRIGATE_CANDIDATE_WHERE}",
            (checked_before.isoformat(sep=" "),),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    async def mark_frigate_missing(
        self,
        frigate_event: str,
        *,
        error: str,
        checked_at: datetime | None = None,
    ) -> bool:
        checked = checked_at or utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET frigate_status = 'missing',
                frigate_missing_since = COALESCE(frigate_missing_since, ?),
                frigate_last_checked_at = ?,
                frigate_last_error = ?
            WHERE frigate_event = ?
            """,
            (checked, checked, error, frigate_event),
        )
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed > 0

    async def record_frigate_check(self, frigate_event: str, *, checked_at: datetime | None = None) -> None:
        """Record that upstream was asked about this detection and confirmed it.

        Separate from `mark_frigate_present`, which only touches rows that are
        not already cleanly present: that restores state, this records that a
        check happened. Without it a healthy row is never stamped, so it stays
        permanently stale and every scan re-asks about the same detections while
        the real backlog never moves.
        """
        await self.db.execute(
            "UPDATE detections SET frigate_last_checked_at = ? WHERE frigate_event = ?",
            ((checked_at or utc_naive_now()).isoformat(sep=" "), frigate_event),
        )
        await self.db.commit()

    async def mark_frigate_present(
        self,
        frigate_event: str,
        *,
        checked_at: datetime | None = None,
    ) -> bool:
        checked = checked_at or utc_naive_now()
        await self.db.execute(
            """
            UPDATE detections
            SET frigate_status = 'present',
                frigate_missing_since = NULL,
                frigate_last_checked_at = ?,
                frigate_last_error = NULL
            WHERE frigate_event = ?
              AND (
                  COALESCE(frigate_status, 'present') != 'present'
                  OR frigate_missing_since IS NOT NULL
                  OR frigate_last_error IS NOT NULL
              )
            """,
            (checked, frigate_event),
        )
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed > 0

    async def get_taxonomy_names(self, name: str, language: str | None = None) -> dict:
        """Get scientific and common names for a species from cache.

        Supports lookup by scientific/common names and localized common names (when
        `taxonomy_translations` exists and `language` is provided).
        """
        result = {"scientific_name": None, "common_name": None, "taxa_id": None}
        normalized_lookup = _normalize_species_lookup_name(name)

        async with self.db.execute(
            """SELECT scientific_name, COALESCE(manual_common_name, common_name), taxa_id,
                      manual_common_name
               FROM taxonomy_cache
               WHERE LOWER(scientific_name) = LOWER(?)
                  OR LOWER(common_name) = LOWER(?)
                  OR LOWER(manual_common_name) = LOWER(?)""",
            (name, name, name),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = {"scientific_name": row[0], "common_name": row[1], "taxa_id": row[2]}
                has_manual_override = bool(row[3])
            else:
                has_manual_override = False

        if (
            result["taxa_id"] is None
            and language
            and language != "en"
            and await self._table_exists("taxonomy_translations")
        ):
            async with self.db.execute(
                """SELECT tc.scientific_name, COALESCE(tc.manual_common_name, tc.common_name),
                          tc.taxa_id, tt.common_name, tc.manual_common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                   WHERE tt.language_code = ?
                     AND LOWER(tt.common_name) = LOWER(?)
                   LIMIT 1""",
                (language, name),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    result = {
                        "scientific_name": row[0],
                        "common_name": row[1] if row[4] else (row[3] or row[1]),
                        "taxa_id": row[2],
                    }
                    return result

        # Accent-insensitive fallback for localized names (e.g. "comun" vs "común").
        # This scans rows only after indexed/case-insensitive lookups miss.
        if (
            result["taxa_id"] is None
            and normalized_lookup
            and language
            and language != "en"
            and await self._table_exists("taxonomy_translations")
        ):
            async with self.db.execute(
                """SELECT tc.scientific_name, COALESCE(tc.manual_common_name, tc.common_name),
                          tc.taxa_id, tt.common_name, tc.manual_common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                   WHERE tt.language_code = ?""",
                (language,),
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if _normalize_species_lookup_name(row[3]) == normalized_lookup:
                    result = {
                        "scientific_name": row[0],
                        "common_name": row[1] if row[4] else (row[3] or row[1]),
                        "taxa_id": row[2],
                    }
                    return result

        # Language-agnostic localized fallback for repair/maintenance paths that
        # do not know the source language of the stored display name.
        if result["taxa_id"] is None and normalized_lookup and await self._table_exists("taxonomy_translations"):
            async with self.db.execute(
                """SELECT tc.scientific_name, COALESCE(tc.manual_common_name, tc.common_name),
                          tc.taxa_id, tt.common_name, tc.manual_common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id"""
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if _normalize_species_lookup_name(row[3]) == normalized_lookup:
                    result = {
                        "scientific_name": row[0],
                        "common_name": row[1] if row[4] else (row[3] or row[1]),
                        "taxa_id": row[2],
                    }
                    return result

        if result["taxa_id"] is None and normalized_lookup:
            async with self.db.execute(
                """SELECT scientific_name, COALESCE(manual_common_name, common_name),
                          taxa_id, manual_common_name FROM taxonomy_cache"""
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if (
                    _normalize_species_lookup_name(row[0]) == normalized_lookup
                    or _normalize_species_lookup_name(row[1]) == normalized_lookup
                ):
                    result = {"scientific_name": row[0], "common_name": row[1], "taxa_id": row[2]}
                    has_manual_override = bool(row[3])
                    break

        if (
            result["taxa_id"] is not None
            and not has_manual_override
            and language
            and language != "en"
            and await self._table_exists("taxonomy_translations")
        ):
            async with self.db.execute(
                """SELECT common_name FROM taxonomy_translations
                   WHERE taxa_id = ? AND language_code = ?
                   LIMIT 1""",
                (result["taxa_id"], language),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    result["common_name"] = row[0]

        return result

    async def update_common_name_for_scientific_name(self, scientific_name: str, common_name: str | None) -> None:
        """Apply one effective taxonomy name to existing detections."""
        await self.db.execute(
            """UPDATE detections SET common_name = ?
               WHERE LOWER(scientific_name) = LOWER(?)""",
            (common_name, scientific_name),
        )

    async def resolve_species_aliases(self, species_name: str, language: str | None = None) -> dict:
        """Resolve a species identifier into taxonomy metadata and matching display labels.

        Returns a dict with:
        - scientific_name / common_name / taxa_id
        - display_labels: distinct `detections.display_name` values representing the species
        - match_names: names suitable for matching across display/scientific columns
        """
        taxonomy = await self.get_taxonomy_names(species_name, language=language)
        taxa_id = taxonomy.get("taxa_id")
        scientific_name = taxonomy.get("scientific_name")
        common_name = taxonomy.get("common_name")

        match_names: list[str] = []
        for candidate in [species_name, scientific_name, common_name]:
            if not candidate:
                continue
            candidate = str(candidate).strip()
            if candidate and candidate not in match_names:
                match_names.append(candidate)

        # If we have a taxa_id and a non-English request, also include the English common name
        # so display-label queries can match historical rows when label style changes.
        if taxa_id is not None:
            async with self.db.execute(
                "SELECT scientific_name, common_name FROM taxonomy_cache WHERE taxa_id = ? LIMIT 1", (taxa_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    for candidate in [row[0], row[1]]:
                        if candidate and candidate not in match_names:
                            match_names.append(candidate)
                    scientific_name = scientific_name or row[0]
                    # Preserve localized common_name if already resolved
                    if common_name is None:
                        common_name = row[1]

        display_labels: list[str] = []
        if taxa_id is not None:
            lowered_names = [n for n in match_names if n]
            if lowered_names:
                placeholders = ",".join(["?"] * len(lowered_names))
                async with self.db.execute(
                    f"""SELECT DISTINCT display_name
                        FROM detections
                        WHERE taxa_id = ?
                           OR LOWER(display_name) IN ({placeholders})
                           OR LOWER(scientific_name) IN ({placeholders})
                           OR LOWER(common_name) IN ({placeholders})
                        ORDER BY display_name ASC""",
                    (
                        taxa_id,
                        *[n.lower() for n in lowered_names],
                        *[n.lower() for n in lowered_names],
                        *[n.lower() for n in lowered_names],
                    ),
                ) as cursor:
                    display_labels = [row[0] for row in await cursor.fetchall() if row and row[0]]
        elif match_names:
            placeholders = ",".join(["?"] * len(match_names))
            lowered = [n.lower() for n in match_names]
            async with self.db.execute(
                f"""SELECT DISTINCT display_name
                    FROM detections
                    WHERE LOWER(display_name) IN ({placeholders})
                       OR LOWER(scientific_name) IN ({placeholders})
                       OR LOWER(common_name) IN ({placeholders})
                    ORDER BY display_name ASC""",
                (*lowered, *lowered, *lowered),
            ) as cursor:
                display_labels = [row[0] for row in await cursor.fetchall() if row and row[0]]

        if not display_labels and species_name:
            display_labels = [species_name]

        return {
            "scientific_name": scientific_name,
            "common_name": common_name,
            "taxa_id": taxa_id,
            "display_labels": display_labels,
            "match_names": match_names,
        }

    async def delete_older_than(
        self,
        cutoff_date: datetime,
        chunk_size: int = 1000,
        preserve_favorites: bool = False,
    ) -> int:
        """Delete detections older than the cutoff date in chunks to avoid locking."""
        total_deleted = 0
        cutoff_str = cutoff_date.isoformat(sep=" ")

        while True:
            # Delete a chunk of rows
            # We use the rowid (implicit or explicit) or limit if supported by the build
            # Standard SQLite DELETE LIMIT requires compilation option, so we use subquery
            query = """
                DELETE FROM detections
                WHERE id IN (
                    SELECT d.id
                    FROM detections d
                    LEFT JOIN detection_favorites f ON f.detection_id = d.id
                    WHERE d.detection_time < ?
            """
            if preserve_favorites:
                query += " AND f.detection_id IS NULL"
            query += """
                    LIMIT ?
                )
            """

            async with self.db.execute(query, (cutoff_str, chunk_size)) as cursor:
                if cursor.rowcount == 0:
                    break
                total_deleted += cursor.rowcount
                await self.db.commit()
                # Brief sleep to yield the event loop and allow other queries
                await asyncio.sleep(0.01)

        return total_deleted

    async def delete_audio_detections_older_than(
        self,
        cutoff_date: datetime,
        chunk_size: int = 1000,
    ) -> int:
        """Delete BirdNET-Go audio detections older than the cutoff date in chunks.

        Audio detections have no favorites/soft-delete concept, so this is a
        straight age-based purge keyed on the ``timestamp`` column. Chunked to
        mirror ``delete_older_than`` and avoid long write locks.
        """
        total_deleted = 0
        cutoff_str = serialize_storage_datetime(cutoff_date)

        while True:
            query = """
                DELETE FROM audio_detections
                WHERE id IN (
                    SELECT id
                    FROM audio_detections
                    WHERE timestamp < ?
                    LIMIT ?
                )
            """
            async with self.db.execute(query, (cutoff_str, chunk_size)) as cursor:
                if cursor.rowcount == 0:
                    break
                total_deleted += cursor.rowcount
                await self.db.commit()
                # Brief sleep to yield the event loop and allow other queries
                await asyncio.sleep(0.01)

        return total_deleted

    async def delete_all(self) -> int:
        """Delete ALL detections. Use with caution."""
        async with self.db.execute("DELETE FROM detections") as cursor:
            count = cursor.rowcount
            await self.db.commit()
            return count

    async def get_unknown_detections(self, *, limit: int | None = None) -> list[Detection]:
        """Get unresolved detections labeled as 'Unknown Bird', newest first."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name="Unknown Bird",
        )
        query_params = list(params)
        query = f"""
            SELECT {DETECTION_SELECT_COLUMNS}
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
            {join_sql}
            WHERE {species_condition}
              AND COALESCE(d.video_classification_status, '') NOT IN ('pending', 'processing')
              AND COALESCE(d.video_classification_error, '') NOT IN ('clip_not_retained', 'frigate_retention_expired')
            ORDER BY d.detection_time DESC, d.id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            query_params.append(max(1, int(limit)))
        async with self.db.execute(query, query_params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]

    async def get_oldest_detection_date(self) -> datetime | None:
        """Get the date of the oldest detection."""
        async with self.db.execute("SELECT MIN(detection_time) FROM detections") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return _parse_datetime(row[0])
            return None

    async def get_detection_time_bounds(self) -> tuple[datetime | None, datetime | None]:
        """Return (min_detection_time, max_detection_time) across all detections."""
        async with self.db.execute(
            "SELECT MIN(detection_time), MAX(detection_time) FROM detections WHERE (is_hidden = 0 OR is_hidden IS NULL)"
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return (None, None)
            return (_parse_datetime(row[0]) if row[0] else None, _parse_datetime(row[1]) if row[1] else None)

    async def get_timebucket_counts_hourly(self, start: datetime, end: datetime) -> dict[str, int]:
        """Counts grouped by UTC hour bucket within [start, end)."""
        query = """
            SELECT strftime('%Y-%m-%dT%H:00:00Z', detection_time) as bucket, COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY bucket
            ORDER BY bucket ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()
        return {row[0]: int(row[1] or 0) for row in rows if row and row[0]}

    async def get_timebucket_counts_halfday(self, start: datetime, end: datetime) -> dict[str, int]:
        """Counts grouped by half-day (AM/PM) within [start, end).

        Bucket key is an ISO timestamp string for the bucket start in UTC:
        - YYYY-MM-DDT00:00:00Z for AM
        - YYYY-MM-DDT12:00:00Z for PM
        """
        query = """
            SELECT
                date(detection_time) as d,
                CASE WHEN CAST(strftime('%H', detection_time) AS integer) < 12 THEN 0 ELSE 12 END as hour_start,
                COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY d, hour_start
            ORDER BY d ASC, hour_start ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()
        out: dict[str, int] = {}
        for d, hour_start, c in rows:
            if not d:
                continue
            hh = "00" if int(hour_start or 0) == 0 else "12"
            key = f"{d}T{hh}:00:00Z"
            out[key] = int(c or 0)
        return out

    async def get_timebucket_counts_daily(self, start: datetime, end: datetime) -> dict[str, int]:
        """Counts grouped by day within [start, end). Key is YYYY-MM-DD."""
        query = """
            SELECT date(detection_time) as d, COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY d
            ORDER BY d ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()
        return {row[0]: int(row[1] or 0) for row in rows if row and row[0]}

    async def get_timebucket_counts_monthly(self, start: datetime, end: datetime) -> dict[str, int]:
        """Counts grouped by month within [start, end). Key is YYYY-MM-01."""
        query = """
            SELECT strftime('%Y-%m-01', detection_time) as m, COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY m
            ORDER BY m ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()
        return {row[0]: int(row[1] or 0) for row in rows if row and row[0]}

    async def get_timebucket_metrics(self, start: datetime, end: datetime, bucket: str) -> dict[str, dict]:
        """Bucketed aggregate metrics for timeline charts.

        Returns per-bucket totals:
        - count
        - unique_species
        - avg_confidence
        """
        if bucket == "hour":
            query = """
                SELECT
                    strftime('%Y-%m-%dT%H:00:00Z', d.detection_time) as bucket,
                    COUNT(*) as c,
                    COUNT(DISTINCT COALESCE(
                        CAST(d.taxa_id AS TEXT),
                        LOWER(d.scientific_name),
                        (
                            SELECT LOWER(tc.scientific_name)
                            FROM taxonomy_cache tc
                            WHERE LOWER(d.display_name) = LOWER(tc.scientific_name)
                               OR LOWER(d.display_name) = LOWER(tc.common_name)
                            LIMIT 1
                        ),
                        LOWER(d.display_name)
                    )) as unique_species,
                    AVG(d.score) as avg_confidence
                FROM detections d
                WHERE d.detection_time >= ? AND d.detection_time < ?
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                GROUP BY bucket
                ORDER BY bucket ASC
            """
            params = (start, end)
        elif bucket == "halfday":
            query = """
                SELECT
                    date(d.detection_time) as d,
                    CASE WHEN CAST(strftime('%H', d.detection_time) AS integer) < 12 THEN 0 ELSE 12 END as hour_start,
                    COUNT(*) as c,
                    COUNT(DISTINCT COALESCE(
                        CAST(d.taxa_id AS TEXT),
                        LOWER(d.scientific_name),
                        (
                            SELECT LOWER(tc.scientific_name)
                            FROM taxonomy_cache tc
                            WHERE LOWER(d.display_name) = LOWER(tc.scientific_name)
                               OR LOWER(d.display_name) = LOWER(tc.common_name)
                            LIMIT 1
                        ),
                        LOWER(d.display_name)
                    )) as unique_species,
                    AVG(d.score) as avg_confidence
                FROM detections d
                WHERE d.detection_time >= ? AND d.detection_time < ?
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                GROUP BY d, hour_start
                ORDER BY d ASC, hour_start ASC
            """
            params = (start, end)
        elif bucket == "day":
            query = """
                SELECT
                    date(d.detection_time) as d,
                    COUNT(*) as c,
                    COUNT(DISTINCT COALESCE(
                        CAST(d.taxa_id AS TEXT),
                        LOWER(d.scientific_name),
                        (
                            SELECT LOWER(tc.scientific_name)
                            FROM taxonomy_cache tc
                            WHERE LOWER(d.display_name) = LOWER(tc.scientific_name)
                               OR LOWER(d.display_name) = LOWER(tc.common_name)
                            LIMIT 1
                        ),
                        LOWER(d.display_name)
                    )) as unique_species,
                    AVG(d.score) as avg_confidence
                FROM detections d
                WHERE d.detection_time >= ? AND d.detection_time < ?
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                GROUP BY d
                ORDER BY d ASC
            """
            params = (start, end)
        else:
            query = """
                SELECT
                    strftime('%Y-%m-01', d.detection_time) as m,
                    COUNT(*) as c,
                    COUNT(DISTINCT COALESCE(
                        CAST(d.taxa_id AS TEXT),
                        LOWER(d.scientific_name),
                        (
                            SELECT LOWER(tc.scientific_name)
                            FROM taxonomy_cache tc
                            WHERE LOWER(d.display_name) = LOWER(tc.scientific_name)
                               OR LOWER(d.display_name) = LOWER(tc.common_name)
                            LIMIT 1
                        ),
                        LOWER(d.display_name)
                    )) as unique_species,
                    AVG(d.score) as avg_confidence
                FROM detections d
                WHERE d.detection_time >= ? AND d.detection_time < ?
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                GROUP BY m
                ORDER BY m ASC
            """
            params = (start, end)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        out: dict[str, dict] = {}
        for row in rows:
            if bucket == "halfday":
                d = row[0]
                hour_start = int(row[1] or 0)
                if not d:
                    continue
                hh = "00" if hour_start == 0 else "12"
                key = f"{d}T{hh}:00:00Z"
                c = row[2]
                unique_species = row[3]
                avg_confidence = row[4]
            elif bucket == "day":
                d = row[0]
                if not d:
                    continue
                key = f"{d}T00:00:00Z"
                c = row[1]
                unique_species = row[2]
                avg_confidence = row[3]
            elif bucket == "month":
                m = row[0]
                if not m:
                    continue
                key = f"{m}T00:00:00Z"
                c = row[1]
                unique_species = row[2]
                avg_confidence = row[3]
            else:
                key = row[0]
                if not key:
                    continue
                c = row[1]
                unique_species = row[2]
                avg_confidence = row[3]

            out[key] = {
                "count": int(c or 0),
                "unique_species": int(unique_species or 0),
                "avg_confidence": float(avg_confidence) if avg_confidence is not None else None,
            }
        return out

    async def get_timebucket_species_counts(
        self,
        start: datetime,
        end: datetime,
        bucket: str,
        species_map: dict[str, list[str]],
    ) -> dict[str, dict[str, int]]:
        """Counts by timeline bucket for selected species labels.

        species_map maps output species names to one or more display_name labels.
        """
        if not species_map:
            return {}

        selected_labels: set[str] = set()
        reverse_map: dict[str, list[str]] = {}
        for output_species, labels in species_map.items():
            for label in labels:
                selected_labels.add(label)
                reverse_map.setdefault(label, []).append(output_species)
        if not selected_labels:
            return {}

        placeholders = ",".join(["?"] * len(selected_labels))
        labels_params = tuple(selected_labels)

        if bucket == "hour":
            query = f"""
                SELECT
                    strftime('%Y-%m-%dT%H:00:00Z', detection_time) as bucket_key,
                    display_name,
                    scientific_name,
                    COUNT(*) as c
                FROM detections
                WHERE detection_time >= ? AND detection_time < ?
                  AND (is_hidden = 0 OR is_hidden IS NULL)
                  AND (display_name IN ({placeholders}) OR scientific_name IN ({placeholders}))
                GROUP BY bucket_key, display_name, scientific_name
                ORDER BY bucket_key ASC
            """
            params = (start, end, *labels_params, *labels_params)
        elif bucket == "halfday":
            query = f"""
                SELECT
                    date(detection_time) as d,
                    CASE WHEN CAST(strftime('%H', detection_time) AS integer) < 12 THEN 0 ELSE 12 END as hour_start,
                    display_name,
                    scientific_name,
                    COUNT(*) as c
                FROM detections
                WHERE detection_time >= ? AND detection_time < ?
                  AND (is_hidden = 0 OR is_hidden IS NULL)
                  AND (display_name IN ({placeholders}) OR scientific_name IN ({placeholders}))
                GROUP BY d, hour_start, display_name, scientific_name
                ORDER BY d ASC, hour_start ASC
            """
            params = (start, end, *labels_params, *labels_params)
        elif bucket == "day":
            query = f"""
                SELECT
                    date(detection_time) as d,
                    display_name,
                    scientific_name,
                    COUNT(*) as c
                FROM detections
                WHERE detection_time >= ? AND detection_time < ?
                  AND (is_hidden = 0 OR is_hidden IS NULL)
                  AND (display_name IN ({placeholders}) OR scientific_name IN ({placeholders}))
                GROUP BY d, display_name, scientific_name
                ORDER BY d ASC
            """
            params = (start, end, *labels_params, *labels_params)
        else:
            query = f"""
                SELECT
                    strftime('%Y-%m-01', detection_time) as m,
                    display_name,
                    scientific_name,
                    COUNT(*) as c
                FROM detections
                WHERE detection_time >= ? AND detection_time < ?
                  AND (is_hidden = 0 OR is_hidden IS NULL)
                  AND (display_name IN ({placeholders}) OR scientific_name IN ({placeholders}))
                GROUP BY m, display_name, scientific_name
                ORDER BY m ASC
            """
            params = (start, end, *labels_params, *labels_params)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        out: dict[str, dict[str, int]] = {}
        for row in rows:
            if bucket == "halfday":
                d = row[0]
                hour_start = int(row[1] or 0)
                label = row[2]
                sci_name = row[3]
                count = int(row[4] or 0)
                if not d:
                    continue
                hh = "00" if hour_start == 0 else "12"
                bucket_key = f"{d}T{hh}:00:00Z"
            elif bucket == "day":
                d = row[0]
                label = row[1]
                sci_name = row[2]
                count = int(row[3] or 0)
                if not d:
                    continue
                bucket_key = f"{d}T00:00:00Z"
            elif bucket == "month":
                m = row[0]
                label = row[1]
                sci_name = row[2]
                count = int(row[3] or 0)
                if not m:
                    continue
                bucket_key = f"{m}T00:00:00Z"
            else:
                bucket_key = row[0]
                label = row[1]
                sci_name = row[2]
                count = int(row[3] or 0)
                if not bucket_key:
                    continue

            # We need to find which "output species" this row belongs to.
            # It could match by display_name OR by scientific_name.
            target_species_set: set[str] = set()
            if label and label in reverse_map:
                target_species_set.update(reverse_map[label])
            if sci_name and sci_name in reverse_map:
                target_species_set.update(reverse_map[sci_name])

            for output_species in target_species_set:
                out.setdefault(bucket_key, {})
                out[bucket_key][output_species] = out[bucket_key].get(output_species, 0) + count
        return out

    async def get_timebucket_species_counts_for_names(
        self,
        start: datetime,
        end: datetime,
        bucket: str,
        species_names: list[str],
        *,
        language: str | None = None,
    ) -> dict[str, dict[str, int]]:
        """Counts by timeline bucket for canonical species selections.

        Uses the same canonical/unknown matching rules as the main species queries,
        so selections like "Unknown Bird" also include hidden noncanonical labels.
        """
        if not species_names:
            return {}

        out: dict[str, dict[str, int]] = {}

        for species_name in species_names:
            name = str(species_name or "").strip()
            if not name:
                continue

            join_sql, species_condition, species_params = await self._canonical_species_query_parts(
                detection_alias="d",
                species_name=name,
            )

            if bucket == "hour":
                query = f"""
                    SELECT
                        strftime('%Y-%m-%dT%H:00:00Z', d.detection_time) as bucket_key,
                        COUNT(*) as c
                    FROM detections d
                    {join_sql}
                    WHERE d.detection_time >= ? AND d.detection_time < ?
                      AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                      AND {species_condition}
                    GROUP BY bucket_key
                    ORDER BY bucket_key ASC
                """
            elif bucket == "halfday":
                query = f"""
                    SELECT
                        date(d.detection_time) as d,
                        CASE WHEN CAST(strftime('%H', d.detection_time) AS integer) < 12 THEN 0 ELSE 12 END as hour_start,
                        COUNT(*) as c
                    FROM detections d
                    {join_sql}
                    WHERE d.detection_time >= ? AND d.detection_time < ?
                      AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                      AND {species_condition}
                    GROUP BY d, hour_start
                    ORDER BY d ASC, hour_start ASC
                """
            elif bucket == "day":
                query = f"""
                    SELECT
                        date(d.detection_time) as d,
                        COUNT(*) as c
                    FROM detections d
                    {join_sql}
                    WHERE d.detection_time >= ? AND d.detection_time < ?
                      AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                      AND {species_condition}
                    GROUP BY d
                    ORDER BY d ASC
                """
            else:
                query = f"""
                    SELECT
                        strftime('%Y-%m-01', d.detection_time) as m,
                        COUNT(*) as c
                    FROM detections d
                    {join_sql}
                    WHERE d.detection_time >= ? AND d.detection_time < ?
                      AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                      AND {species_condition}
                    GROUP BY m
                    ORDER BY m ASC
                """

            params = [start, end, *species_params]
            async with self.db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                if bucket == "halfday":
                    d = row[0]
                    hour_start = int(row[1] or 0)
                    count = int(row[2] or 0)
                    if not d:
                        continue
                    hh = "00" if hour_start == 0 else "12"
                    bucket_key = f"{d}T{hh}:00:00Z"
                elif bucket == "day":
                    d = row[0]
                    count = int(row[1] or 0)
                    if not d:
                        continue
                    bucket_key = f"{d}T00:00:00Z"
                elif bucket == "month":
                    m = row[0]
                    count = int(row[1] or 0)
                    if not m:
                        continue
                    bucket_key = f"{m}T00:00:00Z"
                else:
                    bucket_key = row[0]
                    count = int(row[1] or 0)
                    if not bucket_key:
                        continue

                out.setdefault(bucket_key, {})
                out[bucket_key][name] = out[bucket_key].get(name, 0) + count

        return out

    async def get_activity_heatmap_utc_hourly_counts(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, int]]:
        """Return visible detection counts grouped by UTC hour buckets."""
        query = """
            SELECT
                strftime('%Y-%m-%d %H:00:00', detection_time) as bucket_start,
                COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY bucket_start
            ORDER BY bucket_start ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()

        out: list[tuple[datetime, int]] = []
        for row in rows:
            bucket_start = _parse_datetime(row[0])
            count = int(row[1] or 0)
            if count <= 0:
                continue
            out.append((bucket_start, count))
        return out

    async def get_species_leaderboard_base(self) -> list[dict]:
        """Get leaderboard base stats per species with taxonomy and time bounds."""
        canonical_key = self._canonical_key_sql()
        taxonomy_join = self._taxonomy_join_sql()
        query = f"""
            SELECT 
                {canonical_key} as unified_id,
                COUNT(*) as total_count, 
                COALESCE(MAX(tc.scientific_name), MAX(d.scientific_name)) as scientific_name,
                COALESCE(MAX(tc.manual_common_name), MAX(d.common_name), MAX(tc.common_name)) as common_name,
                MAX(d.display_name) as display_name,
                COALESCE(MAX(d.taxa_id), MAX(tc.taxa_id)) as taxa_id,
                MIN(d.detection_time) as first_seen,
                MAX(d.detection_time) as last_seen,
                AVG(d.score) as avg_confidence,
                MAX(d.score) as max_confidence,
                MIN(d.score) as min_confidence,
                COUNT(DISTINCT d.camera_name) as camera_count,
                MAX(d.species_id) as species_id,
                MAX(tc.manual_common_name) as manual_common_name
            FROM detections d
            {taxonomy_join}
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
            GROUP BY {canonical_key}
            ORDER BY total_count DESC
        """
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "species": row[4],
                    "count": row[1],
                    "scientific_name": row[2],
                    "common_name": row[3],
                    "taxa_id": row[5],
                    # The grouping key itself, so callers join on it rather than
                    # rebuilding the same rule and drifting out of step.
                    "unified_key": row[0],
                    "first_seen": _parse_datetime(row[6]) if row[6] else None,
                    "last_seen": _parse_datetime(row[7]) if row[7] else None,
                    "avg_confidence": row[8] or 0.0,
                    "max_confidence": row[9] or 0.0,
                    "min_confidence": row[10] or 0.0,
                    "camera_count": row[11] or 0,
                    # The group's catalogue identity, so a name can be chosen
                    # for the group rather than taken from one of its rows.
                    # Every row in a group shares it, so MAX is just "the one".
                    "species_id": int(row[12]) if row[12] is not None else None,
                    # An owner rename still wins over any catalogue name.
                    "manual_common_name": row[13],
                }
                for row in rows
            ]

    async def get_species_leaderboard_window(
        self,
        window_start: datetime,
        window_end: datetime,
        prev_start: datetime,
        prev_end: datetime,
    ) -> list[dict]:
        """Get leaderboard stats for a rolling window and the prior window.

        Notes:
        - Uses detection_time timestamps (not rollups) so it supports 24h windows.
        - Returns rows for any species that appears in either window; caller can filter to window_count > 0.
        """
        canonical_key = self._canonical_key_sql()
        taxonomy_join = self._taxonomy_join_sql()
        query = f"""
            SELECT
                {canonical_key} as unified_id,
                COALESCE(MAX(tc.scientific_name), MAX(d.scientific_name)) as scientific_name,
                COALESCE(MAX(tc.manual_common_name), MAX(d.common_name), MAX(tc.common_name)) as common_name,
                MAX(d.display_name) as display_name,
                COALESCE(MAX(d.taxa_id), MAX(tc.taxa_id)) as taxa_id,

                SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as window_count,
                SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as prev_count,

                MIN(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_first_seen,
                MAX(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_last_seen,

                AVG(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.score ELSE NULL END) as window_avg_confidence,
                COUNT(DISTINCT CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.camera_name ELSE NULL END) as window_camera_count
            FROM detections d
            {taxonomy_join}
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
              AND d.detection_time >= ?
              AND d.detection_time < ?
            GROUP BY {canonical_key}
        """
        params = (
            window_start,
            window_end,
            prev_start,
            prev_end,
            window_start,
            window_end,
            window_start,
            window_end,
            window_start,
            window_end,
            window_start,
            window_end,
            prev_start,
            window_end,
        )
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "species": row[3],
                "scientific_name": row[1],
                "common_name": row[2],
                "taxa_id": row[4],
                "window_count": int(row[5] or 0),
                "prev_count": int(row[6] or 0),
                "window_first_seen": _parse_datetime(row[7]) if row[7] else None,
                "window_last_seen": _parse_datetime(row[8]) if row[8] else None,
                "window_avg_confidence": float(row[9] or 0.0),
                "window_camera_count": int(row[10] or 0),
            }
            for row in rows
        ]

    async def get_species_leaderboard_window_for_labels(
        self,
        labels: list[str],
        window_start: datetime,
        window_end: datetime,
        prev_start: datetime,
        prev_end: datetime,
    ) -> dict | None:
        """Aggregate window stats across a list of labels (e.g. unknown-bird label set)."""
        if not labels:
            return None
        placeholders = ",".join(["?"] * len(labels))
        query = f"""
            SELECT
                SUM(CASE WHEN detection_time >= ? AND detection_time < ? THEN 1 ELSE 0 END) as window_count,
                SUM(CASE WHEN detection_time >= ? AND detection_time < ? THEN 1 ELSE 0 END) as prev_count,
                MIN(CASE WHEN detection_time >= ? AND detection_time < ? THEN detection_time ELSE NULL END) as window_first_seen,
                MAX(CASE WHEN detection_time >= ? AND detection_time < ? THEN detection_time ELSE NULL END) as window_last_seen,
                AVG(CASE WHEN detection_time >= ? AND detection_time < ? THEN score ELSE NULL END) as window_avg_confidence,
                COUNT(DISTINCT CASE WHEN detection_time >= ? AND detection_time < ? THEN camera_name ELSE NULL END) as window_camera_count
            FROM detections
            WHERE (is_hidden = 0 OR is_hidden IS NULL)
              AND display_name IN ({placeholders})
              AND detection_time >= ?
              AND detection_time < ?
        """
        params = (
            window_start,
            window_end,
            prev_start,
            prev_end,
            window_start,
            window_end,
            window_start,
            window_end,
            window_start,
            window_end,
            window_start,
            window_end,
            *labels,
            prev_start,
            window_end,
        )
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            window_count = int(row[0] or 0)
            prev_count = int(row[1] or 0)
            if window_count == 0 and prev_count == 0:
                return None
            return {
                "window_count": window_count,
                "prev_count": prev_count,
                "window_first_seen": _parse_datetime(row[2]) if row[2] else None,
                "window_last_seen": _parse_datetime(row[3]) if row[3] else None,
                "window_avg_confidence": float(row[4] or 0.0),
                "window_camera_count": int(row[5] or 0),
            }

    async def get_latest_rollup_date(self) -> date | None:
        async with self.db.execute("SELECT MAX(rollup_date) FROM species_daily_rollup") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return datetime.strptime(row[0], "%Y-%m-%d").date()
            return None

    async def ensure_recent_rollups(self, lookback_days: int = 90) -> None:
        """Ensure daily rollups exist for the recent lookback window."""
        today = datetime.utcnow().date()
        latest = await self.get_latest_rollup_date()
        if latest is None:
            start_date = today - timedelta(days=lookback_days)
        else:
            start_date = latest + timedelta(days=1)
        if start_date > today:
            return
        await self.upsert_daily_rollups(start_date, today)

    async def upsert_daily_rollups(self, start_date: date, end_date: date) -> None:
        """Rebuild rollups between start_date and end_date (inclusive)."""
        rows, rollup_has_canonical_columns = await self._build_daily_rollup_rows(start_date, end_date)
        if not rows:
            return
        await self._insert_daily_rollup_rows(
            "species_daily_rollup",
            rows,
            canonical=rollup_has_canonical_columns,
            upsert=True,
        )
        await self.db.commit()

    async def _build_daily_rollup_rows(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[list[tuple], bool]:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        rollup_columns = await self._table_columns("species_daily_rollup")
        rollup_has_canonical_columns = "canonical_key" in rollup_columns
        if await self._table_exists("taxonomy_cache"):
            query = """
                WITH enriched AS (
                    SELECT
                        date(d.detection_time) as rollup_date,
                        d.display_name,
                        COALESCE(d.scientific_name, tc.scientific_name) as scientific_name,
                        COALESCE(d.common_name, tc.common_name) as common_name,
                        COALESCE(d.taxa_id, tc.taxa_id) as taxa_id,
                        d.camera_name,
                        d.score,
                        d.detection_time,
                        d.species_id,
                        {canonical_key} as canonical_key
                    FROM detections d
                    {taxonomy_join}
                    WHERE d.detection_time >= ? AND d.detection_time < ?
                      AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                )
                SELECT
                    rollup_date,
                    canonical_key,
                    COALESCE(
                        MAX(CASE
                            WHEN common_name IS NOT NULL AND LOWER(display_name) = LOWER(common_name) THEN display_name
                            END),
                        MAX(common_name),
                        MIN(display_name)
                    ) as display_name,
                    MAX(scientific_name) as scientific_name,
                    MAX(common_name) as common_name,
                    MAX(taxa_id) as taxa_id,
                    COUNT(*) as detection_count,
                    COUNT(DISTINCT camera_name) as camera_count,
                    AVG(score) as avg_confidence,
                    MAX(score) as max_confidence,
                    MIN(score) as min_confidence,
                    MIN(detection_time) as first_seen,
                    MAX(detection_time) as last_seen,
                    -- Stored alongside the key rather than only inside it, so
                    -- the column and the key cannot disagree and the identity
                    -- is joinable without parsing a string.
                    MAX(species_id) as species_id
                FROM enriched
                GROUP BY rollup_date, canonical_key
            """.format(
                canonical_key=self._canonical_key_sql(detection_alias="d", taxonomy_alias="tc"),
                taxonomy_join=self._taxonomy_join_sql(detection_alias="d", taxonomy_alias="tc"),
            )
        else:
            query = """
                WITH enriched AS (
                    SELECT
                        date(detection_time) as rollup_date,
                        display_name,
                        scientific_name,
                        common_name,
                        taxa_id,
                        camera_name,
                        score,
                        detection_time,
                        species_id,
                        -- Same key as the joined branch above, so an install
                        -- without a taxonomy cache does not end up with a
                        -- differently-keyed rollup.
                        COALESCE(
                            'species:' || CAST(species_id AS TEXT),
                            'taxon:' || CAST(taxa_id AS TEXT),
                            'name:' || LOWER(scientific_name),
                            'label:' || LOWER(display_name)
                        ) as canonical_key
                    FROM detections
                    WHERE detection_time >= ? AND detection_time < ?
                      AND (is_hidden = 0 OR is_hidden IS NULL)
                )
                SELECT
                    rollup_date,
                    canonical_key,
                    COALESCE(
                        MAX(CASE
                            WHEN common_name IS NOT NULL AND LOWER(display_name) = LOWER(common_name) THEN display_name
                            END),
                        MAX(common_name),
                        MIN(display_name)
                    ) as display_name,
                    MAX(scientific_name) as scientific_name,
                    MAX(common_name) as common_name,
                    MAX(taxa_id) as taxa_id,
                    COUNT(*) as detection_count,
                    COUNT(DISTINCT camera_name) as camera_count,
                    AVG(score) as avg_confidence,
                    MAX(score) as max_confidence,
                    MIN(score) as min_confidence,
                    MIN(detection_time) as first_seen,
                    MAX(detection_time) as last_seen,
                    -- Stored alongside the key rather than only inside it, so
                    -- the column and the key cannot disagree and the identity
                    -- is joinable without parsing a string.
                    MAX(species_id) as species_id
                FROM enriched
                GROUP BY rollup_date, canonical_key
            """
        async with self.db.execute(query, (start_dt, end_dt)) as cursor:
            rows = await cursor.fetchall()
        return rows, rollup_has_canonical_columns

    async def _insert_daily_rollup_rows(
        self,
        table_name: str,
        rows: list[tuple],
        *,
        canonical: bool,
        upsert: bool = False,
    ) -> None:
        if not rows:
            return
        if canonical:
            conflict_sql = ""
            if upsert:
                conflict_sql = """
                    ON CONFLICT(rollup_date, canonical_key) DO UPDATE SET
                        display_name=excluded.display_name,
                        scientific_name=excluded.scientific_name,
                        common_name=excluded.common_name,
                        taxa_id=excluded.taxa_id,
                        detection_count=excluded.detection_count,
                        camera_count=excluded.camera_count,
                        avg_confidence=excluded.avg_confidence,
                        max_confidence=excluded.max_confidence,
                        min_confidence=excluded.min_confidence,
                        first_seen=excluded.first_seen,
                        last_seen=excluded.last_seen,
                        species_id=excluded.species_id
                """
            await self.db.executemany(
                f"""INSERT INTO {table_name}
                        (rollup_date, canonical_key, display_name, scientific_name, common_name, taxa_id,
                         detection_count, camera_count, avg_confidence, max_confidence, min_confidence, first_seen,
                         last_seen, species_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    {conflict_sql}""",
                rows,
            )
        else:
            legacy_rows = [(row[0], row[2], row[6], row[7], row[8], row[9], row[10], row[11], row[12]) for row in rows]
            conflict_sql = ""
            if upsert:
                conflict_sql = """
                    ON CONFLICT(rollup_date, display_name) DO UPDATE SET
                        detection_count=excluded.detection_count,
                        camera_count=excluded.camera_count,
                        avg_confidence=excluded.avg_confidence,
                        max_confidence=excluded.max_confidence,
                        min_confidence=excluded.min_confidence,
                        first_seen=excluded.first_seen,
                        last_seen=excluded.last_seen
                """
            await self.db.executemany(
                f"""INSERT INTO {table_name}
                       (rollup_date, display_name, detection_count, camera_count,
                        avg_confidence, max_confidence, min_confidence, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    {conflict_sql}""",
                legacy_rows,
            )

    async def _clone_table_sql(self, source_table: str, target_table: str) -> str:
        async with self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (source_table,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row or not row[0]:
            raise RuntimeError(f"missing table schema for {source_table}")

        cloned_sql = re.sub(
            rf"^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)([`\"]?){re.escape(source_table)}\2",
            rf"\1{target_table}",
            row[0],
            count=1,
            flags=re.IGNORECASE,
        )
        if cloned_sql == row[0]:
            raise RuntimeError(f"unable to clone schema for {source_table}")
        return cloned_sql

    async def _table_index_sql(self, table_name: str) -> list[str]:
        async with self.db.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = ?
              AND sql IS NOT NULL
            ORDER BY name
            """,
            (table_name,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows if row and row[0]]

    async def rebuild_all_rollups(self, start_date: date, end_date: date) -> int:
        rows, rollup_has_canonical_columns = await self._build_daily_rollup_rows(start_date, end_date)
        rebuild_table = "species_daily_rollup_rebuild"
        rebuild_sql = await self._clone_table_sql("species_daily_rollup", rebuild_table)
        index_sql = await self._table_index_sql("species_daily_rollup")
        await self.db.execute("BEGIN")
        try:
            await self.db.execute(f"DROP TABLE IF EXISTS {rebuild_table}")
            await self.db.execute(rebuild_sql)

            await self._insert_daily_rollup_rows(
                rebuild_table,
                rows,
                canonical=rollup_has_canonical_columns,
            )

            await self.db.execute("ALTER TABLE species_daily_rollup RENAME TO species_daily_rollup_backup")
            await self.db.execute(f"ALTER TABLE {rebuild_table} RENAME TO species_daily_rollup")
            await self.db.execute("DROP TABLE species_daily_rollup_backup")
            for statement in index_sql:
                await self.db.execute(statement)

            await self.db.commit()
            return len(rows)
        except Exception:
            await self.db.rollback()
            raise

    async def get_total_daily_counts(self, days: int = 30) -> list[dict]:
        """Get total detection counts per day for the last N days (inclusive)."""
        if days <= 0:
            return []
        query = """
            SELECT rollup_date, SUM(detection_count) as total_count
            FROM species_daily_rollup
            WHERE rollup_date >= date('now', ?)
            GROUP BY rollup_date
            ORDER BY rollup_date ASC
        """
        window = f"-{days - 1} day"
        async with self.db.execute(query, (window,)) as cursor:
            rows = await cursor.fetchall()

        counts_by_date = {row[0]: row[1] or 0 for row in rows}
        start_date = datetime.utcnow().date() - timedelta(days=days - 1)
        results: list[dict] = []
        for i in range(days):
            day = start_date + timedelta(days=i)
            key = day.strftime("%Y-%m-%d")
            results.append({"date": key, "count": counts_by_date.get(key, 0)})
        return results

    async def get_unified_species_window_metrics(self, lookback_days: int = 30) -> dict[str, dict]:
        """Aggregate recent per-species metrics using a stable unified key.

        Keyed by `_canonical_key_sql`, the same rule the leaderboard groups by.
        """
        window = f"-{lookback_days} day"
        # The same key and the same join as the leaderboard, because the
        # leaderboard looks its trends up in this result by that key. Matching
        # only by coincidence is how a species silently shows a flat trend:
        # without the join a row whose scientific name is absent keys on its
        # label here and on the cached scientific name there.
        canonical_key = self._canonical_key_sql()
        taxonomy_join = self._taxonomy_join_sql()
        query = f"""
            SELECT
                {canonical_key} as unified_key,
                SUM(CASE WHEN d.detection_time >= datetime('now','-1 day') THEN 1 ELSE 0 END) as count_1d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-7 day') THEN 1 ELSE 0 END) as count_7d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-30 day') THEN 1 ELSE 0 END) as count_30d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-14 day')
                          AND d.detection_time < datetime('now','-7 day') THEN 1 ELSE 0 END) as count_prev_7d,
                COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-14 day') THEN date(d.detection_time) END) as days_seen_14d,
                COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-30 day') THEN date(d.detection_time) END) as days_seen_30d,
                MAX(d.detection_time) as last_seen_recent
            FROM detections d
            {taxonomy_join}
            WHERE d.detection_time >= datetime('now', ?)
              AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
            GROUP BY unified_key
        """
        async with self.db.execute(query, (window,)) as cursor:
            rows = await cursor.fetchall()

        metrics: dict[str, dict] = {}
        for row in rows:
            metrics[row[0]] = {
                "count_1d": row[1] or 0,
                "count_7d": row[2] or 0,
                "count_30d": row[3] or 0,
                "count_prev_7d": row[4] or 0,
                "days_seen_14d": row[5] or 0,
                "days_seen_30d": row[6] or 0,
                "last_seen_recent": _parse_datetime(row[7]) if row[7] else None,
            }
        return metrics

    async def get_window_metrics_for_species_name(self, species_name: str, lookback_days: int = 30) -> dict:
        """Aggregate recent per-species metrics directly from detections."""
        window = f"-{lookback_days} day"
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""
                SELECT
                    SUM(CASE WHEN d.detection_time >= datetime('now','-1 day') THEN 1 ELSE 0 END) as count_1d,
                    SUM(CASE WHEN d.detection_time >= datetime('now','-7 day') THEN 1 ELSE 0 END) as count_7d,
                    SUM(CASE WHEN d.detection_time >= datetime('now','-30 day') THEN 1 ELSE 0 END) as count_30d,
                    SUM(CASE WHEN d.detection_time >= datetime('now','-14 day')
                              AND d.detection_time < datetime('now','-7 day') THEN 1 ELSE 0 END) as count_prev_7d,
                    COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-14 day') THEN date(d.detection_time) END) as days_seen_14d,
                    COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-30 day') THEN date(d.detection_time) END) as days_seen_30d,
                    MAX(d.detection_time) as last_seen_recent
                FROM detections d
                {join_sql}
                WHERE d.detection_time >= datetime('now', ?)
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                  AND {species_condition}
            """,
            [window, *params],
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return {}
        return {
            "count_1d": row[0] or 0,
            "count_7d": row[1] or 0,
            "count_30d": row[2] or 0,
            "count_prev_7d": row[3] or 0,
            "days_seen_14d": row[4] or 0,
            "days_seen_30d": row[5] or 0,
            "last_seen_recent": _parse_datetime(row[6]) if row[6] else None,
        }

    async def get_species_aggregate_for_labels(self, labels: list[str]) -> dict | None:
        """Aggregate stats across multiple display_name labels."""
        if not labels:
            return None
        placeholders = ",".join(["?"] * len(labels))
        query = f"""
            SELECT COUNT(*), MIN(detection_time), MAX(detection_time),
                   AVG(score), MAX(score), MIN(score),
                   COUNT(DISTINCT camera_name)
            FROM detections
            WHERE display_name IN ({placeholders})
              AND (is_hidden = 0 OR is_hidden IS NULL)
        """
        async with self.db.execute(query, labels) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] == 0:
            return None
        return {
            "count": row[0],
            "first_seen": _parse_datetime(row[1]) if row[1] else None,
            "last_seen": _parse_datetime(row[2]) if row[2] else None,
            "avg_confidence": row[3] or 0.0,
            "max_confidence": row[4] or 0.0,
            "min_confidence": row[5] or 0.0,
            "camera_count": row[6] or 0,
        }

    async def get_species_aggregate_for_name(self, species_name: str) -> dict | None:
        """Aggregate stats for a canonical species selection."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""
                SELECT COUNT(*), MIN(d.detection_time), MAX(d.detection_time),
                       AVG(d.score), MAX(d.score), MIN(d.score),
                       COUNT(DISTINCT d.camera_name)
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
            """,
            params,
        ) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] == 0:
            return None
        return {
            "count": row[0],
            "first_seen": _parse_datetime(row[1]) if row[1] else None,
            "last_seen": _parse_datetime(row[2]) if row[2] else None,
            "avg_confidence": row[3] or 0.0,
            "max_confidence": row[4] or 0.0,
            "min_confidence": row[5] or 0.0,
            "camera_count": row[6] or 0,
        }

    async def get_species_basic_stats(self, species_name: str) -> dict:
        """Get basic stats for a species: count, min/max dates, confidence stats."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""SELECT COUNT(*), MIN(d.detection_time), MAX(d.detection_time),
                       AVG(d.score), MAX(d.score), MIN(d.score)
                FROM detections d
                {join_sql}
                WHERE {species_condition}""",
            params,
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                return {
                    "total": row[0],
                    "first_seen": _parse_datetime(row[1]) if row[1] else None,
                    "last_seen": _parse_datetime(row[2]) if row[2] else None,
                    "avg_confidence": row[3] or 0.0,
                    "max_confidence": row[4] or 0.0,
                    "min_confidence": row[5] or 0.0,
                }
            return {
                "total": 0,
                "first_seen": None,
                "last_seen": None,
                "avg_confidence": 0.0,
                "max_confidence": 0.0,
                "min_confidence": 0.0,
            }

    async def get_species_leaderboard_window_for_name(
        self,
        species_name: str,
        window_start: datetime,
        window_end: datetime,
        prev_start: datetime,
        prev_end: datetime,
    ) -> dict | None:
        """Aggregate leaderboard window stats for a canonical species selection."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""
                SELECT
                    SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as window_count,
                    SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as prev_count,
                    MIN(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_first_seen,
                    MAX(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_last_seen,
                    AVG(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.score ELSE NULL END) as window_avg_confidence,
                    COUNT(DISTINCT CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.camera_name ELSE NULL END) as window_camera_count
                FROM detections d
                {join_sql}
                WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
                  AND d.detection_time >= ?
                  AND d.detection_time < ?
                  AND {species_condition}
            """,
            [
                window_start,
                window_end,
                prev_start,
                prev_end,
                window_start,
                window_end,
                window_start,
                window_end,
                window_start,
                window_end,
                window_start,
                window_end,
                window_start,
                window_end,
                *params,
            ],
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        window_count = int(row[0] or 0)
        prev_count = int(row[1] or 0)
        if window_count == 0 and prev_count == 0:
            return None
        return {
            "window_count": window_count,
            "prev_count": prev_count,
            "window_first_seen": _parse_datetime(row[2]) if row[2] else None,
            "window_last_seen": _parse_datetime(row[3]) if row[3] else None,
            "window_avg_confidence": float(row[4] or 0.0),
            "window_camera_count": int(row[5] or 0),
        }

    async def get_camera_breakdown(self, species_name: str) -> list[dict]:
        """Get detection counts grouped by camera."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""SELECT d.camera_name, COUNT(*) as count
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                GROUP BY d.camera_name ORDER BY count DESC""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            total = sum(row[1] for row in rows)
            return [
                {"camera_name": row[0], "count": row[1], "percentage": (row[1] / total * 100) if total > 0 else 0.0}
                for row in rows
            ]

    async def get_hourly_distribution(self, species_name: str) -> list[int]:
        """Get 24-element list of detection counts per hour."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""SELECT strftime('%H', d.detection_time) as hour, COUNT(*)
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                GROUP BY hour""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 24
            for row in rows:
                hour = int(row[0])
                distribution[hour] = row[1]
            return distribution

    async def get_daily_distribution(self, species_name: str) -> list[int]:
        """Get 7-element list of detection counts per day of week (0=Sunday)."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""SELECT strftime('%w', d.detection_time) as dow, COUNT(*)
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                GROUP BY dow""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 7
            for row in rows:
                dow = int(row[0])
                distribution[dow] = row[1]
            return distribution

    async def get_monthly_distribution(self, species_name: str) -> list[int]:
        """Get 12-element list of detection counts per month (1-12)."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""SELECT strftime('%m', d.detection_time) as month, COUNT(*)
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                GROUP BY month""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 12
            for row in rows:
                month = int(row[0]) - 1  # Convert 1-12 to 0-11 index
                distribution[month] = row[1]
            return distribution

    async def get_global_hourly_distribution(self, start_date: datetime, end_date: datetime) -> list[int]:
        """Get 24-element list of detection counts per hour for ALL species in range."""
        async with self.db.execute(
            """SELECT strftime('%H', detection_time) as hour, COUNT(*)
               FROM detections 
               WHERE detection_time >= ? AND detection_time <= ?
               AND (is_hidden = 0 OR is_hidden IS NULL)
               GROUP BY hour""",
            (start_date.isoformat(sep=" "), end_date.isoformat(sep=" ")),
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 24
            for row in rows:
                hour = int(row[0])
                distribution[hour] = row[1]
            return distribution

    async def get_species_utc_hourly_counts(self, species_name: str) -> list[tuple[datetime, int]]:
        """Return counts grouped by UTC hour buckets for a canonical species lookup."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        async with self.db.execute(
            f"""
                SELECT strftime('%Y-%m-%d %H:00:00', d.detection_time) as bucket_start, COUNT(*)
                FROM detections d
                {join_sql}
                WHERE {species_condition}
                GROUP BY bucket_start
                ORDER BY bucket_start ASC
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

        out: list[tuple[datetime, int]] = []
        for row in rows:
            bucket_start = _parse_datetime(row[0])
            count = int(row[1] or 0)
            if count <= 0:
                continue
            out.append((bucket_start, count))
        return out

    async def get_daily_species_counts(self, start_date: datetime, end_date: datetime) -> list[dict]:
        """Get detection counts per species for a specific time range."""
        canonical_key = self._canonical_key_sql(taxonomy_alias=None)
        query = f"""
            WITH filtered AS (
                SELECT
                    d.id,
                    d.detection_time,
                    d.frigate_event,
                    d.scientific_name,
                    d.common_name,
                    d.display_name,
                    d.taxa_id,
                    {canonical_key} AS unified_id
                FROM detections d
                WHERE d.detection_time >= ? AND d.detection_time <= ?
                  AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
            ),
            ranked AS (
                SELECT
                    unified_id,
                    frigate_event,
                    scientific_name,
                    common_name,
                    display_name,
                    taxa_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY unified_id
                        ORDER BY detection_time DESC, id DESC, frigate_event DESC
                    ) AS row_num
                FROM filtered
            ),
            counts AS (
                SELECT unified_id, COUNT(*) AS count
                FROM filtered
                GROUP BY unified_id
            )
            SELECT
                counts.unified_id,
                counts.count,
                ranked.frigate_event AS latest_event,
                filtered_latest.detection_time AS latest_detection_time,
                ranked.scientific_name,
                ranked.common_name,
                ranked.display_name,
                ranked.taxa_id
            FROM counts
            JOIN ranked
              ON ranked.unified_id = counts.unified_id
             AND ranked.row_num = 1
            JOIN filtered AS filtered_latest
              ON filtered_latest.unified_id = ranked.unified_id
             AND filtered_latest.frigate_event = ranked.frigate_event
            ORDER BY counts.count DESC
        """
        async with self.db.execute(query, (start_date.isoformat(sep=" "), end_date.isoformat(sep=" "))) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "species": row[6],
                    "count": row[1],
                    "latest_event": row[2],
                    "latest_detection_time": _parse_datetime(row[3]) if row[3] else None,
                    "scientific_name": row[4],
                    "common_name": row[5],
                    "taxa_id": row[7],
                }
                for row in rows
            ]

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

        cursor = await self.db.execute(
            """INSERT INTO audio_detections (
                   timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id,
                   species_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                resolve_audio_identity(scientific_name),
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

    async def get_recent_audio_source_observations(self, limit: int = 200) -> list[dict]:
        """Return recent raw audio rows for source discovery/deduping."""
        async with self.db.execute(
            """SELECT timestamp, sensor_id, raw_data
               FROM audio_detections
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "timestamp": row[0],
                "sensor_id": row[1],
                "raw_data": row[2],
            }
            for row in rows
        ]

    async def get_audio_context(
        self, target_time: datetime, window_seconds: int, mapping_value: Optional[str], limit: int
    ) -> tuple[list[dict], int]:
        """Return audio near ``target_time`` plus how many rows the mapping excluded.

        The count lets a caller distinguish a silent window from one where audio was
        heard on a microphone this camera is not mapped to; both otherwise present as
        an empty list.
        """
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        start_dt = target_time - timedelta(seconds=window_seconds)
        end_dt = target_time + timedelta(seconds=window_seconds)
        query = """SELECT timestamp, species, confidence, sensor_id, scientific_name, raw_data
                   FROM audio_detections
                   WHERE timestamp >= ? AND timestamp <= ?"""
        params: list = [serialize_storage_datetime(start_dt), serialize_storage_datetime(end_dt)]
        query += " ORDER BY timestamp DESC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        # Deferred import to avoid the circular `audio_service ->
        # detection_repository` cycle. Reuse the same extractor that
        # /api/audio/recent uses so payload key handling stays in lockstep
        # (`detectionId` / `id` / `detection_id`).
        from app.services.audio.audio_service import _extract_birdnet_id

        wildcard_mapping, mapping_keys = _parse_mapping_filter_values(mapping_value)
        results: list[dict] = []
        suppressed_by_mapping = 0
        for row in rows:
            if not wildcard_mapping:
                row_keys = _extract_audio_mapping_keys(row[3], row[5])
                if not row_keys.intersection(mapping_keys):
                    suppressed_by_mapping += 1
                    continue
            det_time = _parse_datetime(row[0])
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
                    birdnet_id = _extract_birdnet_id(payload)

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

    def _build_audio_history_filter(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        species: Optional[str],
        source: Optional[str],
        min_confidence: Optional[float],
    ) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []

        if start_date is not None:
            clauses.append("timestamp >= ?")
            params.append(serialize_storage_datetime(start_date))
        if end_date is not None:
            clauses.append("timestamp <= ?")
            params.append(serialize_storage_datetime(end_date))
        if species:
            clauses.append("LOWER(species) LIKE ?")
            params.append(f"%{species.strip().casefold()}%")
        if source:
            source_like = f"%{source.strip().casefold()}%"
            clauses.append("(LOWER(COALESCE(sensor_id, '')) LIKE ? OR LOWER(COALESCE(raw_data, '')) LIKE ?)")
            params.extend([source_like, source_like])
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
    ) -> dict:
        """Return persisted BirdNET detections for history browsing."""
        where_sql, params = self._build_audio_history_filter(
            start_date=start_date,
            end_date=end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
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

        from app.services.audio.audio_service import _extract_birdnet_id

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
                    birdnet_id = _extract_birdnet_id(payload)

            items.append(
                {
                    "id": row[0],
                    "timestamp": serialize_api_datetime(_parse_datetime(row[1])),
                    "species": row[2],
                    "confidence": row[3],
                    "sensor_id": row[4],
                    "source_name": _extract_birdnet_source_name(row[4], raw_data),
                    "scientific_name": row[5],
                    "birdnet_id": birdnet_id,
                    "_mapping_keys": _extract_audio_mapping_keys(row[4], raw_data),
                }
            )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_audio_visual_match_candidates(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
        scientific_names: set[str],
    ) -> list[dict]:
        """Return bounded automatic video results eligible for audio-history links."""
        normalized_names = sorted(
            {normalized for name in scientific_names if (normalized := _normalize_species_lookup_name(name))}
        )
        if not normalized_names:
            return []

        placeholders = ", ".join("?" for _ in normalized_names)
        params: list[object] = [
            start_date.isoformat(sep=" "),
            end_date.isoformat(sep=" "),
            *normalized_names,
        ]
        query = f"""SELECT frigate_event, detection_time, camera_name,
                           video_classification_label, video_classification_score
                    FROM detections
                    WHERE detection_time >= ?
                      AND detection_time <= ?
                      AND (is_hidden = 0 OR is_hidden IS NULL)
                      AND (manual_tagged = 0 OR manual_tagged IS NULL)
                      AND video_classification_status = 'completed'
                      AND video_classification_label IS NOT NULL
                      AND LOWER(TRIM(video_classification_label)) IN ({placeholders})"""
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "frigate_event": row[0],
                "detection_time": row[1],
                "camera_name": row[2],
                "video_classification_label": row[3],
                "video_classification_score": row[4],
            }
            for row in rows
        ]

    async def get_audio_history_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        species: Optional[str] = None,
        source: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> dict:
        """Return rollups over persisted BirdNET detections."""
        where_sql, params = self._build_audio_history_filter(
            start_date=start_date,
            end_date=end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
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
            f"""SELECT DATE(timestamp), COUNT(*)
                FROM audio_detections
                {where_sql}
                GROUP BY DATE(timestamp)
                ORDER BY DATE(timestamp) ASC""",
            params,
        ) as cursor:
            daily_rows = await cursor.fetchall()

        async with self.db.execute(
            f"""SELECT CAST(strftime('%H', timestamp) AS INTEGER), COUNT(*)
                FROM audio_detections
                {where_sql}
                GROUP BY CAST(strftime('%H', timestamp) AS INTEGER)
                ORDER BY CAST(strftime('%H', timestamp) AS INTEGER) ASC""",
            params,
        ) as cursor:
            hourly_rows = await cursor.fetchall()

        async with self.db.execute(
            f"""SELECT timestamp, sensor_id, raw_data
                FROM audio_detections
                {where_sql}
                ORDER BY timestamp DESC""",
            params,
        ) as cursor:
            source_rows = await cursor.fetchall()

        source_totals: dict[str, dict] = {}
        for row in source_rows:
            source_name = _extract_birdnet_source_name(row[1], row[2])
            if not source_name:
                source_name = "Unknown source"
            if source_name not in source_totals:
                source_totals[source_name] = {
                    "source_name": source_name,
                    "count": 0,
                    "last_heard": serialize_api_datetime(_parse_datetime(row[0])),
                }
            source_totals[source_name]["count"] += 1

        top_species = [
            {
                "species": row[0],
                "scientific_name": row[1],
                "count": int(row[2] or 0),
                "avg_confidence": float(row[3] or 0),
                "max_confidence": float(row[4] or 0),
                "first_heard": serialize_api_datetime(_parse_datetime(row[5])) if row[5] else None,
                "last_heard": serialize_api_datetime(_parse_datetime(row[6])) if row[6] else None,
            }
            for row in top_species_rows
        ]

        sources = sorted(
            source_totals.values(),
            key=lambda item: (-int(item["count"]), str(item["source_name"]).casefold()),
        )

        return {
            "total": int(totals[0] or 0) if totals else 0,
            "species_count": int(totals[1] or 0) if totals else 0,
            "source_count": len(sources),
            "top_species": top_species,
            "daily_counts": [{"date": row[0], "count": int(row[1] or 0)} for row in daily_rows],
            "hourly_counts": [{"hour": int(row[0] or 0), "count": int(row[1] or 0)} for row in hourly_rows],
            "sources": sources,
        }

    async def backfill_audio_species_ids(self, *, resolver: Any = None, batch_size: int = 500) -> dict[str, int]:
        """Give existing audio detections the identity new ones will carry.

        Required rather than optional: grouping audio by identity while older
        rows have none would split a species at the upgrade boundary, which is
        the exact failure this phase removes.

        Conservative and idempotent. Only rows with no identity are considered,
        a name is resolved once rather than per row, and anything the catalogue
        cannot pin to exactly one species is counted and left alone.
        """
        from app.services.audio_identity import resolve_audio_identity

        async with self.db.execute(
            """
            SELECT scientific_name, COUNT(*) FROM audio_detections
            WHERE species_id IS NULL AND scientific_name IS NOT NULL AND TRIM(scientific_name) != ''
            GROUP BY scientific_name
            """
        ) as cursor:
            pending = await cursor.fetchall()

        identified = 0
        unresolved = 0
        for scientific_name, row_count in pending:
            species_id = resolve_audio_identity(scientific_name, resolver=resolver)
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
            WHERE timestamp >= ? AND timestamp < ?
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
                    "window_last_heard": _parse_datetime(row[6]) if row[6] else None,
                }
            )
        return results

    async def get_audio_confirmations_count(self, start_date: datetime, end_date: datetime) -> int:
        """Get total audio-confirmed detections in a time range."""
        async with self.db.execute(
            """SELECT COUNT(*)
               FROM detections
               WHERE detection_time >= ? AND detection_time <= ?
               AND audio_confirmed = 1
               AND (is_hidden = 0 OR is_hidden IS NULL)""",
            (start_date.isoformat(sep=" "), end_date.isoformat(sep=" ")),
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0] or 0)

    async def get_recent_by_species(
        self, species_name: str, limit: int = 5, include_hidden: bool = False
    ) -> list[Detection]:
        """Get most recent detections for a species."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        if include_hidden:
            query = f"""SELECT {DETECTION_SELECT_COLUMNS}
                   FROM detections d
                   LEFT JOIN detection_favorites f ON f.detection_id = d.id
                   {join_sql}
                   WHERE {species_condition}
                   ORDER BY d.detection_time DESC LIMIT ?"""
            params = [*params, limit]
        else:
            query = f"""SELECT {DETECTION_SELECT_COLUMNS}
                   FROM detections d
                   LEFT JOIN detection_favorites f ON f.detection_id = d.id
                   {join_sql}
                   WHERE {species_condition} AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                   ORDER BY d.detection_time DESC LIMIT ?"""
            params = [*params, limit]

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]
