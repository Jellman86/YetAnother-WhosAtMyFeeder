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
        camera_name=row[7]
    )


class DetectionRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_by_frigate_event(self, frigate_event: str) -> Optional[Detection]:
        async with self.db.execute(
            "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name FROM detections WHERE frigate_event = ?",
            (frigate_event,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_detection(row)
            return None

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

    async def get_all(
        self,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        species: str | None = None,
        camera: str | None = None,
        sort: str = "newest"
    ) -> list[Detection]:
        query = "SELECT id, detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name FROM detections"
        params: list = []
        conditions = []

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
        camera: str | None = None
    ) -> int:
        """Get total count of detections, optionally filtered."""
        query = "SELECT COUNT(*) FROM detections"
        params: list = []
        conditions = []

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

    async def get_recent_by_species(self, species_name: str, limit: int = 5) -> list[Detection]:
        """Get most recent detections for a species."""
        async with self.db.execute(
            """SELECT id, detection_time, detection_index, score, display_name,
                      category_name, frigate_event, camera_name
               FROM detections WHERE display_name = ?
               ORDER BY detection_time DESC LIMIT ?""",
            (species_name, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_detection(row) for row in rows]
