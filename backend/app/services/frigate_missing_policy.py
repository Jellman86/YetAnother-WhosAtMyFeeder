from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from app.config import settings
from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.repositories.detection_repository import DetectionRepository
from app.services.broadcaster import broadcaster
from app.services.error_diagnostics import error_diagnostics_history
from app.services.media_cache import media_cache
from app.utils.api_datetime import serialize_api_datetime, utc_naive_now
from app.utils.calendar_day import instance_timezone

log = structlog.get_logger()


async def apply_missing_policy(
    *,
    repo: DetectionRepository,
    frigate_event: str,
    error: str,
    source: str,
    media_kind: str,
    checked_at: datetime | None = None,
    extra_context: dict[str, Any] | None = None,
    delete_cached_media: bool = True,
    broadcast_delete: bool = False,
) -> dict[str, int]:
    checked = checked_at or utc_naive_now()
    behavior = settings.maintenance.frigate_missing_behavior
    context = {
        "event_id": frigate_event,
        "error": error,
        "behavior": behavior,
        "media_kind": media_kind,
        "source": source,
        **(extra_context or {}),
    }
    if behavior == "delete" and await media_cache.get_snapshot_path(frigate_event) is not None:
        # YA-WAMF holds its own copy of the record's photo, so the record is not lost with
        # Frigate's media; deleting it would destroy the only photo left.
        behavior = context["behavior"] = "mark_missing"
        context["own_photo_kept"] = True
    if behavior == "delete":
        # Check the owner's keep decision in the DELETE itself. A stale read followed by
        # file cleanup would destroy a favourite accepted while that cleanup was awaiting.
        # The capture's count is kept as its own record, in the same transaction as the delete,
        # so its day stays live and correctable (#949).
        deleted = await DailyTotalsRepository(repo.db).delete_lost_capture(
            frigate_event, zone=instance_timezone(), now=checked, preserve_favorites=True
        )
        if not deleted:
            detection = await repo.get_by_frigate_event(frigate_event)
            if detection is None or not detection.is_favorite:
                return {"deleted_count": 0, "marked_missing_count": 0, "kept_count": 0}
            behavior = context["behavior"] = "mark_missing"
            context["favorite_kept"] = True

    if behavior == "delete":
        if delete_cached_media:
            await media_cache.delete_cached_media(frigate_event)
        if deleted and broadcast_delete:
            await broadcaster.broadcast(
                {
                    "type": "detection_deleted",
                    "data": {
                        "frigate_event": frigate_event,
                        "timestamp": serialize_api_datetime(checked),
                    },
                }
            )
        # Applying the configured missing-media policy when Frigate ages out old media
        # is routine maintenance, not a system fault that should degrade Health.
        error_diagnostics_history.record(
            source=source,
            component="frigate_missing_policy",
            reason_code="frigate_missing_deleted",
            message="Deleted local detection because Frigate no longer has the event or retained media.",
            severity="info",
            stage=media_kind,
            event_id=frigate_event,
            context=context,
        )
        log.info("Applied Frigate missing policy", action="delete", **context)
        return {"deleted_count": 1, "marked_missing_count": 0, "kept_count": 0}

    if behavior == "mark_missing":
        marked = await repo.mark_frigate_missing(
            frigate_event,
            error=error,
            checked_at=checked,
        )
        error_diagnostics_history.record(
            source=source,
            component="frigate_missing_policy",
            reason_code="frigate_missing_marked",
            message="Marked detection as missing upstream while preserving local data.",
            severity="info",
            stage=media_kind,
            event_id=frigate_event,
            context=context,
        )
        log.info("Applied Frigate missing policy", action="mark_missing", **context)
        return {"deleted_count": 0, "marked_missing_count": 1 if marked else 0, "kept_count": 0}

    error_diagnostics_history.record(
        source=source,
        component="frigate_missing_policy",
        reason_code="frigate_missing_kept",
        message="Detected missing Frigate event/media but left local data unchanged.",
        severity="info",
        stage=media_kind,
        event_id=frigate_event,
        context=context,
    )
    log.info("Applied Frigate missing policy", action="keep", **context)
    return {"deleted_count": 0, "marked_missing_count": 0, "kept_count": 1}


async def clear_missing_state_if_present(
    *,
    repo: DetectionRepository,
    frigate_event: str,
    source: str,
    media_kind: str,
    checked_at: datetime | None = None,
) -> bool:
    checked = checked_at or utc_naive_now()
    restored = await repo.mark_frigate_present(frigate_event, checked_at=checked)
    if restored:
        log.info(
            "Cleared stale Frigate missing state",
            event_id=frigate_event,
            source=source,
            media_kind=media_kind,
        )
    return restored
