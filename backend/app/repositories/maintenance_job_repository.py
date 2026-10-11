"""Durable, bounded maintenance summaries; interrupted jobs remain inspectable."""

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite


class MaintenanceJobRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def save(self, payload: dict[str, Any]) -> None:
        await self.db.execute(
            """INSERT INTO maintenance_job_history (id, kind, status, payload_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
            (payload["id"], payload["kind"], payload["status"], json.dumps(payload)),
        )
        await self.db.execute(
            """DELETE FROM maintenance_job_history WHERE status != 'running' AND id NOT IN
            (SELECT id FROM maintenance_job_history ORDER BY updated_at DESC, rowid DESC LIMIT 100)"""
        )
        await self.db.commit()

    async def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT payload_json FROM maintenance_job_history ORDER BY updated_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [json.loads(row[0]) for row in rows]

    async def get(self, job_id: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT payload_json FROM maintenance_job_history WHERE id=?", (job_id,)) as cursor:
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def latest(self, kind: str | None = None) -> dict[str, Any] | None:
        condition = "WHERE kind=?" if kind else ""
        async with self.db.execute(
            f"SELECT payload_json FROM maintenance_job_history {condition} ORDER BY updated_at DESC, rowid DESC LIMIT 1",
            (kind,) if kind else (),
        ) as cursor:
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def recover_interrupted(self) -> None:
        async with self.db.execute(
            "SELECT payload_json FROM maintenance_job_history WHERE status='running' LIMIT 100"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            payload = json.loads(row[0])
            payload.update(
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                message="Interrupted by application restart. Saved progress is retained.",
            )
            await self.save(payload)
