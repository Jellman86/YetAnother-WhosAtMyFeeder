import asyncio
from collections import Counter
from typing import Any

from app.config import settings


class MaintenanceCoordinator:
    """Coordinates maintenance workflows with per-kind capacity.

    Regression fix for issue #33: a single global `max_concurrent=1` slot was
    shared across every maintenance kind (video_classification, backfill,
    weather_backfill, taxonomy_sync, timezone_repair, analyze_unknowns). That
    meant a single historical-video-classification holder could block all
    user-initiated maintenance for hours and produce a 962-deep pending
    queue. Capacity is now tracked per-kind so different kinds do not
    contend with each other.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # holder_id → kind
        self._holders: dict[str, str] = {}

    def _default_per_kind_capacity(self) -> int:
        """Per-kind default. Retains the `max_concurrent` setting semantics as
        a per-kind cap (historically it was a global cap, but same-kind
        throttling is what the setting was meant to express)."""
        return max(1, int(getattr(settings.maintenance, "max_concurrent", 1) or 1))

    def _per_kind_overrides(self) -> dict[str, int]:
        raw: Any = getattr(settings.maintenance, "per_kind_capacity", None)
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, int] = {}
        for k, v in raw.items():
            try:
                kind = str(k or "").strip()
                capacity = int(v)
            except (TypeError, ValueError):
                continue
            if not kind or capacity < 1:
                continue
            normalized[kind] = capacity
        return normalized

    def _capacity_for_kind(self, kind: str) -> int:
        overrides = self._per_kind_overrides()
        if kind in overrides:
            return overrides[kind]
        return self._default_per_kind_capacity()

    async def try_acquire(self, holder_id: str, *, kind: str) -> bool:
        normalized_id = str(holder_id or "").strip()
        normalized_kind = str(kind or "maintenance").strip() or "maintenance"
        if not normalized_id:
            raise ValueError("holder_id is required")
        async with self._lock:
            if normalized_id in self._holders:
                return False
            active_for_kind = sum(1 for k in self._holders.values() if k == normalized_kind)
            if active_for_kind >= self._capacity_for_kind(normalized_kind):
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
        default_capacity = self._default_per_kind_capacity()
        overrides = self._per_kind_overrides()
        # capacity_by_kind covers every kind we have either an active holder
        # for or an explicit override for — consumers of the diagnostics
        # bundle then see which kinds are saturated at a glance.
        kinds = set(counts.keys()) | set(overrides.keys())
        capacity_by_kind = {kind: self._capacity_for_kind(kind) for kind in kinds}
        # Overall `capacity` field is retained for backwards-compat with
        # existing dashboards; it reports the per-kind default.
        return {
            "capacity": default_capacity,
            "capacity_by_kind": capacity_by_kind,
            "active_total": active_total,
            "available": max(0, default_capacity - active_total),
            "active_by_kind": counts,
        }


maintenance_coordinator = MaintenanceCoordinator()
