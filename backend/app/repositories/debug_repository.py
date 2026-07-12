import aiosqlite
import structlog

log = structlog.get_logger()


class DebugRepository:
    """Read-only database diagnostics used by the owner debug API."""

    _COUNTABLE_TABLES = ("detections", "taxonomy_cache")

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def table_counts(self) -> dict[str, int | str]:
        counts: dict[str, int | str] = {}
        for table in self._COUNTABLE_TABLES:
            try:
                async with self.db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    row = await cursor.fetchone()
                counts[table] = int(row[0]) if row else 0
            except aiosqlite.Error as exc:
                log.warning("Debug table count failed", table=table, error=str(exc))
                counts[table] = f"Error: {exc}"
        return counts
