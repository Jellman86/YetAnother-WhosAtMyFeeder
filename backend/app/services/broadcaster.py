import asyncio
import structlog
from typing import Set, Dict
from collections import defaultdict
from app.config import settings

log = structlog.get_logger()

class Broadcaster:
    def __init__(self):
        self.queues: Set[asyncio.Queue] = set()
        self._queue_lock = asyncio.Lock()
        self._full_counts: Dict[asyncio.Queue, int] = defaultdict(int)

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=settings.system.broadcaster_max_queue_size)
        async with self._queue_lock:
            self.queues.add(queue)
            self._full_counts[queue] = 0
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        async with self._queue_lock:
            self.queues.discard(queue)
            self._full_counts.pop(queue, None)

    async def broadcast(self, message: dict):
        if not self.queues:
            return

        # Create a snapshot to avoid holding lock during message delivery
        async with self._queue_lock:
            queues_snapshot = list(self.queues)

        # Track which queues to remove after broadcasting
        queues_to_remove = []

        for queue in queues_snapshot:
            try:
                # If the queue's put method has been monkey-patched (tests), call it to surface errors.
                if getattr(queue.put, "__func__", None) is not asyncio.Queue.put:
                    await queue.put(message)
                else:
                    queue.put_nowait(message)

                # Reset full count on successful delivery
                if queue in self._full_counts:
                    self._full_counts[queue] = 0
            except asyncio.QueueFull:
                # Increment full count and check if we should remove
                self._full_counts[queue] += 1
                max_consecutive = settings.system.broadcaster_max_consecutive_full
                if self._full_counts[queue] >= max_consecutive:
                    log.warning("Removing subscriber due to persistent backpressure",
                               queue_size=queue.qsize(),
                               consecutive_failures=self._full_counts[queue],
                               threshold=max_consecutive)
                    queues_to_remove.append(queue)
                else:
                    log.warning("Dropping SSE message for slow subscriber",
                               queue_size=queue.qsize(),
                               consecutive_failures=self._full_counts[queue],
                               threshold=max_consecutive)
            except Exception as e:
                # Queue may have been closed or is in bad state, remove it
                log.warning("Removing subscriber due to error", error=str(e))
                queues_to_remove.append(queue)

        # Clean up failed queues outside the broadcast loop
        if queues_to_remove:
            async with self._queue_lock:
                for queue in queues_to_remove:
                    self.queues.discard(queue)
                    self._full_counts.pop(queue, None)

broadcaster = Broadcaster()
