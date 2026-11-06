"""Atomic per-channel claims for currently eligible Garden visits."""

from app.repositories.garden_visit_repository import GardenVisitRepository


class GardenNotificationRepository(GardenVisitRepository):
    async def claim(self, capture_id: str, channel: str, attempted_at: str) -> bool:
        cte, values = await self._groups(start=None, end=None, camera=None, status="confirmed")
        cursor = await self.db.execute(
            f"""{cte} INSERT INTO garden_notification_attempts(capture_id,channel,attempted_at,state)
            SELECT m.id,?,?,'attempted' FROM members m WHERE m.id=?
              AND json_extract(m.identification,'$.outcome')='suggestion'
              AND json_extract(m.identification,'$.review')='accepted'
              AND NOT EXISTS (
                SELECT 1 FROM members other JOIN garden_notification_attempts a ON a.capture_id=other.id
                WHERE other.visit_id=m.visit_id AND a.channel=? AND a.state != 'skipped'
              ) ON CONFLICT(capture_id,channel) DO NOTHING RETURNING capture_id""",
            [*values, channel, attempted_at, capture_id, channel],
        )
        inserted = await cursor.fetchone() is not None
        await cursor.close()
        await self.db.commit()
        return inserted

    async def finish(self, capture_id: str, channel: str, state: str) -> None:
        await self.db.execute(
            "UPDATE garden_notification_attempts SET state=? WHERE capture_id=? AND channel=?",
            (state, capture_id, channel),
        )
        await self.db.commit()

    async def counts(self) -> dict[str, int]:
        result = {key: 0 for key in ["attempted", "sent", "failed", "skipped"]}
        async with self.db.execute(
            "SELECT state,COUNT(*) FROM garden_notification_attempts GROUP BY state LIMIT 4"
        ) as cursor:
            result.update(dict(await cursor.fetchall()))
        return result
