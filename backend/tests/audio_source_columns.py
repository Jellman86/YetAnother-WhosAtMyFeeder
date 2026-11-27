"""Rows a test inserts by hand, given the source columns the upgrade fills for every stored call."""

import aiosqlite

from app.repositories.audio_history_repository import AudioHistoryRepository


async def fill_source_columns(db: aiosqlite.Connection) -> None:
    """Read each hand-inserted call's source from its payload, as the upgrade and startup do."""
    repository = AudioHistoryRepository(db)
    while await repository.resolve_pending_sources(500):
        pass
