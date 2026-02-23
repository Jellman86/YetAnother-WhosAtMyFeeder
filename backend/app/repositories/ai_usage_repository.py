import aiosqlite
import structlog
from datetime import datetime
from typing import List, Dict, Optional
from app.models.ai_models import AIUsageLog

log = structlog.get_logger()

class AIUsageRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def record_usage(self, provider: str, model: str, feature: str, input_tokens: int, output_tokens: int, timestamp: Optional[datetime] = None):
        """Record an AI API usage event."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        total_tokens = input_tokens + output_tokens
        
        try:
            await self.db.execute(
                """INSERT INTO ai_usage_log (timestamp, provider, model, feature, input_tokens, output_tokens, total_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (timestamp.isoformat(), provider, model, feature, input_tokens, output_tokens, total_tokens)
            )
            await self.db.commit()
        except Exception as e:
            log.error("Failed to record AI usage", error=str(e), provider=provider, model=model)

    async def get_summary(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get aggregated usage summary for a time range."""
        summary = {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "breakdown": [],
            "daily": []
        }

        # 1. Overall totals
        async with self.db.execute(
            """SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(total_tokens)
               FROM ai_usage_log
               WHERE timestamp >= ? AND timestamp <= ?""",
            (start_date.isoformat(), end_date.isoformat())
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                summary["calls"] = row[0]
                summary["input_tokens"] = row[1] or 0
                summary["output_tokens"] = row[2] or 0
                summary["total_tokens"] = row[3] or 0

        # 2. Breakdown by provider/model/feature
        async with self.db.execute(
            """SELECT provider, model, feature, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(total_tokens)
               FROM ai_usage_log
               WHERE timestamp >= ? AND timestamp <= ?
               GROUP BY provider, model, feature
               ORDER BY SUM(total_tokens) DESC""",
            (start_date.isoformat(), end_date.isoformat())
        ) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                summary["breakdown"].append({
                    "provider": r[0],
                    "model": r[1],
                    "feature": r[2],
                    "calls": r[3],
                    "input_tokens": r[4] or 0,
                    "output_tokens": r[5] or 0,
                    "total_tokens": r[6] or 0
                })

        # 3. Daily totals
        async with self.db.execute(
            """SELECT date(timestamp) as day, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(total_tokens)
               FROM ai_usage_log
               WHERE timestamp >= ? AND timestamp <= ?
               GROUP BY day
               ORDER BY day ASC""",
            (start_date.isoformat(), end_date.isoformat())
        ) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                summary["daily"].append({
                    "day": r[0],
                    "calls": r[1],
                    "input_tokens": r[2] or 0,
                    "output_tokens": r[3] or 0,
                    "total_tokens": r[4] or 0
                })

        return summary

    async def clear_history(self) -> int:
        """Clear all usage logs. Returns number of rows deleted."""
        async with self.db.execute("DELETE FROM ai_usage_log") as cursor:
            count = cursor.rowcount
            await self.db.commit()
            return count or 0
