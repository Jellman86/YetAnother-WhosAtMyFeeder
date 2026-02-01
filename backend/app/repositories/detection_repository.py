from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, date
import aiosqlite
import asyncio
import json

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
    return datetime.now()


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
        sub_label=row[10] if len(row) > 10 else None,
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

    return d


class DetectionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_by_frigate_event(self, frigate_event: str) -> Optional[Detection]:
        async with self.db.execute(
            "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, video_classification_score, video_classification_label, video_classification_index, video_classification_timestamp, video_classification_status, video_classification_error, ai_analysis, ai_analysis_timestamp, manual_tagged, notified_at FROM detections WHERE frigate_event = ?",
            (frigate_event,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

    async def update_video_classification(self, frigate_event: str, label: str, score: float, index: int, status: str = 'completed'):
        """Update video classification results for an event."""
        now = datetime.now()
        await self.db.execute("""
            UPDATE detections
            SET video_classification_label = ?,
                video_classification_score = ?,
                video_classification_index = ?,
                video_classification_timestamp = ?,
                video_classification_status = ?,
                video_classification_error = NULL
            WHERE frigate_event = ?
        """, (label, score, index, now, status, frigate_event))
        await self.db.commit()

    async def update_video_status(self, frigate_event: str, status: str, error: Optional[str] = None):
        """Update just the video classification status."""
        now = datetime.now()
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
        now = datetime.now()
        await self.db.execute("""
            UPDATE detections
            SET video_classification_status = 'failed',
                video_classification_error = 'stale_timeout',
                video_classification_timestamp = ?
            WHERE video_classification_status IN ('pending', 'processing')
              AND (video_classification_timestamp IS NULL
                   OR video_classification_timestamp < datetime('now', ?))
        """, (now, f'-{max_age_minutes} minutes'))
        await self.db.commit()
        cur = await self.db.execute("SELECT changes()")
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def mark_notified(self, frigate_event: str, timestamp: Optional[datetime] = None):
        """Mark a detection as notified."""
        if timestamp is None:
            timestamp = datetime.now()
        await self.db.execute(
            "UPDATE detections SET notified_at = ? WHERE frigate_event = ?",
            (timestamp, frigate_event)
        )
        await self.db.commit()

    async def update_ai_analysis(self, frigate_event: str, analysis: str):
        """Update AI naturalist analysis for an event."""
        now = datetime.now()
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
        await self.db.commit()
        return self.db.total_changes > 0

    async def delete_by_frigate_event(self, frigate_event: str) -> bool:
        """Delete a detection by Frigate event ID. Returns True if deleted."""
        await self.db.execute("DELETE FROM detections WHERE frigate_event = ?", (frigate_event,))
        await self.db.commit()
        return self.db.total_changes > 0

    async def create(self, detection: Detection):
        await self.db.execute("""
            INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, manual_tagged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_event, detection.camera_name, 1 if detection.is_hidden else 0, detection.frigate_score, detection.sub_label, 1 if detection.audio_confirmed else 0, detection.audio_species, detection.audio_score, detection.temperature, detection.weather_condition, detection.weather_cloud_cover, detection.weather_wind_speed, detection.weather_wind_direction, detection.weather_precipitation, detection.weather_rain, detection.weather_snowfall, detection.scientific_name, detection.common_name, detection.taxa_id, 1 if detection.manual_tagged else 0))
        await self.db.commit()

    async def update(self, detection: Detection):
        await self.db.execute("""
            UPDATE detections
            SET detection_time = ?, detection_index = ?, score = ?, display_name = ?, category_name = ?, frigate_score = ?, sub_label = ?, audio_confirmed = ?, audio_species = ?, audio_score = ?, temperature = ?, weather_condition = ?, weather_cloud_cover = ?, weather_wind_speed = ?, weather_wind_direction = ?, weather_precipitation = ?, weather_rain = ?, weather_snowfall = ?, scientific_name = ?, common_name = ?, taxa_id = ?, manual_tagged = ?
            WHERE frigate_event = ?
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_score, detection.sub_label, detection.audio_confirmed, detection.audio_species, detection.audio_score, detection.temperature, detection.weather_condition, detection.weather_cloud_cover, detection.weather_wind_speed, detection.weather_wind_direction, detection.weather_precipitation, detection.weather_rain, detection.weather_snowfall, detection.scientific_name, detection.common_name, detection.taxa_id, 1 if detection.manual_tagged else 0, detection.frigate_event))
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
        """Atomically insert or update a detection, only updating if new score is higher.

        Uses SQLite's ON CONFLICT clause to prevent race conditions.

        Args:
            detection: The detection to insert or update

        Returns:
            Tuple of (was_inserted, was_updated)
        """
        # First, check if the event already exists to distinguish insert vs update.
        existing = await self.get_by_frigate_event(detection.frigate_event)
        was_existing = existing is not None

        # Then, try to insert. If conflict on frigate_event, update only if score is higher.
        # SQLite's ON CONFLICT DO UPDATE with WHERE clause handles this atomically.
        await self.db.execute("""
            INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, manual_tagged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(frigate_event) DO UPDATE SET
                detection_time = excluded.detection_time,
                detection_index = excluded.detection_index,
                score = excluded.score,
                display_name = excluded.display_name,
                category_name = excluded.category_name,
                frigate_score = excluded.frigate_score,
                sub_label = excluded.sub_label,
                audio_confirmed = excluded.audio_confirmed,
                audio_species = excluded.audio_species,
                audio_score = excluded.audio_score,
                temperature = excluded.temperature,
                weather_condition = excluded.weather_condition,
                weather_cloud_cover = excluded.weather_cloud_cover,
                weather_wind_speed = excluded.weather_wind_speed,
                weather_wind_direction = excluded.weather_wind_direction,
                weather_precipitation = excluded.weather_precipitation,
                weather_rain = excluded.weather_rain,
                weather_snowfall = excluded.weather_snowfall,
                scientific_name = excluded.scientific_name,
                common_name = excluded.common_name,
                taxa_id = excluded.taxa_id,
                manual_tagged = detections.manual_tagged
            WHERE excluded.score > detections.score OR (excluded.audio_confirmed = 1 AND detections.audio_confirmed = 0)
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
            detection.sub_label,
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
            1 if detection.manual_tagged else 0
        ))

        changes = self.db.total_changes
        await self.db.commit()

        if changes == 0:
            return (False, False)
        if was_existing:
            return (False, True)
        return (True, False)

    async def insert_if_not_exists(self, detection: Detection) -> bool:
        """Atomically insert a detection only if it doesn't already exist.

        Uses SQLite's INSERT OR IGNORE to prevent race conditions.
        Useful for backfill operations where we don't want to update existing records.

        Args:
            detection: The detection to insert

        Returns:
            True if inserted, False if already existed
        """
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
            detection.sub_label,
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

        changes = self.db.total_changes
        await self.db.commit()
        return changes > 0

    async def get_all(
        self,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        species: str | None = None,
        camera: str | None = None,
        sort: str = "newest",
        include_hidden: bool = False
    ) -> list[Detection]:
        query = "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label, audio_confirmed, audio_species, audio_score, temperature, weather_condition, weather_cloud_cover, weather_wind_speed, weather_wind_direction, weather_precipitation, weather_rain, weather_snowfall, scientific_name, common_name, taxa_id, video_classification_score, video_classification_label, video_classification_index, video_classification_timestamp, video_classification_status, video_classification_error, ai_analysis, ai_analysis_timestamp, manual_tagged, notified_at FROM detections"
        params: list = []
        conditions = []

        # By default, exclude hidden detections
        if not include_hidden:
            conditions.append("(is_hidden = 0 OR is_hidden IS NULL)")

        if start_date:
            conditions.append("detection_time >= ?")
            params.append(start_date.isoformat(sep=' '))
        if end_date:
            conditions.append("detection_time <= ?")
            params.append(end_date.isoformat(sep=' '))
        if species:
            conditions.append("display_name = ?")
            params.append(species)
        if camera:
            conditions.append("camera_name = ?")
            params.append(camera)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Apply sort order
        if sort == "oldest":
            query += " ORDER BY detection_time ASC"
        elif sort == "confidence":
            query += " ORDER BY score DESC, detection_time DESC"
        else:  # newest (default)
            query += " ORDER BY detection_time DESC"

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
        camera: str | None = None,
        include_hidden: bool = False
    ) -> int:
        """Get total count of detections, optionally filtered."""
        query = "SELECT COUNT(*) FROM detections"
        params: list = []
        conditions = []

        # By default, exclude hidden detections
        if not include_hidden:
            conditions.append("(is_hidden = 0 OR is_hidden IS NULL)")

        if start_date:
            conditions.append("detection_time >= ?")
            params.append(start_date.isoformat(sep=' '))
        if end_date:
            conditions.append("detection_time <= ?")
            params.append(end_date.isoformat(sep=' '))
        if species:
            conditions.append("display_name = ?")
            params.append(species)
        if camera:
            conditions.append("camera_name = ?")
            params.append(camera)

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

    async def get_unique_cameras(self) -> list[str]:
        """Get list of unique camera names, sorted alphabetically."""
        async with self.db.execute(
            "SELECT DISTINCT camera_name FROM detections ORDER BY camera_name ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_taxonomy_names(self, name: str) -> dict:
        """Get scientific and common names for a given species name from cache."""
        async with self.db.execute(
            "SELECT scientific_name, common_name FROM taxonomy_cache WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)",
            (name, name)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"scientific_name": row[0], "common_name": row[1]}
        return {"scientific_name": None, "common_name": None}

    async def delete_older_than(self, cutoff_date: datetime, chunk_size: int = 1000) -> int:
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
                    SELECT id FROM detections 
                    WHERE detection_time < ? 
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
        """Get all detections labeled as 'Unknown Bird'."""
        query = """
            SELECT id, detection_time, detection_index, score, display_name, category_name, 
                   frigate_event, camera_name, is_hidden, frigate_score, sub_label, 
                   audio_confirmed, audio_species, audio_score, temperature, weather_condition,
                   weather_cloud_cover, weather_wind_speed, weather_wind_direction,
                   weather_precipitation, weather_rain, weather_snowfall,
                   scientific_name, common_name, taxa_id, video_classification_score, 
                   video_classification_label, video_classification_index, 
                   video_classification_timestamp, video_classification_status, 
                   video_classification_error, ai_analysis, ai_analysis_timestamp, 
                   manual_tagged, notified_at
            FROM detections 
            WHERE display_name = 'Unknown Bird'
        """
        async with self.db.execute(query) as cursor:
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

    async def get_species_counts(self) -> list[dict]:
        """Get detection counts per species with taxonomic metadata."""
        query = """
            SELECT 
                COALESCE(t.scientific_name, LOWER(d.display_name)) as unified_id,
                COUNT(*) as count, 
                MAX(COALESCE(d.scientific_name, t.scientific_name)) as scientific_name, 
                MAX(COALESCE(d.common_name, t.common_name)) as common_name,
                MAX(d.display_name) as display_name,
                MAX(COALESCE(d.taxa_id, t.taxa_id)) as taxa_id
            FROM detections d
            LEFT JOIN taxonomy_cache t ON 
                LOWER(d.display_name) = LOWER(t.scientific_name) OR 
                LOWER(d.display_name) = LOWER(t.common_name)
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
                COALESCE(t.scientific_name, LOWER(d.display_name)) as unified_id,
                COUNT(*) as total_count, 
                MAX(COALESCE(d.scientific_name, t.scientific_name)) as scientific_name, 
                MAX(COALESCE(d.common_name, t.common_name)) as common_name,
                MAX(d.display_name) as display_name,
                MAX(COALESCE(d.taxa_id, t.taxa_id)) as taxa_id,
                MIN(d.detection_time) as first_seen,
                MAX(d.detection_time) as last_seen,
                AVG(d.score) as avg_confidence,
                MAX(d.score) as max_confidence,
                MIN(d.score) as min_confidence,
                COUNT(DISTINCT d.camera_name) as camera_count
            FROM detections d
            LEFT JOIN taxonomy_cache t ON 
                LOWER(d.display_name) = LOWER(t.scientific_name) OR 
                LOWER(d.display_name) = LOWER(t.common_name)
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
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        query = """
            SELECT 
                date(detection_time) as rollup_date,
                display_name,
                COUNT(*) as detection_count,
                COUNT(DISTINCT camera_name) as camera_count,
                AVG(score) as avg_confidence,
                MAX(score) as max_confidence,
                MIN(score) as min_confidence,
                MIN(detection_time) as first_seen,
                MAX(detection_time) as last_seen
            FROM detections
            WHERE detection_time >= ? AND detection_time < ?
              AND (is_hidden = 0 OR is_hidden IS NULL)
            GROUP BY rollup_date, display_name
        """
        async with self.db.execute(query, (start_dt, end_dt)) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            return
        await self.db.executemany(
            """INSERT INTO species_daily_rollup
                   (rollup_date, display_name, detection_count, camera_count,
                    avg_confidence, max_confidence, min_confidence, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(rollup_date, display_name) DO UPDATE SET
                    detection_count=excluded.detection_count,
                    camera_count=excluded.camera_count,
                    avg_confidence=excluded.avg_confidence,
                    max_confidence=excluded.max_confidence,
                    min_confidence=excluded.min_confidence,
                    first_seen=excluded.first_seen,
                    last_seen=excluded.last_seen
            """,
            rows
        )
        await self.db.commit()

    async def get_rollup_metrics(self, lookback_days: int = 30) -> dict[str, dict]:
        """Aggregate rollup metrics for leaderboard windows."""
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
        window = f"-{lookback_days} day"
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

    async def get_species_basic_stats(self, species_name: str) -> dict:
        """Get basic stats for a species: count, min/max dates, confidence stats."""
        async with self.db.execute(
            """SELECT COUNT(*), MIN(detection_time), MAX(detection_time),
                      AVG(score), MAX(score), MIN(score)
               FROM detections WHERE display_name = ?""",
            (species_name,)
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

    async def get_camera_breakdown(self, species_name: str) -> list[dict]:
        """Get detection counts grouped by camera."""
        async with self.db.execute(
            """SELECT camera_name, COUNT(*) as count
               FROM detections WHERE display_name = ?
               GROUP BY camera_name ORDER BY count DESC""",
            (species_name,)
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
        async with self.db.execute(
            """SELECT strftime('%H', detection_time) as hour, COUNT(*)
               FROM detections WHERE display_name = ?
               GROUP BY hour""",
            (species_name,)
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 24
            for row in rows:
                hour = int(row[0])
                distribution[hour] = row[1]
            return distribution

    async def get_daily_distribution(self, species_name: str) -> list[int]:
        """Get 7-element list of detection counts per day of week (0=Sunday)."""
        async with self.db.execute(
            """SELECT strftime('%w', detection_time) as dow, COUNT(*)
               FROM detections WHERE display_name = ?
               GROUP BY dow""",
            (species_name,)
        ) as cursor:
            rows = await cursor.fetchall()
            distribution = [0] * 7
            for row in rows:
                dow = int(row[0])
                distribution[dow] = row[1]
            return distribution

    async def get_monthly_distribution(self, species_name: str) -> list[int]:
        """Get 12-element list of detection counts per month (1-12)."""
        async with self.db.execute(
            """SELECT strftime('%m', detection_time) as month, COUNT(*)
               FROM detections WHERE display_name = ?
               GROUP BY month""",
            (species_name,)
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
            SELECT 
                COALESCE(t.scientific_name, LOWER(d.display_name)) as unified_id,
                COUNT(*) as count, 
                MAX(d.frigate_event) as latest_event,
                MAX(COALESCE(d.scientific_name, t.scientific_name)) as scientific_name, 
                MAX(COALESCE(d.common_name, t.common_name)) as common_name,
                MAX(d.display_name) as display_name,
                MAX(COALESCE(d.taxa_id, t.taxa_id)) as taxa_id
            FROM detections d
            LEFT JOIN taxonomy_cache t ON 
                LOWER(d.display_name) = LOWER(t.scientific_name) OR 
                LOWER(d.display_name) = LOWER(t.common_name)
            WHERE d.detection_time >= ? AND d.detection_time <= ?
            AND (d.is_hidden = 0 OR d.is_hidden IS NULL)
            GROUP BY unified_id
            ORDER BY count DESC
        """
        async with self.db.execute(query, (start_date.isoformat(sep=' '), end_date.isoformat(sep=' '))) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "species": row[5], 
                    "count": row[1],
                    "latest_event": row[2],
                    "scientific_name": row[3],
                    "common_name": row[4],
                    "taxa_id": row[6]
                }
                for row in rows
            ]

    async def insert_audio_detection(
        self,
        timestamp: datetime,
        species: str,
        confidence: float,
        sensor_id: Optional[str],
        raw_data: Optional[dict]
    ) -> None:
        payload = json.dumps(raw_data or {}, ensure_ascii=True)
        await self.db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp.isoformat(sep=' '), species, confidence, sensor_id, payload)
        )
        await self.db.commit()

    async def get_audio_context(
        self,
        target_time: datetime,
        window_seconds: int,
        sensor_id: Optional[str],
        limit: int
    ) -> list[dict]:
        start_dt = target_time - timedelta(seconds=window_seconds)
        end_dt = target_time + timedelta(seconds=window_seconds)
        query = """SELECT timestamp, species, confidence, sensor_id
                   FROM audio_detections
                   WHERE timestamp >= ? AND timestamp <= ?"""
        params: list = [start_dt.isoformat(sep=' '), end_dt.isoformat(sep=' ')]
        if sensor_id:
            query += " AND sensor_id = ?"
            params.append(sensor_id)
        query += " ORDER BY timestamp DESC"

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        results: list[dict] = []
        for row in rows:
            det_time = _parse_datetime(row[0])
            offset_seconds = int((det_time - target_time).total_seconds())
            results.append({
                "timestamp": det_time.isoformat(),
                "species": row[1],
                "confidence": row[2],
                "sensor_id": row[3],
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
        if include_hidden:
            query = """SELECT id, detection_time, detection_index, score, display_name,
                          category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label,
                          audio_confirmed, audio_species, audio_score, temperature, weather_condition,
                          weather_cloud_cover, weather_wind_speed, weather_wind_direction,
                          weather_precipitation, weather_rain, weather_snowfall,
                          scientific_name, common_name, taxa_id, video_classification_score, video_classification_label,
                          video_classification_index, video_classification_timestamp, video_classification_status,
                          video_classification_error, ai_analysis, ai_analysis_timestamp
                   FROM detections WHERE display_name = ?
                   ORDER BY detection_time DESC LIMIT ?"""
            params = (species_name, limit)
        else:
            query = """SELECT id, detection_time, detection_index, score, display_name,
                          category_name, frigate_event, camera_name, is_hidden, frigate_score, sub_label,
                          audio_confirmed, audio_species, audio_score, temperature, weather_condition,
                          weather_cloud_cover, weather_wind_speed, weather_wind_direction,
                          weather_precipitation, weather_rain, weather_snowfall,
                          scientific_name, common_name, taxa_id, video_classification_score, video_classification_label,
                          video_classification_index, video_classification_timestamp, video_classification_status,
                          video_classification_error, ai_analysis, ai_analysis_timestamp
                   FROM detections WHERE display_name = ? AND (is_hidden = 0 OR is_hidden IS NULL)
                   ORDER BY detection_time DESC LIMIT ?"""
            params = (species_name, limit)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]
