import asyncio
import time
from typing import Optional


class VideoClassificationWaiter:
    """In-process coordination for video classification completion events."""

    _FINAL_STATUSES = {"completed", "failed"}

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 5000):
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._states: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    def _snapshot(self, event_id: str) -> Optional[dict]:
        state = self._states.get(event_id)
        if not state:
            return None
        return dict(state)

    def _cleanup_locked(self, now: float) -> None:
        stale = [
            event_id
            for event_id, state in self._states.items()
            if now - float(state.get("updated_at", now)) > self._ttl_seconds
        ]
        for event_id in stale:
            self._states.pop(event_id, None)
            self._events.pop(event_id, None)

        if len(self._states) <= self._max_entries:
            return

        ordered = sorted(self._states.items(), key=lambda item: float(item[1].get("updated_at", 0)))
        overflow = len(self._states) - self._max_entries
        for event_id, _ in ordered[:overflow]:
            self._states.pop(event_id, None)
            self._events.pop(event_id, None)

    async def publish(
        self,
        event_id: str,
        status: str,
        *,
        label: Optional[str] = None,
        score: Optional[float] = None,
        error: Optional[str] = None
    ) -> None:
        now = time.time()
        async with self._lock:
            self._states[event_id] = {
                "status": status,
                "label": label,
                "score": score,
                "error": error,
                "updated_at": now,
            }

            current = self._events.get(event_id)
            if status in self._FINAL_STATUSES:
                if current is None:
                    current = asyncio.Event()
                    self._events[event_id] = current
                current.set()
            else:
                if current is None or current.is_set():
                    self._events[event_id] = asyncio.Event()

            self._cleanup_locked(now)

    async def get_state(self, event_id: str) -> Optional[dict]:
        async with self._lock:
            return self._snapshot(event_id)

    async def wait_for_final_status(self, event_id: str, timeout: float) -> Optional[dict]:
        if timeout <= 0:
            return await self.get_state(event_id)

        async with self._lock:
            state = self._snapshot(event_id)
            if state and state.get("status") in self._FINAL_STATUSES:
                return state
            event = self._events.get(event_id)
            if event is None:
                event = asyncio.Event()
                self._events[event_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return await self.get_state(event_id)

        return await self.get_state(event_id)


video_classification_waiter = VideoClassificationWaiter()
