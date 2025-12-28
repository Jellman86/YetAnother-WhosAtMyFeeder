from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import aiosqlite

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
    return Detection(
        id=row[0],
        detection_time=_parse_datetime(row[1]),
        detection_index=row[2],
        score=row[3],
        display_name=row[4],
        category_name=row[5],
        frigate_event=row[6],
        camera_name=row[7],
        is_hidden=bool(row[8]) if len(row) > 8 else False
    )


class DetectionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_by_frigate_event(self, frigate_event: str) -> Optional[Detection]:
        async with self.db.execute(
            "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden FROM detections WHERE frigate_event = ?",
            (frigate_event,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

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
            INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_event, detection.camera_name))
        await self.db.commit()

    async def update(self, detection: Detection):
        await self.db.execute("""
            UPDATE detections
            SET detection_time = ?, detection_index = ?, score = ?, display_name = ?, category_name = ?
            WHERE frigate_event = ?
        """, (detection.detection_time, detection.detection_index, detection.score, detection.display_name, detection.category_name, detection.frigate_event))
        await self.db.commit()

    async def upsert_if_higher_score(self, detection: Detection) -> tuple[bool, bool]:
        """Atomically insert or update a detection, only updating if new score is higher.

        Uses SQLite's ON CONFLICT clause to prevent race conditions.

        Args:
            detection: The detection to insert or update

        Returns:
            Tuple of (was_inserted, was_updated)
        """
        # First, try to insert. If conflict on frigate_event, update only if score is higher.
        # SQLite's ON CONFLICT DO UPDATE with WHERE clause handles this atomically.
        await self.db.execute("""
            INSERT INTO detections (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(frigate_event) DO UPDATE SET
                detection_time = excluded.detection_time,
                detection_index = excluded.detection_index,
                score = excluded.score,
                display_name = excluded.display_name,
                category_name = excluded.category_name
            WHERE excluded.score > detections.score
        """, (
            detection.detection_time,
            detection.detection_index,
            detection.score,
            detection.display_name,
            detection.category_name,
            detection.frigate_event,
            detection.camera_name
        ))

        changes = self.db.total_changes
        await self.db.commit()

        # Determine what happened:
        # - If changes > 0 and row was new: inserted
        # - If changes > 0 and row existed: updated (score was higher)
        # - If changes == 0: row existed but score wasn't higher
        # We can't perfectly distinguish insert vs update without extra query,
        # but for logging purposes we return (changes > 0, False) for simplicity
        return (changes > 0, False)

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
            (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            detection.detection_time,
            detection.detection_index,
            detection.score,
            detection.display_name,
            detection.category_name,
            detection.frigate_event,
            detection.camera_name
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
        query = "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name, is_hidden FROM detections"
        params: list = []
        conditions = []

        # By default, exclude hidden detections
        if not include_hidden:
            conditions.append("(is_hidden = 0 OR is_hidden IS NULL)")

        if start_date:
            conditions.append("detection_time >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("detection_time <= ?")
            params.append(end_date.isoformat())
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
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("detection_time <= ?")
            params.append(end_date.isoformat())
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

    async def delete_older_than(self, cutoff_date: datetime) -> int:
        """Delete detections older than the cutoff date. Returns count of deleted rows."""
        async with self.db.execute(
            "SELECT COUNT(*) FROM detections WHERE detection_time < ?",
            (cutoff_date.isoformat(),)
        ) as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0

        if count > 0:
            await self.db.execute(
                "DELETE FROM detections WHERE detection_time < ?",
                (cutoff_date.isoformat(),)
            )
            await self.db.commit()

        return count

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
        async with self.db.execute(
            "SELECT display_name, COUNT(*) as count FROM detections GROUP BY display_name ORDER BY count DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"species": row[0], "count": row[1]} for row in rows]

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

    async def get_recent_by_species(self, species_name: str, limit: int = 5, include_hidden: bool = False) -> list[Detection]:
        """Get most recent detections for a species."""
        if include_hidden:
            query = """SELECT id, detection_time, detection_index, score, display_name,
                          category_name, frigate_event, camera_name, is_hidden
                   FROM detections WHERE display_name = ?
                   ORDER BY detection_time DESC LIMIT ?"""
            params = (species_name, limit)
        else:
            query = """SELECT id, detection_time, detection_index, score, display_name,
                          category_name, frigate_event, camera_name, is_hidden
                   FROM detections WHERE display_name = ? AND (is_hidden = 0 OR is_hidden IS NULL)
                   ORDER BY detection_time DESC LIMIT ?"""
            params = (species_name, limit)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]
