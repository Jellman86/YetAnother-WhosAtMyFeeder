"""Periodically reconcile `frigate_status` with what Frigate actually holds.

`frigate_missing_behavior` is a real setting, but nothing ran it on the common
path: it was reached only from the owner-triggered maintenance endpoints, the
automatic video classifier, and a scheduled scan that was off by default and,
when on, read every row in the table and asked Frigate about each one on every
cycle. So a database could disagree with reality indefinitely — on the reference
deployment every detection said `present`, including 44 whose events Frigate
returned 404 for, and 89% had not been checked in over a week (#254).

This scan is the missing piece, and it is bounded on purpose:

- it takes the least recently confirmed rows first, capped per run, so a large
  history drains over several runs instead of flooding Frigate in one;
- it never asks about a row already known missing, because Frigate does not
  un-retire an event and that answer cannot change. The consequence is that
  `missing` is terminal for this scan: a detection marked missing in error stays
  marked, and the manual full scan in Settings is the way back;
- it does nothing at all when Frigate is unreachable, because "we could not ask"
  must never be recorded as "upstream no longer has it" — on `delete` that
  mistake destroys history during an outage.

The read path deliberately does not do this work: a GET must not mutate history.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal, Optional

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.services.frigate_client import frigate_client
from app.services.frigate_missing_policy import apply_missing_policy
from app.services.maintenance_coordinator import maintenance_coordinator
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()

MEDIA_INTEGRITY_SCAN_KIND = "media_integrity_scan"
MEDIA_INTEGRITY_SCAN_HOLDER = "media_integrity_scan"
# Matches the owner-triggered purge endpoints, so a scheduled scan is no harder
# on Frigate than the button an owner can already press.
MEDIA_INTEGRITY_CHECK_CONCURRENCY = 8
# Writes are applied in chunks, releasing the connection between them. The batch
# is configurable up to 20,000, and holding one of five pooled connections for
# that whole write is the contention the pool work exists to remove.
MEDIA_INTEGRITY_WRITE_CHUNK = 200

ScanStatus = Literal["completed", "disabled", "frigate_unreachable", "busy", "nothing_to_check"]


def evaluate_media_presence(
    event_data: Optional[dict],
    error: Optional[str],
    *,
    media: str,
    clips_enabled: bool,
) -> tuple[bool, Optional[str]]:
    """Decide whether a detection's upstream media is missing, and why.

    `has_snapshot` defaults to True because Frigate omits it on some event
    shapes, and absence of the field is not evidence of absence of the snapshot.
    A clip is only expected when Frigate clips are enabled at all.
    """
    if not event_data:
        return True, error or "event_not_found"

    reasons: list[str] = []
    if media in ("any", "clip") and clips_enabled and not bool(event_data.get("has_clip", False)):
        reasons.append("clip_unavailable")
    if media in ("any", "snapshot") and not bool(event_data.get("has_snapshot", True)):
        reasons.append("snapshot_unavailable")

    if reasons:
        return True, ",".join(reasons)
    return False, None


@dataclass
class MediaIntegrityScanResult:
    """What one scan did, for logs, Health and the Jobs surface."""

    status: ScanStatus
    checked: int = 0
    missing: int = 0
    deleted_count: int = 0
    marked_missing_count: int = 0
    kept_count: int = 0
    errors: int = 0
    pending: int = 0
    message: str = ""
    finished_at: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked": self.checked,
            "missing": self.missing,
            "deleted_count": self.deleted_count,
            "marked_missing_count": self.marked_missing_count,
            "kept_count": self.kept_count,
            "errors": self.errors,
            "pending": self.pending,
            "message": self.message,
            "finished_at": self.finished_at,
        }


@dataclass
class _ScanState:
    last: Optional[MediaIntegrityScanResult] = None
    running: bool = False
    history: list = field(default_factory=list)


_state = _ScanState()


def get_media_integrity_scan_status() -> dict[str, Any]:
    """Health surface: whether the scan is on, running, and how far behind."""
    return {
        "enabled": bool(settings.maintenance.media_integrity_scan_enabled),
        "media": settings.maintenance.media_integrity_scan_media,
        "interval_hours": settings.maintenance.media_integrity_scan_interval_hours,
        "batch_size": settings.maintenance.media_integrity_scan_batch_size,
        "running": _state.running,
        "last_run": _state.last.as_dict() if _state.last else None,
    }


def _record(result: MediaIntegrityScanResult) -> MediaIntegrityScanResult:
    result.finished_at = utc_naive_now().isoformat(sep=" ")
    _state.last = result
    return result


async def _count_pending(checked_before) -> int:
    try:
        async with get_db() as db:
            return await DetectionRepository(db).count_stale_frigate_check_candidates(checked_before=checked_before)
    except Exception as exc:
        log.warning("Could not count pending media integrity checks", error=str(exc))
        return 0


async def run_media_integrity_scan() -> MediaIntegrityScanResult:
    """Re-check a bounded batch of detections against Frigate."""
    maintenance = settings.maintenance
    if not maintenance.media_integrity_scan_enabled:
        return _record(MediaIntegrityScanResult(status="disabled", message="Media integrity scan is turned off."))

    acquired = await maintenance_coordinator.try_acquire(MEDIA_INTEGRITY_SCAN_HOLDER, kind=MEDIA_INTEGRITY_SCAN_KIND)
    if not acquired:
        return _record(MediaIntegrityScanResult(status="busy", message="A media integrity scan is already running."))

    _state.running = True
    try:
        return await _run_scan_locked(maintenance)
    finally:
        _state.running = False
        await maintenance_coordinator.release(MEDIA_INTEGRITY_SCAN_HOLDER)


async def _run_scan_locked(maintenance) -> MediaIntegrityScanResult:
    # Only re-confirm rows whose last answer has had time to go stale, so a run
    # never re-asks about work the previous run just did.
    checked_before = utc_naive_now() - timedelta(hours=max(1, int(maintenance.media_integrity_scan_interval_hours)))

    async with get_db() as db:
        candidates = await DetectionRepository(db).get_stale_frigate_check_candidates(
            limit=int(maintenance.media_integrity_scan_batch_size),
            checked_before=checked_before,
        )

    if not candidates:
        return _record(
            MediaIntegrityScanResult(status="nothing_to_check", message="Every detection has been confirmed recently.")
        )

    # Ask Frigate whether it is there at all before concluding anything about
    # individual events. Without this, an outage marks the batch missing — and
    # on `delete`, deletes it.
    try:
        version = await frigate_client.get_version()
    except Exception as exc:
        log.warning("Media integrity scan skipped; Frigate unreachable", error=str(exc))
        version = None
    if not version:
        return _record(
            MediaIntegrityScanResult(
                status="frigate_unreachable",
                pending=await _count_pending(checked_before),
                message="Frigate is not reachable. Nothing was changed.",
            )
        )

    clips_enabled = bool(settings.frigate.clips_enabled)
    media = str(maintenance.media_integrity_scan_media or "any")
    semaphore = asyncio.Semaphore(MEDIA_INTEGRITY_CHECK_CONCURRENCY)

    async def check(event_id: str) -> tuple[str, bool, Optional[str], bool]:
        """Returns (event_id, missing, reason, errored)."""
        async with semaphore:
            try:
                event_data, error = await frigate_client.get_event_with_error(event_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # One unreadable event must not condemn it or stop the batch.
                log.debug("Media integrity check failed", event_id=event_id, error=str(exc))
                return event_id, False, None, True
            missing, reason = evaluate_media_presence(event_data, error, media=media, clips_enabled=clips_enabled)
            return event_id, missing, reason, False

    results = await asyncio.gather(*(check(row["frigate_event"]) for row in candidates))

    result = MediaIntegrityScanResult(status="completed", checked=len(candidates))
    checked_at = utc_naive_now()

    chunk_size = max(1, int(MEDIA_INTEGRITY_WRITE_CHUNK))
    for offset in range(0, len(results), chunk_size):
        async with get_db() as db:
            repo = DetectionRepository(db)
            for event_id, missing, reason, errored in results[offset : offset + chunk_size]:
                if errored:
                    result.errors += 1
                    continue
                if missing:
                    result.missing += 1
                    counts = await apply_missing_policy(
                        repo=repo,
                        frigate_event=event_id,
                        error=reason or "media_unavailable",
                        source="media_integrity_scan",
                        media_kind=media,
                        checked_at=checked_at,
                    )
                    result.deleted_count += counts["deleted_count"]
                    result.marked_missing_count += counts["marked_missing_count"]
                    result.kept_count += counts["kept_count"]
                    continue
                # Present. Record the check so a confirmed detection stops being
                # re-asked about. Nothing to clear: a row already `missing` is
                # never selected, so anything reaching here was already present.
                await repo.record_frigate_check(event_id, checked_at=checked_at)

    result.pending = await _count_pending(checked_before)
    log.info("Media integrity scan completed", **result.as_dict())
    return _record(result)
