"""The one way detection history is deleted by age (#949).

Scheduled cleanup and "Purge Old Records" both come here. Each day is sealed from its rows, and
that is committed, before any of its captures is deleted. If sealing fails nothing is deleted:
the owner is told in Health, and the caller carries on with work that does not depend on it.
"""

from __future__ import annotations

from datetime import datetime

import aiosqlite
import structlog

from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.services.error_diagnostics import error_diagnostics_history
from app.utils.calendar_day import instance_timezone
from app.utils.diagnostic_redaction import safe_error_message

log = structlog.get_logger()

RETENTION_PAUSED = "retention_paused_daily_totals"
RETENTION_PAUSED_MESSAGE = (
    "Retention paused: the daily totals that keep the counts of old captures could not be saved, "
    "so no capture was deleted. Cleanup tries again on its next run."
)


class RetentionPaused(RuntimeError):
    """Sealing failed, so no capture was deleted."""


async def delete_aged_captures(
    db: aiosqlite.Connection, cutoff: datetime, *, now: datetime, species_floor: int, source: str
) -> int:
    """Seal, then delete captures older than ``cutoff``, keeping favourites and the species floor."""
    try:
        return await DailyTotalsRepository(db).seal_and_delete_older_than(
            cutoff, zone=instance_timezone(), now=now, preserve_favorites=True, species_floor=species_floor
        )
    except Exception as exc:
        error_diagnostics_history.record(
            source=source,
            component="daily_totals",
            reason_code=RETENTION_PAUSED,
            message=RETENTION_PAUSED_MESSAGE,
            severity="error",
            context={"error": safe_error_message(exc)},
        )
        log.error("retention_paused", source=source, error=safe_error_message(exc))
        raise RetentionPaused(RETENTION_PAUSED_MESSAGE) from exc
