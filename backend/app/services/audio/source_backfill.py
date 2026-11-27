"""Read the source of calls a release from before source tracking stored, after a rollback (#1111).

The upgrade reads every stored call's source once. A release from before it, run against the
upgraded database, stores calls without one, and running this release again does not repeat the
upgrade. Such calls are read here at startup, a small batch at a time, each batch its own short
write, so neither startup nor ingest waits on them. Shutdown stops the read before the database
closes: a batch cut short is rolled back with its connection, and the next start reads it.
"""

import asyncio

import structlog

from app.database import get_db
from app.repositories.audio_history_repository import AudioHistoryRepository

log = structlog.get_logger()

BATCH_SIZE = 500


async def resolve_pending_audio_sources(batch_size: int = BATCH_SIZE) -> int:
    """Read every call stored without its source; return how many were read."""
    resolved = 0
    while True:
        async with get_db() as db:
            count = await AudioHistoryRepository(db).resolve_pending_sources(batch_size)
        resolved += count
        if count < batch_size:
            return resolved
        # Give ingest and requests the database between batches.
        await asyncio.sleep(0)


async def stop_audio_source_backfill(task: asyncio.Task | None) -> None:
    """Stop the read and wait for it, so no batch outlives the database it writes to."""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def start_background_audio_source_backfill() -> None:
    """Run the read detached from startup; never fatal, always reported."""
    try:
        resolved = await resolve_pending_audio_sources()
    except Exception as error:
        log.warning("Audio source backfill failed", error=str(error))
        return
    if resolved:
        log.info("Audio source backfill finished", resolved=resolved)
