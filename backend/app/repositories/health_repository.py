from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite
import structlog

log = structlog.get_logger()

#: Heartbeats older than this are pruned; the About window only reaches back a day,
#: and a week is enough to answer "was it up yesterday?" without growing forever.
HEALTH_SAMPLE_RETENTION_DAYS = 7


class HealthRepository:
    """Heartbeat rows: proof the application was running at a point in time."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def record_heartbeat(self, instance_id: str, sampled_at: Optional[datetime] = None) -> None:
        moment = sampled_at or datetime.now(timezone.utc)
        await self.db.execute(
            "INSERT INTO health_samples (sampled_at, instance_id) VALUES (?, ?)",
            (moment.replace(tzinfo=None), instance_id),
        )
        await self.db.commit()

    async def list_samples_since(self, cutoff: datetime) -> list[datetime]:
        cursor = await self.db.execute(
            "SELECT sampled_at FROM health_samples WHERE sampled_at >= ? ORDER BY sampled_at ASC",
            (cutoff.replace(tzinfo=None),),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_parse(row[0]) for row in rows if row[0] is not None]

    async def first_sample_at(self) -> Optional[datetime]:
        cursor = await self.db.execute("SELECT MIN(sampled_at) FROM health_samples")
        row = await cursor.fetchone()
        await cursor.close()
        if not row or row[0] is None:
            return None
        return _parse(row[0])

    async def prune(self, retention_days: int = HEALTH_SAMPLE_RETENTION_DAYS) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cursor = await self.db.execute(
            "DELETE FROM health_samples WHERE sampled_at < ?", (cutoff.replace(tzinfo=None),)
        )
        await self.db.commit()
        removed = cursor.rowcount or 0
        await cursor.close()
        if removed:
            log.info("health_samples_pruned", removed=removed, retention_days=retention_days)
        return removed


def _parse(value: object) -> datetime:
    """SQLite hands back naive strings or datetimes; heartbeats are always UTC."""
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value))
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment
