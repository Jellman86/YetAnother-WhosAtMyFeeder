import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .classifier_worker_protocol import decode_protocol_message, encode_protocol_message


ProcessFactory = Callable[..., Awaitable[Any]]


class ClassifierWorkerClient:
    def __init__(
        self,
        *,
        worker_name: str,
        worker_generation: int,
        heartbeat_timeout_seconds: float,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        self.worker_name = str(worker_name)
        self.worker_generation = int(worker_generation)
        self.heartbeat_timeout_seconds = max(0.1, float(heartbeat_timeout_seconds))
        self._process_factory = process_factory or self._spawn_process
        self._process: Any = None
        self._ready = asyncio.Event()
        self._closed = asyncio.Event()
        self._reader_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._last_heartbeat_monotonic: float | None = None
        self._busy = False
        self._current_request_id: str | None = None
        self._exit_code: int | None = None

    async def start(self) -> None:
        if self._process is not None:
            return
        self._process = await self._process_factory(
            worker_name=self.worker_name,
            worker_generation=self.worker_generation,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._wait_task = asyncio.create_task(self._wait_loop())

    async def wait_until_ready(self, timeout_seconds: float = 1.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=max(0.01, float(timeout_seconds)))

    async def send(self, message: dict[str, Any]) -> None:
        if self._process is None or getattr(self._process, "stdin", None) is None:
            raise RuntimeError("worker process is not started")
        self._process.stdin.write(encode_protocol_message(message))
        await self._process.stdin.drain()

    async def next_event(self) -> dict[str, Any]:
        return await self._event_queue.get()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def terminate(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        await self.wait_closed()

    async def kill(self) -> None:
        if self._process is None:
            return
        self._process.kill()
        await self.wait_closed()

    def get_status(self) -> dict[str, Any]:
        return {
            "worker_name": self.worker_name,
            "worker_generation": self.worker_generation,
            "ready": self._ready.is_set(),
            "busy": self._busy,
            "current_request_id": self._current_request_id,
            "last_heartbeat_monotonic": self._last_heartbeat_monotonic,
            "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
            "exit_code": self._exit_code,
        }

    async def _reader_loop(self) -> None:
        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    return
                message = decode_protocol_message(raw)
                if message.get("worker_generation") not in {None, self.worker_generation}:
                    continue
                message_type = message["type"]
                if message_type == "ready":
                    self._ready.set()
                elif message_type == "heartbeat":
                    self._last_heartbeat_monotonic = time.monotonic()
                    self._busy = bool(message.get("busy"))
                    self._current_request_id = message.get("request_id")
                else:
                    await self._event_queue.put(message)
        finally:
            self._closed.set()

    async def _wait_loop(self) -> None:
        try:
            self._exit_code = await self._process.wait()
        finally:
            self._closed.set()

    async def _spawn_process(self, *, worker_name: str, worker_generation: int) -> Any:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.services.classifier_worker_process",
            worker_name,
            str(worker_generation),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
