"""Bounded, process-local storage measurements that survive short HTTP requests."""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import structlog

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Measurement:
    id: str
    task: asyncio.Task[dict]
    started_at: datetime
    completed_at: datetime | None = None

    def completed(self, task: asyncio.Task[dict]) -> None:
        self.completed_at = _now()
        if not task.cancelled():
            error = task.exception()  # Retrieve failures even when the requesting tab has gone away.
            if error is not None:
                log.warning("storage_measurement_failed", measurement_id=self.id, error_type=type(error).__name__)

    def snapshot(self) -> dict:
        result = {
            "id": self.id,
            "status": "running",
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stats": None,
            "error": None,
        }
        if self.task.done():
            result["completed_at"] = self.completed_at or _now()
            if self.task.cancelled() or self.task.exception() is not None:
                result.update(status="failed", error="Storage measurement failed. Retry the measurement.")
            else:
                result.update(status="completed", stats=self.task.result())
        return result


class CacheStatsMeasurements:
    def __init__(self, collect: Callable[[], Awaitable[dict]], *, max_retained: int = 16) -> None:
        if max_retained < 2:
            raise ValueError("At least two measurements must be retained")
        self._collect = collect
        self._max_retained = max_retained
        self._loop: asyncio.AbstractEventLoop | None = None
        self._measurements: OrderedDict[str, _Measurement] = OrderedDict()
        self._active: _Measurement | None = None

    def get(self, measurement_id: str | None = None) -> dict:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._measurements.clear()
            self._active = None
        if measurement_id is not None:
            return self._measurements[measurement_id].snapshot()
        if self._active is not None and not self._active.task.done():
            return self._active.snapshot()
        while len(self._measurements) >= self._max_retained:
            self._measurements.popitem(last=False)
        measurement = _Measurement(str(uuid4()), loop.create_task(self._collect()), _now())
        measurement.task.add_done_callback(measurement.completed)
        self._measurements[measurement.id] = measurement
        self._active = measurement
        return measurement.snapshot()
