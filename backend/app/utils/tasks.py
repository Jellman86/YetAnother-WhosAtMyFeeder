import asyncio
from typing import Any, Coroutine

import structlog

log = structlog.get_logger()


def create_background_task(coro: Coroutine[Any, Any, Any], name: str | None = None) -> asyncio.Task:
    """Create a task that logs unhandled exceptions instead of failing silently."""
    task = asyncio.create_task(coro, name=name)

    def _handle_task_result(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            log.debug("Background task cancelled", task=task.get_name())
        except Exception as e:  # noqa: BLE001 - log unexpected failures
            log.error("Background task failed", task=task.get_name(), error=str(e), exc_info=True)

    task.add_done_callback(_handle_task_result)
    return task
