"""When each Maintenance job last ran and what it found.

The outcome is kept in the durable maintenance job history beside the backfill jobs, so the
Maintenance tab can say "last run" after a restart instead of only for the current session.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import structlog

from app.database import get_db
from app.repositories.maintenance_job_repository import MaintenanceJobRepository

log = structlog.get_logger()

MaintenanceRunKind = Literal["taxonomy", "timezone_scan", "timezone_repair", "analyze_unknowns"]
MAINTENANCE_RUN_KINDS: tuple[MaintenanceRunKind, ...] = (
    "taxonomy",
    "timezone_scan",
    "timezone_repair",
    "analyze_unknowns",
)
# The backfill jobs share the history table and keep their own payload shape.
BACKFILL_JOB_KINDS: tuple[str, ...] = ("detections", "weather")


async def record_maintenance_run(
    kind: MaintenanceRunKind,
    *,
    status: Literal["completed", "failed"],
    checked: int | None = None,
    changed: int | None = None,
    unchecked: int | None = None,
) -> None:
    """Keep the outcome of one run. A failure to record never fails the job it describes."""
    payload = {
        "id": f"{kind}-{uuid4()}",
        "kind": kind,
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "checked": checked,
        "changed": changed,
        # Records the run looked at but could not check, e.g. Frigate did not answer. Without it a
        # scan whose every lookup failed would read as an all-clear.
        "unchecked": unchecked,
    }
    try:
        async with get_db() as db:
            await MaintenanceJobRepository(db).save(payload)
    except Exception as exc:  # noqa: BLE001 - the job's own result matters more than its record
        log.warning("maintenance_run_record_failed", kind=kind, error=str(exc))


async def latest_maintenance_runs() -> list[dict]:
    """The newest recorded run of each Maintenance job and each backfill kind, newest first."""
    async with get_db() as db:
        repo = MaintenanceJobRepository(db)
        runs: list[dict] = []
        for kind in (*MAINTENANCE_RUN_KINDS, *BACKFILL_JOB_KINDS):
            payload = await repo.latest(kind)
            if payload is None:
                continue
            runs.append(_summary(payload))
    return runs


def _summary(payload: dict) -> dict:
    if payload["kind"] in BACKFILL_JOB_KINDS:
        changed = int(payload.get("new_detections") or 0) + int(payload.get("updated") or 0)
        return {
            "kind": payload["kind"],
            "status": payload.get("status") or "failed",
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
            "checked": payload.get("processed"),
            "changed": changed,
            "unchecked": payload.get("errors"),
        }
    return {
        key: payload.get(key)
        for key in ("kind", "status", "started_at", "finished_at", "checked", "changed", "unchecked")
    }
