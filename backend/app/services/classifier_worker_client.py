import asyncio
import os
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
        stderr_tail_max_bytes: int = 8192,
    ) -> None:
        self.worker_name = str(worker_name)
        self.worker_generation = int(worker_generation)
        self.heartbeat_timeout_seconds = max(0.1, float(heartbeat_timeout_seconds))
        self._process_factory = process_factory or self._spawn_process
        self._stderr_tail_max_bytes = max(1, int(stderr_tail_max_bytes))
        self._process: Any = None
        self._ready = asyncio.Event()
        self._closed = asyncio.Event()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._last_heartbeat_monotonic: float | None = None
        self._last_stderr_monotonic: float | None = None
        self._busy = False
        self._current_request_id: str | None = None
        self._exit_code: int | None = None
        self._stderr_tail = bytearray()
        self._stderr_truncated_bytes = 0

    async def start(self) -> None:
        if self._process is not None:
            return
        self._process = await self._process_factory(
            worker_name=self.worker_name,
            worker_generation=self.worker_generation,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        self._wait_task = asyncio.create_task(self._wait_loop())

    async def wait_until_ready(self, timeout_seconds: float = 5.0) -> None:
        timeout = max(0.01, float(timeout_seconds))
        ready_task = asyncio.create_task(self._ready.wait())
        closed_task = asyncio.create_task(self._closed.wait())
        try:
            done, pending = await asyncio.wait(
                {ready_task, closed_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

            if ready_task in done and self._ready.is_set():
                return
            if closed_task in done and self._closed.is_set():
                raise RuntimeError(self._build_startup_failure_message())
            raise TimeoutError()
        except TimeoutError:
            if self._closed.is_set():
                raise RuntimeError(self._build_startup_failure_message()) from None
            raise
        finally:
            for task in (ready_task, closed_task):
                if not task.done():
                    task.cancel()

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
            "last_stderr_monotonic": self._last_stderr_monotonic,
            "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
            "exit_code": self._exit_code,
            "recent_stderr_excerpt": self._stderr_excerpt(),
            "stderr_truncated_bytes": self._stderr_truncated_bytes,
        }

    async def _reader_loop(self) -> None:
        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    return
                try:
                    message = decode_protocol_message(raw)
                except ValueError:
                    self._append_stdout_noise(raw)
                    continue
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
            self._mark_closed()

    async def _stderr_loop(self) -> None:
        try:
            while True:
                raw = await self._process.stderr.read(4096)
                if not raw:
                    return
                self._append_stderr(raw)
        finally:
            self._mark_closed()

    async def _wait_loop(self) -> None:
        try:
            self._exit_code = await self._process.wait()
        finally:
            self._mark_closed()

    def _append_stderr(self, data: bytes) -> None:
        if not data:
            return
        self._last_stderr_monotonic = time.monotonic()
        self._stderr_tail.extend(data)
        
        # Forward worker stderr to main process log so it's visible in docker logs
        try:
            text = data.decode("utf-8", errors="replace").strip()
            if text:
                from structlog import get_logger
                log = get_logger()
                log.info(f"Worker {self.worker_name} stderr", text=text)
        except Exception:
            pass

        overflow = len(self._stderr_tail) - self._stderr_tail_max_bytes
        if overflow > 0:
            del self._stderr_tail[:overflow]
            self._stderr_truncated_bytes += overflow

    def _append_stdout_noise(self, data: bytes) -> None:
        if not data:
            return
        stripped = data.rstrip(b"\r\n")
        if not stripped:
            return
        self._append_stderr(b"[stdout-noise] " + stripped + b"\n")

    def _stderr_excerpt(self) -> str:
        if not self._stderr_tail:
            return ""
        return bytes(self._stderr_tail).decode("utf-8", errors="replace")

    def _build_startup_failure_message(self) -> str:
        message = f"classifier worker exited before ready worker={self.worker_name} generation={self.worker_generation}"
        if self._exit_code is not None:
            message += f" exit_code={self._exit_code}"
        stderr_excerpt = self._stderr_excerpt().strip()
        if stderr_excerpt:
            message += f" stderr={stderr_excerpt}"
        return message

    def _mark_closed(self) -> None:
        if self._closed.is_set():
            return
        try:
            self._closed.set()
        except RuntimeError:
            pass

    async def _spawn_process(self, *, worker_name: str, worker_generation: int) -> Any:
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        # Use a large limit (512KB) for the StreamReader to prevent LimitOverrunError
        # if a worker dumps a massive JSON payload or large GPU error stack trace.
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.services.classifier_worker_process",
            worker_name,
            str(worker_generation),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=backend_root,
            limit=512 * 1024,
        )
