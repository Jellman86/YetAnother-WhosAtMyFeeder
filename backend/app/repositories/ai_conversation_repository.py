from dataclasses import dataclass
from datetime import datetime

import aiosqlite
from app.repositories.detection_repository import AIAnalysisRevision


@dataclass
class ConversationTurn:
    id: int
    frigate_event: str
    role: str
    content: str
    created_at: datetime


class AIConversationRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def delete_turns(self, frigate_event: str) -> None:
        await self.db.execute(
            "DELETE FROM ai_conversation_turns WHERE frigate_event = ?",
            (frigate_event,),
        )
        await self.db.commit()

    async def add_reply_if_context_current(
        self,
        frigate_event: str,
        question_id: int,
        content: str,
        revision: AIAnalysisRevision,
    ) -> bool:
        """A reply to an old analysis cannot repopulate a regenerated thread."""
        cursor = await self.db.execute(
            """INSERT INTO ai_conversation_turns (frigate_event, role, content)
               SELECT frigate_event, 'assistant', ? FROM detections
               WHERE frigate_event = ? AND ai_analysis IS ? AND ai_analysis_timestamp IS ?
                 AND EXISTS (SELECT 1 FROM ai_conversation_turns
                             WHERE id = ? AND frigate_event = ? AND role = 'user')""",
            (content, frigate_event, revision.analysis, revision.timestamp, question_id, frigate_event),
        )
        await self.db.commit()
        return cursor.rowcount == 1

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
            (frigate_event, role, content),
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
