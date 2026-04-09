from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import structlog

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, TimezoneRepairRow
from app.services.frigate_client import frigate_client
from app.utils.api_datetime import serialize_api_datetime, utc_naive_from_timestamp

log = structlog.get_logger()

MAX_REPAIR_OFFSET_HOURS = 14
FRIGATE_LOOKUP_CONCURRENCY = 8
STATUS_SORT_ORDER = {
    "repair_candidate": 0,
    "missing_frigate_event": 1,
    "lookup_error": 2,
    "unsupported_delta": 3,
    "ok": 4,
}


@dataclass
class TimezoneRepairCandidate:
    detection_id: int
    frigate_event: str
    camera_name: str
    display_name: str
    status: str
    stored_detection_time: str
    frigate_start_time: str | None
    repaired_detection_time: str | None
    delta_hours: int | None
    error: str | None = None


class TimezoneRepairService:
    def __init__(self, frigate=None):
        self._frigate_client = frigate or frigate_client

    async def preview(self) -> dict:
        async with get_db() as db:
            repo = DetectionRepository(db)
            rows = await repo.list_timezone_repair_rows()
        return await self._build_preview(rows)

    async def apply(self, *, confirm: bool) -> dict:
        if not confirm:
            raise ValueError("Timezone repair apply requires explicit confirmation.")

        async with get_db() as db:
            repo = DetectionRepository(db)
            rows = await repo.list_timezone_repair_rows()

        preview = await self._build_preview(rows)

        async with get_db() as db:
            repo = DetectionRepository(db)
            repaired_count = 0
            for candidate in preview["candidates"]:
                if candidate["status"] != "repair_candidate" or not candidate["repaired_detection_time"]:
                    continue
                repaired_dt = self._parse_utc_naive(candidate["repaired_detection_time"])
                changed = await repo.update_detection_time_by_id(int(candidate["detection_id"]), repaired_dt)
                repaired_count += int(changed > 0)

        skipped_count = max(0, int(preview["summary"]["scanned_count"]) - repaired_count)
        result = {
            "status": "ok",
            "repaired_count": repaired_count,
            "skipped_count": skipped_count,
            "preview": preview,
        }
        log.info("Timezone repair apply completed", repaired_count=repaired_count, skipped_count=skipped_count)
        return result

    async def _build_preview(self, rows: list[TimezoneRepairRow]) -> dict:
        semaphore = asyncio.Semaphore(FRIGATE_LOOKUP_CONCURRENCY)

        async def classify(row: TimezoneRepairRow) -> TimezoneRepairCandidate:
            async with semaphore:
                event, error = await self._frigate_client.get_event_with_error(row.frigate_event, timeout=10.0)
            return self._classify_candidate(row, event, error)

        candidates = await asyncio.gather(*(classify(row) for row in rows))
        candidates.sort(key=lambda candidate: (STATUS_SORT_ORDER.get(candidate.status, 99), candidate.detection_id))
        summary = {
            "scanned_count": len(candidates),
            "repair_candidate_count": sum(1 for c in candidates if c.status == "repair_candidate"),
            "ok_count": sum(1 for c in candidates if c.status == "ok"),
            "missing_frigate_event_count": sum(1 for c in candidates if c.status == "missing_frigate_event"),
            "lookup_error_count": sum(1 for c in candidates if c.status == "lookup_error"),
            "unsupported_delta_count": sum(1 for c in candidates if c.status == "unsupported_delta"),
        }
        return {
            "summary": summary,
            "candidates": [asdict(candidate) for candidate in candidates],
        }

    def _classify_candidate(
        self,
        row: TimezoneRepairRow,
        event: dict | None,
        error: str | None,
    ) -> TimezoneRepairCandidate:
        stored_detection_time = row.detection_time.isoformat(sep=" ", timespec="seconds")

        if not event:
            status = "missing_frigate_event" if error == "event_not_found" else "lookup_error"
            return TimezoneRepairCandidate(
                detection_id=row.id,
                frigate_event=row.frigate_event,
                camera_name=row.camera_name,
                display_name=row.display_name,
                status=status,
                stored_detection_time=stored_detection_time,
                frigate_start_time=None,
                repaired_detection_time=None,
                delta_hours=None,
                error=error or "event_lookup_failed",
            )

        if event.get("start_time") is None:
            return TimezoneRepairCandidate(
                detection_id=row.id,
                frigate_event=row.frigate_event,
                camera_name=row.camera_name,
                display_name=row.display_name,
                status="lookup_error",
                stored_detection_time=stored_detection_time,
                frigate_start_time=None,
                repaired_detection_time=None,
                delta_hours=None,
                error=error or "missing_start_time",
            )

        frigate_detection_time = utc_naive_from_timestamp(float(event["start_time"]))
        delta = frigate_detection_time - self._as_utc_naive(row.detection_time)
        delta_seconds = int(delta.total_seconds())
        delta_hours: int | None = None
        status = "unsupported_delta"
        repaired_detection_time: str | None = None

        if delta_seconds == 0:
            status = "ok"
            delta_hours = 0
        elif self._is_supported_timezone_offset(delta_seconds):
            status = "repair_candidate"
            delta_hours = int(delta_seconds // 3600)
            repaired_detection_time = serialize_api_datetime(frigate_detection_time)

        return TimezoneRepairCandidate(
            detection_id=row.id,
            frigate_event=row.frigate_event,
            camera_name=row.camera_name,
            display_name=row.display_name,
            status=status,
            stored_detection_time=stored_detection_time,
            frigate_start_time=serialize_api_datetime(frigate_detection_time),
            repaired_detection_time=repaired_detection_time,
            delta_hours=delta_hours,
            error=error,
        )

    @staticmethod
    def _as_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _is_supported_timezone_offset(delta_seconds: int) -> bool:
        if delta_seconds == 0 or delta_seconds % 3600 != 0:
            return False
        delta_hours = abs(delta_seconds // 3600)
        return 1 <= delta_hours <= MAX_REPAIR_OFFSET_HOURS

    @staticmethod
    def _parse_utc_naive(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)


timezone_repair_service = TimezoneRepairService()
