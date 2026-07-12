"""Persistence operations for expiring video-share links."""

from datetime import datetime

import aiosqlite


VIDEO_SHARE_COLUMNS = "id, frigate_event, created_by, watermark_label, created_at, expires_at, revoked"


class VideoShareRepository:
    """Own storage and lifecycle operations for video-share links."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def get_by_token_hash(self, token_hash: str) -> aiosqlite.Row | None:
        async with self.db.execute(
            "SELECT frigate_event, watermark_label, expires_at, revoked FROM video_share_links WHERE token_hash = ? LIMIT 1",
            (token_hash,),
        ) as cursor:
            return await cursor.fetchone()

    async def create(
        self,
        *,
        token_hash: str,
        event_id: str,
        created_by: str | None,
        watermark_label: str | None,
        expires_at: datetime,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO video_share_links
               (token_hash, frigate_event, created_by, watermark_label, expires_at, revoked)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (token_hash, event_id, created_by, watermark_label, expires_at),
        )
        await self.db.commit()
        return int(cursor.lastrowid or 0)

    async def list_active(self, event_id: str, now: datetime) -> list[aiosqlite.Row]:
        async with self.db.execute(
            f"""SELECT {VIDEO_SHARE_COLUMNS} FROM video_share_links
                WHERE frigate_event = ? AND revoked = 0 AND expires_at > ?
                ORDER BY created_at DESC, id DESC""",
            (event_id, now),
        ) as cursor:
            return await cursor.fetchall()

    async def get_active(self, event_id: str, link_id: int, now: datetime) -> aiosqlite.Row | None:
        async with self.db.execute(
            f"""SELECT {VIDEO_SHARE_COLUMNS} FROM video_share_links
                WHERE frigate_event = ? AND id = ? AND revoked = 0 AND expires_at > ? LIMIT 1""",
            (event_id, link_id, now),
        ) as cursor:
            return await cursor.fetchone()

    async def update_active(
        self,
        event_id: str,
        link_id: int,
        *,
        expires_at: datetime | None,
        update_watermark: bool,
        watermark_label: str | None,
    ) -> aiosqlite.Row | None:
        updates: list[str] = []
        params: list[object] = []
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)
        if update_watermark:
            updates.append("watermark_label = ?")
            params.append(watermark_label)
        if not updates:
            return None
        await self.db.execute(
            f"UPDATE video_share_links SET {', '.join(updates)} WHERE frigate_event = ? AND id = ?",
            (*params, event_id, link_id),
        )
        await self.db.commit()
        async with self.db.execute(
            f"SELECT {VIDEO_SHARE_COLUMNS} FROM video_share_links WHERE frigate_event = ? AND id = ? LIMIT 1",
            (event_id, link_id),
        ) as cursor:
            return await cursor.fetchone()

    async def revoke_active(self, event_id: str, link_id: int, now: datetime) -> bool:
        cursor = await self.db.execute(
            """UPDATE video_share_links SET revoked = 1
               WHERE frigate_event = ? AND id = ? AND revoked = 0 AND expires_at > ?""",
            (event_id, link_id, now),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def delete_expired_or_revoked(self, now: datetime) -> int:
        cursor = await self.db.execute("DELETE FROM video_share_links WHERE expires_at <= ? OR revoked = 1", (now,))
        await self.db.commit()
        return max(0, cursor.rowcount)
