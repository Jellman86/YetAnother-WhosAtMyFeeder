from typing import Optional
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
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()

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
    notified_at: Optional[datetime] = None
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
    # AI naturalist analysis fields
    ai_analysis: Optional[str] = None
    ai_analysis_timestamp: Optional[datetime] = None


def _parse_datetime(value) -> datetime:
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
        return True, set()
    tokens = {
        _normalize_mapping_key(token)
        for token in re.split(r"[,\n;|]+", mapping_value)
    }
    tokens.discard("")
    if not tokens or "*" in tokens:
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


def _row_to_detection(row) -> Detection:
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
        taxa_id=row[24] if len(row) > 24 else None
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

    return d


class DetectionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self._table_exists_cache: dict[str, bool] = {}

    @staticmethod
    def _canonical_key_sql(*, detection_alias: str = "d", taxonomy_alias: str = "tc") -> str:
        return (
            f"COALESCE(CAST(COALESCE({detection_alias}.taxa_id, {taxonomy_alias}.taxa_id) AS TEXT), "
            f"LOWER(COALESCE({detection_alias}.scientific_name, {taxonomy_alias}.scientific_name)), "
            f"LOWER({detection_alias}.display_name))"
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
            exact_labels = [
                str(label).strip().lower()
                for label in hidden_species_exact_labels()
                if str(label).strip()
            ]
            exact_labels = list(dict.fromkeys(exact_labels))
            fragments = [
                str(fragment).strip().lower()
                for fragment in hidden_species_substrings()
                if str(fragment).strip()
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
                clauses.append(f"LOWER(COALESCE({detection_alias}.scientific_name, tc_filter.scientific_name)) = LOWER(?)")
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
        has_taxonomy_cache = await self._table_exists("taxonomy_cache")
        join_sql = ""
        if has_taxonomy_cache:
            join_sql = (
                " LEFT JOIN taxonomy_cache tc_filter"
                f" ON (({detection_alias}.scientific_name IS NOT NULL AND LOWER(tc_filter.scientific_name) = LOWER({detection_alias}.scientific_name))"
                f" OR ({detection_alias}.scientific_name IS NULL AND (LOWER(tc_filter.scientific_name) = LOWER({detection_alias}.display_name)"
                f" OR LOWER(tc_filter.common_name) = LOWER({detection_alias}.display_name))))"
            )
        condition, params = await self._build_canonical_species_condition(
            detection_alias=detection_alias,
            species_name=species_name,
            has_taxonomy_cache=has_taxonomy_cache,
        )
        return join_sql, condition, params

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

    async def _table_columns(self, table_name: str) -> set[str]:
        if not await self._table_exists(table_name):
            return set()
        async with self.db.execute(f"PRAGMA table_info({table_name})") as cursor:
            rows = await cursor.fetchall()
        return {row[1] for row in rows if row and len(row) > 1}

    async def get_by_frigate_event(self, frigate_event: str) -> Optional[Detection]:
        async with self.db.execute(
            """SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name, d.category_name, d.frigate_event, d.camera_name,
                      d.is_hidden, d.frigate_score, d.sub_label, d.audio_confirmed, d.audio_species, d.audio_score,
                      d.temperature, d.weather_condition, d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                      d.weather_precipitation, d.weather_rain, d.weather_snowfall, d.scientific_name, d.common_name, d.taxa_id,
                      d.video_classification_score, d.video_classification_label, d.video_classification_index,
                      d.video_classification_timestamp, d.video_classification_status, d.video_classification_error,
                      d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                      CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                      d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
               FROM detections d
               LEFT JOIN detection_favorites f ON f.detection_id = d.id
               WHERE d.frigate_event = ?""",
            (frigate_event,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

    async def get_recent_full_visit_candidates(
        self,
        *,
        detected_before: datetime,
        detected_after: datetime,
        limit: int = 100,
    ) -> list[Detection]:
        async with self.db.execute(
            """SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name, d.category_name, d.frigate_event, d.camera_name,
                      d.is_hidden, d.frigate_score, d.sub_label, d.audio_confirmed, d.audio_species, d.audio_score,
                      d.temperature, d.weather_condition, d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                      d.weather_precipitation, d.weather_rain, d.weather_snowfall, d.scientific_name, d.common_name, d.taxa_id,
                      d.video_classification_score, d.video_classification_label, d.video_classification_index,
                      d.video_classification_timestamp, d.video_classification_status, d.video_classification_error,
                      d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                      CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                      d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
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
        label: str,
        score: float,
        index: int,
        status: str = 'completed',
        provider: Optional[str] = None,
        backend: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        """Update video classification results for an event."""
        now = utc_naive_now()
        await self.db.execute("""
            UPDATE detections
            SET video_classification_label = ?,
                video_classification_score = ?,
                video_classification_index = ?,
                video_classification_timestamp = ?,
                video_classification_status = ?,
                video_classification_error = NULL,
                video_classification_provider = ?,
                video_classification_backend = ?,
                video_classification_model_id = ?
            WHERE frigate_event = ?
        """, (label, score, index, now, status, provider, backend, model_id, frigate_event))
        await self.db.commit()

    async def update_video_status(self, frigate_event: str, status: str, error: Optional[str] = None):
        """Update just the video classification status."""
        now = utc_naive_now()
        await self.db.execute("""
            UPDATE detections
            SET video_classification_status = ?,
                video_classification_error = ?,
                video_classification_timestamp = ?
            WHERE frigate_event = ?
        """, (status, error, now, frigate_event))
        await self.db.commit()

    async def reset_stale_video_statuses(self, max_age_minutes: int) -> int:
        """Mark pending/processing video classifications as failed if they are too old."""
        now = utc_naive_now()
        await self.db.execute("""
            UPDATE detections
            SET video_classification_status = 'failed',
                video_classification_error = 'stale_timeout',
                video_classification_timestamp = ?
            WHERE video_classification_status IN ('pending', 'processing')
              AND (video_classification_timestamp IS NULL
                   OR video_classification_timestamp < datetime('now', ?))
        """, (now, f'-{max_age_minutes} minutes'))
        changed = await self._last_statement_changes()
        await self.db.commit()
        return changed

    async def mark_notified(self, frigate_event: str, timestamp: Optional[datetime] = None):
        """Mark a detection as notified."""
        if timestamp is None:
            timestamp = utc_naive_now()
        await self.db.execute(
            "UPDATE detections SET notified_at = ? WHERE frigate_event = ?",
            (timestamp, frigate_event)
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

    async def update_ai_analysis(self, frigate_event: str, analysis: str):
        """Update AI naturalist analysis for an event."""
        now = utc_naive_now()
        await self.db.execute("""
            UPDATE detections
            SET ai_analysis = ?,
                ai_analysis_timestamp = ?
            WHERE frigate_event = ?
        """, (analysis, now, frigate_event))
        await self.db.commit()

    async def toggle_hidden(self, frigate_event: str) -> Optional[bool]:
        """Toggle the hidden status of a detection. Returns new hidden status or None if not found."""
        detection = await self.get_by_frigate_event(frigate_event)
        if not detection:
            return None

        new_status = not detection.is_hidden
        await self.db.execute(
            "UPDATE detections SET is_hidden = ? WHERE frigate_event = ?",
            (1 if new_status else 0, frigate_event)
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
            (detection.id, created_by)
        )
        await self.db.commit()
        return True

    async def unfavorite_detection(self, frigate_event: str) -> Optional[bool]:
        """Remove favorite marker. Returns True if detection exists, None if not found."""
        detection = await self.get_by_frigate_event(frigate_event)
        if not detection or detection.id is None:
            return None

        await self.db.execute(
            "DELETE FROM detection_favorites WHERE detection_id = ?",
            (detection.id,)
        )
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
        async with self.db.execute(
            "SELECT COUNT(*) FROM detections WHERE is_hidden = 1"
        ) as cursor:
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

    async def create(self, detection: Detection):
        sub_label = normalize_sub_label(detection.sub_label)
        await self.db.execute("""
            INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, manual_tagged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_event, detection.camera_name, 1 if detection.is_hidden else 0, detection.frigate_score, sub_label, 1 if detection.audio_confirmed else 0, detection.audio_species, detection.audio_score, detection.temperature, detection.weather_condition, detection.weather_cloud_cover, detection.weather_wind_speed, detection.weather_wind_direction, detection.weather_precipitation, detection.weather_rain, detection.weather_snowfall, detection.scientific_name, detection.common_name, detection.taxa_id, 1 if detection.manual_tagged else 0))
        await self.db.commit()

    async def update(self, detection: Detection):
        sub_label = normalize_sub_label(detection.sub_label)
        await self.db.execute("""
            UPDATE detections
            SET detection_time = ?, detection_index = ?, score = ?, display_name = ?, category_name = ?, frigate_score = ?, sub_label = ?, audio_confirmed = ?, audio_species = ?, audio_score = ?, temperature = ?, weather_condition = ?, weather_cloud_cover = ?, weather_wind_speed = ?, weather_wind_direction = ?, weather_precipitation = ?, weather_rain = ?, weather_snowfall = ?, scientific_name = ?, common_name = ?, taxa_id = ?, manual_tagged = ?
            WHERE frigate_event = ?
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_score, sub_label, detection.audio_confirmed, detection.audio_species, detection.audio_score, detection.temperature, detection.weather_condition, detection.weather_cloud_cover, detection.weather_wind_speed, detection.weather_wind_direction, detection.weather_precipitation, detection.weather_rain, detection.weather_snowfall, detection.scientific_name, detection.common_name, detection.taxa_id, 1 if detection.manual_tagged else 0, detection.frigate_event))
        await self.db.commit()

    async def list_for_weather_backfill(self, start: str, end: str, only_missing: bool = True) -> list[dict]:
        """Return detections within range for weather backfill."""
        query = """
            SELECT frigate_event, detection_time, temperature, weather_condition, weather_cloud_cover,
                   weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall
            FROM detections
            WHERE datetime(detection_time) BETWEEN datetime(?) AND datetime(?)
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
                "weather_snowfall": row[9]
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
        snowfall: float | None
    ) -> None:
        await self.db.execute("""
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
        """, (
            temperature,
            weather_condition,
            cloud_cover,
            wind_speed,
            wind_direction,
            precipitation,
            rain,
            snowfall,
            frigate_event
        ))
        await self.db.commit()

    async def upsert_if_higher_score(self, detection: Detection) -> tuple[bool, bool]:
        """Insert if missing, otherwise update only when score/audio is better.

        Returns:
            Tuple of (was_inserted, was_updated)
        """
        sub_label = normalize_sub_label(detection.sub_label)
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
            getattr(detection, 'scientific_name', None),
            getattr(detection, 'common_name', None),
            getattr(detection, 'taxa_id', None),
            1 if detection.manual_tagged else 0,
        )

        # Attempt insert first.
        await self.db.execute("""
            INSERT OR IGNORE INTO detections
            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, manual_tagged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_params)
        inserted = await self._last_statement_changes() > 0
        if inserted:
            await self.db.commit()
            return (True, False)

        # Existing row: update only when it improves quality.
        await self.db.execute("""
            UPDATE detections
            SET detection_time = ?,
                detection_index = ?,
                score = ?,
                display_name = ?,
                category_name = ?,
                frigate_score = ?,
                sub_label = ?,
                audio_confirmed = ?,
                audio_species = ?,
                audio_score = ?,
                temperature = ?,
                weather_condition = ?,
                weather_cloud_cover = ?,
                weather_wind_speed = ?,
                weather_wind_direction = ?,
                weather_precipitation = ?,
                weather_rain = ?,
                weather_snowfall = ?,
                scientific_name = ?,
                common_name = ?,
                taxa_id = ?,
                manual_tagged = manual_tagged
            WHERE frigate_event = ?
              AND (? > score OR (? = 1 AND COALESCE(audio_confirmed, 0) = 0))
        """, (
            detection.detection_time,
            detection.detection_index,
            detection.score,
            detection.display_name,
            detection.category_name,
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
            getattr(detection, 'scientific_name', None),
            getattr(detection, 'common_name', None),
            getattr(detection, 'taxa_id', None),
            detection.frigate_event,
            detection.score,
            1 if detection.audio_confirmed else 0
        ))
        updated = await self._last_statement_changes() > 0
        await self.db.commit()
        return (False, updated)

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
        await self.db.execute("""
            INSERT OR IGNORE INTO detections
            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, manual_tagged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
            1 if detection.manual_tagged else 0
        ))
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
        audio_confirmed_only: bool = False
    ) -> list[Detection]:
        has_taxonomy_cache = await self._table_exists("taxonomy_cache")
        query = """
            SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name, d.category_name, d.frigate_event, d.camera_name,
                   d.is_hidden, d.frigate_score, d.sub_label, d.audio_confirmed, d.audio_species, d.audio_score,
                   d.temperature, d.weather_condition, d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                   d.weather_precipitation, d.weather_rain, d.weather_snowfall, d.scientific_name, d.common_name, d.taxa_id,
                   d.video_classification_score, d.video_classification_label, d.video_classification_index,
                   d.video_classification_timestamp, d.video_classification_status, d.video_classification_error,
                   d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                   CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                   d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
        """
        if has_taxonomy_cache:
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
            params.append(start_date.isoformat(sep=' '))
        if end_date:
            conditions.append("d.detection_time <= ?")
            params.append(end_date.isoformat(sep=' '))
        if species:
            species_condition, species_params = await self._build_canonical_species_condition(
                detection_alias="d",
                species_name=species,
                has_taxonomy_cache=has_taxonomy_cache,
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
                    has_taxonomy_cache=has_taxonomy_cache,
                )
                any_clauses.append(clause)
                any_params.extend(clause_params)
            if any_clauses:
                conditions.append("(" + " OR ".join(any_clauses) + ")")
                params.extend(any_params)
        if taxa_id is not None:
            if has_taxonomy_cache:
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
        query = """
            SELECT COUNT(*)
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
        """
        if has_taxonomy_cache:
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
            params.append(start_date.isoformat(sep=' '))
        if end_date:
            conditions.append("d.detection_time <= ?")
            params.append(end_date.isoformat(sep=' '))
        if species:
            species_condition, species_params = await self._build_canonical_species_condition(
                detection_alias="d",
                species_name=species,
                has_taxonomy_cache=has_taxonomy_cache,
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
                    has_taxonomy_cache=has_taxonomy_cache,
                )
                any_clauses.append(clause)
                any_params.extend(clause_params)
            if any_clauses:
                conditions.append("(" + " OR ".join(any_clauses) + ")")
                params.extend(any_params)
        if taxa_id is not None:
            if has_taxonomy_cache:
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
        async with self.db.execute(
            "SELECT DISTINCT display_name FROM detections ORDER BY display_name ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_unique_species_with_taxonomy(self) -> list[tuple[str, str | None, str | None, int | None]]:
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
        async with self.db.execute(
            """
            WITH species_distinct AS (
                -- Enrich taxa_id from taxonomy_cache when the detection is missing it
                -- but has a known scientific_name we can join on.
                SELECT DISTINCT
                    d.display_name,
                    d.scientific_name,
                    d.common_name,
                    COALESCE(d.taxa_id, tc.taxa_id) AS taxa_id
                FROM detections d
                LEFT JOIN taxonomy_cache tc
                    ON d.scientific_name IS NOT NULL
                    AND LOWER(tc.scientific_name) = LOWER(d.scientific_name)
            ),
            ranked AS (
                SELECT
                    display_name,
                    scientific_name,
                    common_name,
                    taxa_id,
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
            SELECT display_name, scientific_name, common_name, taxa_id
            FROM ranked
            WHERE rn = 1
            ORDER BY display_name ASC
            """
        ) as cursor:
            return await cursor.fetchall()

    async def get_unique_cameras(self) -> list[str]:
        """Get list of unique camera names, sorted alphabetically."""
        async with self.db.execute(
            "SELECT DISTINCT camera_name FROM detections ORDER BY camera_name ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_all_frigate_event_ids(self) -> list[str]:
        """Get all Frigate event IDs."""
        async with self.db.execute("SELECT frigate_event FROM detections") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

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
            chunk = event_ids[i:i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"DELETE FROM detections WHERE frigate_event IN ({placeholders})"
            async with self.db.execute(query, chunk) as cursor:
                total_deleted += cursor.rowcount or 0
                await self.db.commit()
        return total_deleted

    async def get_taxonomy_names(self, name: str, language: str | None = None) -> dict:
        """Get scientific and common names for a species from cache.

        Supports lookup by scientific/common names and localized common names (when
        `taxonomy_translations` exists and `language` is provided).
        """
        result = {"scientific_name": None, "common_name": None, "taxa_id": None}
        normalized_lookup = _normalize_species_lookup_name(name)

        async with self.db.execute(
            "SELECT scientific_name, common_name, taxa_id FROM taxonomy_cache WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)",
            (name, name)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = {"scientific_name": row[0], "common_name": row[1], "taxa_id": row[2]}

        if result["taxa_id"] is None and language and language != "en" and await self._table_exists("taxonomy_translations"):
            async with self.db.execute(
                """SELECT tc.scientific_name, tc.common_name, tc.taxa_id, tt.common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                   WHERE tt.language_code = ?
                     AND LOWER(tt.common_name) = LOWER(?)
                   LIMIT 1""",
                (language, name)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    result = {"scientific_name": row[0], "common_name": row[3] or row[1], "taxa_id": row[2]}
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
                """SELECT tc.scientific_name, tc.common_name, tc.taxa_id, tt.common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                   WHERE tt.language_code = ?""",
                (language,)
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if _normalize_species_lookup_name(row[3]) == normalized_lookup:
                    result = {"scientific_name": row[0], "common_name": row[3] or row[1], "taxa_id": row[2]}
                    return result

        # Language-agnostic localized fallback for repair/maintenance paths that
        # do not know the source language of the stored display name.
        if (
            result["taxa_id"] is None
            and normalized_lookup
            and await self._table_exists("taxonomy_translations")
        ):
            async with self.db.execute(
                """SELECT tc.scientific_name, tc.common_name, tc.taxa_id, tt.common_name
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id"""
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if _normalize_species_lookup_name(row[3]) == normalized_lookup:
                    result = {"scientific_name": row[0], "common_name": row[3] or row[1], "taxa_id": row[2]}
                    return result

        if result["taxa_id"] is None and normalized_lookup:
            async with self.db.execute(
                "SELECT scientific_name, common_name, taxa_id FROM taxonomy_cache"
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                if (
                    _normalize_species_lookup_name(row[0]) == normalized_lookup
                    or _normalize_species_lookup_name(row[1]) == normalized_lookup
                ):
                    result = {"scientific_name": row[0], "common_name": row[1], "taxa_id": row[2]}
                    break

        if result["taxa_id"] is not None and language and language != "en" and await self._table_exists("taxonomy_translations"):
            async with self.db.execute(
                """SELECT common_name FROM taxonomy_translations
                   WHERE taxa_id = ? AND language_code = ?
                   LIMIT 1""",
                (result["taxa_id"], language)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    result["common_name"] = row[0]

        return result

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
                "SELECT scientific_name, common_name FROM taxonomy_cache WHERE taxa_id = ? LIMIT 1",
                (taxa_id,)
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
                    (taxa_id, *[n.lower() for n in lowered_names], *[n.lower() for n in lowered_names], *[n.lower() for n in lowered_names])
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
                (*lowered, *lowered, *lowered)
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
        cutoff_str = cutoff_date.isoformat(sep=' ')
        
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

    async def delete_all(self) -> int:
        """Delete ALL detections. Use with caution."""
        async with self.db.execute("DELETE FROM detections") as cursor:
            count = cursor.rowcount
            await self.db.commit()
            return count

    async def get_unknown_detections(self) -> list[Detection]:
        """Get unresolved detections labeled as 'Unknown Bird'."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name="Unknown Bird",
        )
        query = f"""
            SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name, d.category_name,
                   d.frigate_event, d.camera_name, d.is_hidden, d.frigate_score, d.sub_label,
                   d.audio_confirmed, d.audio_species, d.audio_score, d.temperature, d.weather_condition,
                   d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                   d.weather_precipitation, d.weather_rain, d.weather_snowfall,
                   d.scientific_name, d.common_name, d.taxa_id, d.video_classification_score,
                   d.video_classification_label, d.video_classification_index,
                   d.video_classification_timestamp, d.video_classification_status,
                   d.video_classification_error, d.ai_analysis, d.ai_analysis_timestamp,
                   d.manual_tagged, d.notified_at,
                   CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                   d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
            FROM detections d
            LEFT JOIN detection_favorites f ON f.detection_id = d.id
            {join_sql}
            WHERE {species_condition}
              AND COALESCE(d.video_classification_status, '') NOT IN ('pending', 'processing')
              AND COALESCE(d.video_classification_error, '') NOT IN ('clip_not_retained', 'frigate_retention_expired')
        """
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]

    async def get_oldest_detection_date(self) -> datetime | None:
        """Get the date of the oldest detection."""
        async with self.db.execute(
            "SELECT MIN(detection_time) FROM detections"
        ) as cursor:
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
        has_taxonomy_cache = await self._table_exists("taxonomy_cache")

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

    async def get_activity_heatmap_counts(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[int, dict[int, int]]:
        """Return detection counts grouped by weekday (0=Sunday) and hour (0-23)."""
        query = """
            SELECT
                CAST(strftime('%w', detection_time) AS integer) as dow,
                CAST(strftime('%H', detection_time) AS integer) as hour_of_day,
                COUNT(*) as c
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY dow, hour_of_day
            ORDER BY dow ASC, hour_of_day ASC
        """
        async with self.db.execute(query, (start, end)) as cursor:
            rows = await cursor.fetchall()

        out: dict[int, dict[int, int]] = {}
        for row in rows:
            dow = int(row[0] or 0)
            hour_of_day = int(row[1] or 0)
            count = int(row[2] or 0)
            if dow < 0 or dow > 6 or hour_of_day < 0 or hour_of_day > 23:
                continue
            out.setdefault(dow, {})
            out[dow][hour_of_day] = count
        return out

    async def get_species_counts(self) -> list[dict]:
        """Get detection counts per species with taxonomic metadata."""
        query = """
            SELECT 
                COALESCE(CAST(d.taxa_id AS VARCHAR), LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
                COUNT(*) as count, 
                MAX(d.scientific_name) as scientific_name, 
                MAX(d.common_name) as common_name,
                MAX(d.display_name) as display_name,
                MAX(d.taxa_id) as taxa_id
            FROM detections d
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
            GROUP BY unified_id
            ORDER BY count DESC
        """
        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "species": row[4], 
                    "count": row[1],
                    "scientific_name": row[2],
                    "common_name": row[3],
                    "taxa_id": row[5]
                }
                for row in rows
            ]

    async def get_species_leaderboard_base(self) -> list[dict]:
        """Get leaderboard base stats per species with taxonomy and time bounds."""
        query = """
            SELECT 
                COALESCE(CAST(d.taxa_id AS VARCHAR), LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
                COUNT(*) as total_count, 
                MAX(d.scientific_name) as scientific_name, 
                MAX(d.common_name) as common_name,
                MAX(d.display_name) as display_name,
                MAX(d.taxa_id) as taxa_id,
                MIN(d.detection_time) as first_seen,
                MAX(d.detection_time) as last_seen,
                AVG(d.score) as avg_confidence,
                MAX(d.score) as max_confidence,
                MIN(d.score) as min_confidence,
                COUNT(DISTINCT d.camera_name) as camera_count
            FROM detections d
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
            GROUP BY unified_id
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
                    "first_seen": _parse_datetime(row[6]) if row[6] else None,
                    "last_seen": _parse_datetime(row[7]) if row[7] else None,
                    "avg_confidence": row[8] or 0.0,
                    "max_confidence": row[9] or 0.0,
                    "min_confidence": row[10] or 0.0,
                    "camera_count": row[11] or 0,
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
        query = """
            SELECT
                COALESCE(CAST(d.taxa_id AS VARCHAR), LOWER(d.scientific_name), LOWER(d.display_name)) as unified_id,
                MAX(d.scientific_name) as scientific_name,
                MAX(d.common_name) as common_name,
                MAX(d.display_name) as display_name,
                MAX(d.taxa_id) as taxa_id,

                SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as window_count,
                SUM(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN 1 ELSE 0 END) as prev_count,

                MIN(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_first_seen,
                MAX(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.detection_time ELSE NULL END) as window_last_seen,

                AVG(CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.score ELSE NULL END) as window_avg_confidence,
                COUNT(DISTINCT CASE WHEN d.detection_time >= ? AND d.detection_time < ? THEN d.camera_name ELSE NULL END) as window_camera_count
            FROM detections d
            WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
              AND d.detection_time >= ?
              AND d.detection_time < ?
            GROUP BY unified_id
        """
        params = (
            window_start, window_end,
            prev_start, prev_end,
            window_start, window_end,
            window_start, window_end,
            window_start, window_end,
            window_start, window_end,
            prev_start, window_end,
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
            window_start, window_end,
            prev_start, prev_end,
            window_start, window_end,
            window_start, window_end,
            window_start, window_end,
            window_start, window_end,
            *labels,
            prev_start, window_end,
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
        async with self.db.execute(
            "SELECT MAX(rollup_date) FROM species_daily_rollup"
        ) as cursor:
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
                    MAX(detection_time) as last_seen
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
                        COALESCE(CAST(taxa_id AS TEXT), LOWER(scientific_name), LOWER(display_name)) as canonical_key
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
                    MAX(detection_time) as last_seen
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
                        last_seen=excluded.last_seen
                """
            await self.db.executemany(
                f"""INSERT INTO {table_name}
                        (rollup_date, canonical_key, display_name, scientific_name, common_name, taxa_id,
                         detection_count, camera_count, avg_confidence, max_confidence, min_confidence, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    {conflict_sql}""",
                rows,
            )
        else:
            legacy_rows = [
                (row[0], row[2], row[6], row[7], row[8], row[9], row[10], row[11], row[12])
                for row in rows
            ]
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

    async def get_rollup_metrics(self, lookback_days: int = 30) -> dict[str, dict]:
        """Aggregate rollup metrics for leaderboard windows."""
        window = f"-{lookback_days} day"
        rollup_columns = await self._table_columns("species_daily_rollup")
        if "canonical_key" in rollup_columns:
            query = """
                SELECT
                    canonical_key,
                    COALESCE(MAX(common_name), MIN(display_name)) as display_name,
                    SUM(CASE WHEN rollup_date >= date('now','-1 day') THEN detection_count ELSE 0 END) as count_1d,
                    SUM(CASE WHEN rollup_date >= date('now','-7 day') THEN detection_count ELSE 0 END) as count_7d,
                    SUM(CASE WHEN rollup_date >= date('now','-30 day') THEN detection_count ELSE 0 END) as count_30d,
                    SUM(CASE WHEN rollup_date >= date('now','-14 day')
                              AND rollup_date < date('now','-7 day') THEN detection_count ELSE 0 END) as count_prev_7d,
                    SUM(CASE WHEN rollup_date >= date('now','-14 day') AND detection_count > 0 THEN 1 ELSE 0 END) as days_seen_14d,
                    SUM(CASE WHEN rollup_date >= date('now','-30 day') AND detection_count > 0 THEN 1 ELSE 0 END) as days_seen_30d,
                    MAX(last_seen) as last_seen_recent
                FROM species_daily_rollup
                WHERE rollup_date >= date('now', ?)
                GROUP BY canonical_key
            """
        else:
            query = """
            SELECT
                display_name,
                SUM(CASE WHEN rollup_date >= date('now','-1 day') THEN detection_count ELSE 0 END) as count_1d,
                SUM(CASE WHEN rollup_date >= date('now','-7 day') THEN detection_count ELSE 0 END) as count_7d,
                SUM(CASE WHEN rollup_date >= date('now','-30 day') THEN detection_count ELSE 0 END) as count_30d,
                SUM(CASE WHEN rollup_date >= date('now','-14 day')
                          AND rollup_date < date('now','-7 day') THEN detection_count ELSE 0 END) as count_prev_7d,
                    SUM(CASE WHEN rollup_date >= date('now','-14 day') AND detection_count > 0 THEN 1 ELSE 0 END) as days_seen_14d,
                    SUM(CASE WHEN rollup_date >= date('now','-30 day') AND detection_count > 0 THEN 1 ELSE 0 END) as days_seen_30d,
                    MAX(last_seen) as last_seen_recent
                FROM species_daily_rollup
                WHERE rollup_date >= date('now', ?)
                GROUP BY display_name
            """
        async with self.db.execute(query, (window,)) as cursor:
            rows = await cursor.fetchall()
        metrics: dict[str, dict] = {}
        if "canonical_key" in rollup_columns:
            for row in rows:
                metrics[row[1]] = {
                    "count_1d": row[2] or 0,
                    "count_7d": row[3] or 0,
                    "count_30d": row[4] or 0,
                    "count_prev_7d": row[5] or 0,
                    "days_seen_14d": row[6] or 0,
                    "days_seen_30d": row[7] or 0,
                    "last_seen_recent": _parse_datetime(row[8]) if row[8] else None
                }
        else:
            for row in rows:
                metrics[row[0]] = {
                    "count_1d": row[1] or 0,
                    "count_7d": row[2] or 0,
                    "count_30d": row[3] or 0,
                    "count_prev_7d": row[4] or 0,
                    "days_seen_14d": row[5] or 0,
                    "days_seen_30d": row[6] or 0,
                    "last_seen_recent": _parse_datetime(row[7]) if row[7] else None
                }
        return metrics

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

        Key priority:
        - taxa_id (stringified)
        - scientific_name (lowercased)
        - display_name (lowercased)
        """
        window = f"-{lookback_days} day"
        query = """
            SELECT
                COALESCE(
                    CAST(d.taxa_id AS TEXT),
                    LOWER(d.scientific_name),
                    LOWER(d.display_name)
                ) as unified_key,
                SUM(CASE WHEN d.detection_time >= datetime('now','-1 day') THEN 1 ELSE 0 END) as count_1d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-7 day') THEN 1 ELSE 0 END) as count_7d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-30 day') THEN 1 ELSE 0 END) as count_30d,
                SUM(CASE WHEN d.detection_time >= datetime('now','-14 day')
                          AND d.detection_time < datetime('now','-7 day') THEN 1 ELSE 0 END) as count_prev_7d,
                COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-14 day') THEN date(d.detection_time) END) as days_seen_14d,
                COUNT(DISTINCT CASE WHEN d.detection_time >= datetime('now','-30 day') THEN date(d.detection_time) END) as days_seen_30d,
                MAX(d.detection_time) as last_seen_recent
            FROM detections d
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

    async def get_rollup_metrics_for_species(self, species: list[str], lookback_days: int = 30) -> dict:
        """Aggregate rollup metrics for a set of species as a single group."""
        if not species:
            return {}
        placeholders = ",".join(["?"] * len(species))
        query = f"""
            SELECT 
                SUM(CASE WHEN rollup_date >= date('now','-1 day') THEN detection_count ELSE 0 END) as count_1d,
                SUM(CASE WHEN rollup_date >= date('now','-7 day') THEN detection_count ELSE 0 END) as count_7d,
                SUM(CASE WHEN rollup_date >= date('now','-30 day') THEN detection_count ELSE 0 END) as count_30d,
                SUM(CASE WHEN rollup_date >= date('now','-14 day') 
                          AND rollup_date < date('now','-7 day') THEN detection_count ELSE 0 END) as count_prev_7d,
                COUNT(DISTINCT CASE WHEN rollup_date >= date('now','-14 day') AND detection_count > 0 THEN rollup_date END) as days_seen_14d,
                COUNT(DISTINCT CASE WHEN rollup_date >= date('now','-30 day') AND detection_count > 0 THEN rollup_date END) as days_seen_30d,
                MAX(last_seen) as last_seen_recent
            FROM species_daily_rollup
            WHERE rollup_date >= date('now', ?)
              AND display_name IN ({placeholders})
        """
        window = f"-{lookback_days} day"
        params = [window] + species
        async with self.db.execute(query, params) as cursor:
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
                window_start, window_end,
                prev_start, prev_end,
                window_start, window_end,
                window_start, window_end,
                window_start, window_end,
                window_start, window_end,
                window_start, window_end,
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
                {
                    "camera_name": row[0],
                    "count": row[1],
                    "percentage": (row[1] / total * 100) if total > 0 else 0.0
                }
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
            (start_date.isoformat(sep=' '), end_date.isoformat(sep=' '))
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 24
            for row in rows:
                hour = int(row[0])
                distribution[hour] = row[1]
            return distribution

    async def get_daily_species_counts(self, start_date: datetime, end_date: datetime) -> list[dict]:
        """Get detection counts per species for a specific time range."""
        query = """
            WITH filtered AS (
                SELECT
                    d.id,
                    d.detection_time,
                    d.frigate_event,
                    d.scientific_name,
                    d.common_name,
                    d.display_name,
                    d.taxa_id,
                    COALESCE(CAST(d.taxa_id AS VARCHAR), LOWER(d.scientific_name), LOWER(d.display_name)) AS unified_id
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
        async with self.db.execute(query, (start_date.isoformat(sep=' '), end_date.isoformat(sep=' '))) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "species": row[6], 
                    "count": row[1],
                    "latest_event": row[2],
                    "latest_detection_time": _parse_datetime(row[3]) if row[3] else None,
                    "scientific_name": row[4],
                    "common_name": row[5],
                    "taxa_id": row[7]
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
        scientific_name: Optional[str] = None
    ) -> None:
        payload = json.dumps(raw_data or {}, ensure_ascii=True)
        await self.db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp.isoformat(sep=' '), species, confidence, sensor_id, payload, scientific_name)
        )
        await self.db.commit()

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
        self,
        target_time: datetime,
        window_seconds: int,
        mapping_value: Optional[str],
        limit: int
    ) -> list[dict]:
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        start_dt = target_time - timedelta(seconds=window_seconds)
        end_dt = target_time + timedelta(seconds=window_seconds)
        query = """SELECT timestamp, species, confidence, sensor_id, scientific_name, raw_data
                   FROM audio_detections
                   WHERE timestamp >= ? AND timestamp <= ?"""
        params: list = [start_dt.isoformat(sep=' '), end_dt.isoformat(sep=' ')]
        query += " ORDER BY timestamp DESC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        wildcard_mapping, mapping_keys = _parse_mapping_filter_values(mapping_value)
        results: list[dict] = []
        for row in rows:
            if not wildcard_mapping:
                row_keys = _extract_audio_mapping_keys(row[3], row[5])
                if not row_keys.intersection(mapping_keys):
                    continue
            det_time = _parse_datetime(row[0])
            if det_time.tzinfo is None:
                det_time = det_time.replace(tzinfo=timezone.utc)
            offset_seconds = int((det_time - target_time).total_seconds())
            results.append({
                "timestamp": det_time.isoformat(),
                "species": row[1],
                "confidence": row[2],
                "sensor_id": row[3],
                "scientific_name": row[4],
                "offset_seconds": offset_seconds
            })

        results.sort(key=lambda item: (abs(item["offset_seconds"]), -item["confidence"]))
        return results[:limit]

    async def get_audio_confirmations_count(self, start_date: datetime, end_date: datetime) -> int:
        """Get total audio-confirmed detections in a time range."""
        async with self.db.execute(
            """SELECT COUNT(*)
               FROM detections
               WHERE detection_time >= ? AND detection_time <= ?
               AND audio_confirmed = 1
               AND (is_hidden = 0 OR is_hidden IS NULL)""",
            (start_date.isoformat(sep=' '), end_date.isoformat(sep=' '))
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0] or 0)

    async def get_recent_by_species(self, species_name: str, limit: int = 5, include_hidden: bool = False) -> list[Detection]:
        """Get most recent detections for a species."""
        join_sql, species_condition, params = await self._canonical_species_query_parts(
            detection_alias="d",
            species_name=species_name,
        )
        if include_hidden:
            query = f"""SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name,
                          d.category_name, d.frigate_event, d.camera_name, d.is_hidden, d.frigate_score, d.sub_label,
                          d.audio_confirmed, d.audio_species, d.audio_score, d.temperature, d.weather_condition,
                          d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                          d.weather_precipitation, d.weather_rain, d.weather_snowfall,
                          d.scientific_name, d.common_name, d.taxa_id, d.video_classification_score, d.video_classification_label,
                          d.video_classification_index, d.video_classification_timestamp, d.video_classification_status,
                          d.video_classification_error, d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                          CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                          d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
                   FROM detections d
                   LEFT JOIN detection_favorites f ON f.detection_id = d.id
                   {join_sql}
                   WHERE {species_condition}
                   ORDER BY d.detection_time DESC LIMIT ?"""
            params = [*params, limit]
        else:
            query = f"""SELECT d.id, d.detection_time, d.detection_index, d.score, d.display_name,
                          d.category_name, d.frigate_event, d.camera_name, d.is_hidden, d.frigate_score, d.sub_label,
                          d.audio_confirmed, d.audio_species, d.audio_score, d.temperature, d.weather_condition,
                          d.weather_cloud_cover, d.weather_wind_speed, d.weather_wind_direction,
                          d.weather_precipitation, d.weather_rain, d.weather_snowfall,
                          d.scientific_name, d.common_name, d.taxa_id, d.video_classification_score, d.video_classification_label,
                          d.video_classification_index, d.video_classification_timestamp, d.video_classification_status,
                          d.video_classification_error, d.ai_analysis, d.ai_analysis_timestamp, d.manual_tagged, d.notified_at,
                          CASE WHEN f.detection_id IS NULL THEN 0 ELSE 1 END AS is_favorite,
                          d.video_classification_provider, d.video_classification_backend, d.video_classification_model_id
                   FROM detections d
                   LEFT JOIN detection_favorites f ON f.detection_id = d.id
                   {join_sql}
                   WHERE {species_condition} AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
                   ORDER BY d.detection_time DESC LIMIT ?"""
            params = [*params, limit]

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]
