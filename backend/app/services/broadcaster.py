import asyncio
import structlog
from typing import Set

log = structlog.get_logger()
MAX_QUEUE_SIZE = 100

class Broadcaster:
    def __init__(self):
        self.queues: Set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.queues.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        # Use discard to avoid KeyError if queue already removed
        self.queues.discard(queue)

    async def broadcast(self, message: dict):
        if not self.queues:
            return

        # Create a copy to avoid issues if queues change during iteration
        queues_snapshot = list(self.queues)
        for queue in queues_snapshot:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Drop message for slow consumers to prevent unbounded growth.
                log.warning("Dropping SSE message for slow subscriber", queue_size=queue.qsize())
            except Exception:
                # Queue may have been closed, remove it
                self.queues.discard(queue)

broadcaster = Broadcaster()
