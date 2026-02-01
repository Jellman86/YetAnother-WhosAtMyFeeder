from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json
import aiosqlite


@dataclass
class LeaderboardAnalysis:
    id: int
    config_key: str
    config_json: str
    analysis: str
    analysis_timestamp: datetime
    created_at: datetime


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                if fmt is None:
                    return datetime.fromisoformat(value)
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return datetime.now()


class LeaderboardAnalysisRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_by_config_key(self, config_key: str) -> Optional[LeaderboardAnalysis]:
        async with self.db.execute(
            """SELECT id, config_key, config_json, analysis, analysis_timestamp, created_at
               FROM leaderboard_analyses WHERE config_key = ?""",
            (config_key,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return LeaderboardAnalysis(
            id=row[0],
            config_key=row[1],
            config_json=row[2],
            analysis=row[3],
            analysis_timestamp=_parse_datetime(row[4]) if row[4] else datetime.now(),
            created_at=_parse_datetime(row[5]) if row[5] else datetime.now()
        )

    async def upsert_analysis(self, config_key: str, config_json: dict, analysis: str, timestamp: datetime):
        config_str = json.dumps(config_json, sort_keys=True)
        await self.db.execute(
            """INSERT INTO leaderboard_analyses (config_key, config_json, analysis, analysis_timestamp, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(config_key) DO UPDATE SET
                   config_json = excluded.config_json,
                   analysis = excluded.analysis,
                   analysis_timestamp = excluded.analysis_timestamp
            """,
            (config_key, config_str, analysis, timestamp, timestamp)
        )
        await self.db.commit()
