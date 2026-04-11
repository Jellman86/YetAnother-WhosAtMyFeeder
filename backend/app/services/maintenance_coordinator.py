import asyncio
from collections import Counter

from app.config import settings


class MaintenanceCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._holders: dict[str, str] = {}

    def _capacity(self) -> int:
        return max(1, int(getattr(settings.classification, "video_classification_max_concurrent", 1) or 1))

    async def try_acquire(self, holder_id: str, *, kind: str) -> bool:
        normalized_id = str(holder_id or "").strip()
        normalized_kind = str(kind or "maintenance").strip() or "maintenance"
        if not normalized_id:
            raise ValueError("holder_id is required")
        async with self._lock:
            if normalized_id in self._holders:
                return False
            if len(self._holders) >= self._capacity():
                return False
            self._holders[normalized_id] = normalized_kind
            return True

    async def release(self, holder_id: str) -> None:
        normalized_id = str(holder_id or "").strip()
        if not normalized_id:
            return
        async with self._lock:
            self._holders.pop(normalized_id, None)

    async def get_status(self) -> dict[str, object]:
        async with self._lock:
            counts = Counter(self._holders.values())
            active_total = len(self._holders)
        return self._build_status(active_total=active_total, counts=dict(counts))

    def get_status_nowait(self) -> dict[str, object]:
        counts = Counter(self._holders.values())
        return self._build_status(active_total=len(self._holders), counts=dict(counts))

    async def reset(self) -> None:
        async with self._lock:
            self._holders.clear()

    def _build_status(self, *, active_total: int, counts: dict[str, int]) -> dict[str, object]:
        capacity = self._capacity()
        return {
            "capacity": capacity,
            "active_total": active_total,
            "available": max(0, capacity - active_total),
            "active_by_kind": counts,
        }


maintenance_coordinator = MaintenanceCoordinator()
