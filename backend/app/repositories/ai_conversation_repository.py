from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import aiosqlite


@dataclass
class ConversationTurn:
    id: int
    frigate_event: str
    role: str
    content: str
    created_at: datetime


class AIConversationRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def delete_turns(self, frigate_event: str) -> None:
        await self.db.execute(
            "DELETE FROM ai_conversation_turns WHERE frigate_event = ?",
            (frigate_event,),
        )
        await self.db.commit()

    async def list_turns(self, frigate_event: str) -> list[ConversationTurn]:
        query = (
            "SELECT id, frigate_event, role, content, created_at "
            "FROM ai_conversation_turns WHERE frigate_event = ? "
            "ORDER BY created_at ASC, id ASC"
        )
        async with self.db.execute(query, (frigate_event,)) as cursor:
            rows = await cursor.fetchall()
        return [
            ConversationTurn(
                id=row[0],
                frigate_event=row[1],
                role=row[2],
                content=row[3],
                created_at=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
            )
            for row in rows
        ]

    async def add_turn(self, frigate_event: str, role: str, content: str) -> ConversationTurn:
        await self.db.execute(
            "INSERT INTO ai_conversation_turns (frigate_event, role, content) VALUES (?, ?, ?)",
            (frigate_event, role, content)
        )
        await self.db.commit()
        async with self.db.execute(
            "SELECT id, frigate_event, role, content, created_at "
            "FROM ai_conversation_turns WHERE rowid = last_insert_rowid()"
        ) as cursor:
            row = await cursor.fetchone()
        return ConversationTurn(
            id=row[0],
            frigate_event=row[1],
            role=row[2],
            content=row[3],
            created_at=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
        )
