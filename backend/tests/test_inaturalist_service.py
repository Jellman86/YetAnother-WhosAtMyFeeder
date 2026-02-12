from contextlib import asynccontextmanager

import aiosqlite
import pytest

from app.services.inaturalist_service import InaturalistService


@pytest.mark.asyncio
async def test_delete_token_reports_exact_row_changes(monkeypatch):
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE oauth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                email TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                token_type TEXT,
                expires_at TIMESTAMP,
                scope TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "INSERT INTO oauth_tokens (provider, email, access_token) VALUES (?, ?, ?)",
            ("inaturalist", "bird@example.com", "token")
        )
        await db.commit()

        @asynccontextmanager
        async def fake_get_db():
            yield db

        monkeypatch.setattr("app.services.inaturalist_service.get_db", fake_get_db)

        service = InaturalistService()
        assert await service.delete_token() is True
        assert await service.delete_token() is False
