"""Warm Garden inference children, kept only while birds leave the hardware free.

A worker loads one model for one exact binding (model path, model checksum, variant and
provider) and answers one newline-framed request at a time. Anything other than a clean
result (bird pre-emption, a deadline, cancellation, a crash, an error or malformed
output) stops it, so the next request starts a fresh process. An idle worker is
stopped after ``WARM_IDLE_SECONDS`` or as soon as bird work is pending, and every worker
is replaced after ``WARM_MAX_REQUESTS`` so slow growth inside a native runtime is bounded.

The worker owns its child until the child is reaped: retirement runs to completion even
when its caller is cancelled, and anyone else who needs the child gone joins it.
"""

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from contextlib import suppress
import json
import os
import re
import signal
import time
from typing import Any

import structlog

from app.utils.child_signals import kill_child, terminate_child
from app.utils.python_subprocess import python_subprocess_launch

log = structlog.get_logger()

RESULT_LIMIT_BYTES = 64 * 1024
WARM_IDLE_SECONDS = 60.0
WARM_MAX_REQUESTS = 500


class GardenBusy(RuntimeError):
    pass


def exit_signal_name(exit_code: int | None) -> str | None:
    """The signal that ended a child, from asyncio's negative return code."""
    if exit_code is None or exit_code >= 0:
        return None
    try:
        return signal.Signals(-exit_code).name
    except ValueError:
        return f"signal {-exit_code}"


def worker_error_type(output: bytes) -> str | None:
    """The exception type a Garden worker named before exiting non-zero, if any."""
    for line in output.splitlines():
        if line.startswith(b"WORKER_ERROR:"):
            name = line[len(b"WORKER_ERROR:") :].decode("ascii", "replace").strip()
            return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) else None
    return None


class GardenNativeWorkerFailed(ValueError):
    """A Garden worker exited non-zero.

    A signal (negative exit code) is a native fault or a kill; a positive code is a
    Python exception inside the worker, named by ``error_type`` when it said so.
    """

    def __init__(self, exit_code: int, error_type: str | None = None) -> None:
        self.exit_code = exit_code
        self.signal_name = exit_signal_name(exit_code)
        self.error_type = error_type
        cause = f"was stopped by {self.signal_name}" if self.signal_name else f"exited with status {exit_code}"
        super().__init__(f"Garden worker {cause}" + (f" after {error_type}" if error_type else ""))

    def log_fields(self) -> dict[str, int | str | None]:
        return {"exit_code": self.exit_code, "signal": self.signal_name, "worker_error": self.error_type}


def worker_failure_fields(error: BaseException) -> dict[str, int | str | None]:
    """Exit details for a failure log; empty for anything but a failed worker."""
    return error.log_fields() if isinstance(error, GardenNativeWorkerFailed) else {}


class GardenCleanupFailed(RuntimeError):
    pass


async def stop_worker(process: Any) -> None:
    with suppress(ProcessLookupError):
        terminate_child(process)
    try:
        await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        with suppress(ProcessLookupError):
            kill_child(process)
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError as error:
            raise GardenCleanupFailed("Garden worker did not stop") from error


async def finish_despite_cancellation(cleanup: Awaitable[None]) -> None:
    """Run cleanup to the end even if the caller is cancelled meanwhile, then honour that cancellation."""
    task = asyncio.ensure_future(cleanup)
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True
    task.result()
    if interrupted:
        raise asyncio.CancelledError


class GardenWarmWorker:
    """At most one warm child for one module; a different binding replaces it."""

    def __init__(
        self,
        module: str,
        result_prefix: bytes,
        *,
        release: Callable[[], bool],
        on_stuck: Callable[[], None],
        idle_seconds: float = WARM_IDLE_SECONDS,
        poll_seconds: float = 0.5,
        max_requests: int = WARM_MAX_REQUESTS,
        launch_args: tuple[str, ...] | None = None,
    ) -> None:
        self.module = module
        self.result_prefix = result_prefix
        self.release = release
        self.on_stuck = on_stuck
        self.idle_seconds = idle_seconds
        self.poll_seconds = poll_seconds
        self.max_requests = max_requests
        self.launch_args = launch_args or ("-m", module)
        self.stuck = False
        self._process: Any = None
        self._key: Hashable | None = None
        self._served = 0
        self._idle_since = 0.0
        self._lock = asyncio.Lock()
        self._monitor: asyncio.Task | None = None
        self._retiring: asyncio.Task | None = None

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    @property
    def key(self) -> Hashable | None:
        """The binding of the child currently held, if any."""
        return self._key

    async def request(
        self,
        key: Hashable,
        payload: dict[str, Any],
        blocked: Callable[[], bool],
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.1,
    ) -> dict[str, Any]:
        """The worker's result object for this request."""
        message = json.dumps(payload).encode() + b"\n"
        async with self._lock:
            if self.stuck:
                raise GardenCleanupFailed("Garden worker did not stop")
            if self._process is not None and (self._key != key or self._process.returncode is not None):
                await self._retire("binding_changed" if self._key != key else "exited")
            if self._process is None:
                await self._spawn(key)
            kept = False
            try:
                result = await self._exchange(message, blocked, timeout_seconds, poll_seconds)
                self._served += 1
                kept = self._served < self.max_requests
                return result
            finally:
                if kept:
                    self._idle_since = time.monotonic()
                    self._watch_idle()
                else:
                    # Request cancellation cannot leave a native call using the device.
                    await self._retire("request_ended" if self._served < self.max_requests else "recycled")

    async def retire(self, reason: str) -> None:
        """Stop the child now and wait until it has exited; the next request starts a fresh one."""
        async with self._lock:
            await self._retire(reason)

    async def stop(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()
            # A release the monitor already started finishes before the monitor ends.
            with suppress(asyncio.CancelledError):
                await self._monitor
            self._monitor = None
        await self.retire("shutdown")

    async def _spawn(self, key: Hashable) -> None:
        environment = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        executable, environment = python_subprocess_launch(environment)
        self._process = await asyncio.create_subprocess_exec(
            executable,
            *self.launch_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
            limit=RESULT_LIMIT_BYTES,
        )
        self._key = key
        self._served = 0
        log.info("garden_worker_started", module=self.module, pid=self._process.pid)

    async def _exchange(
        self, message: bytes, blocked: Callable[[], bool], timeout_seconds: float, poll_seconds: float
    ) -> dict[str, Any]:
        process = self._process

        async def send_and_read() -> bytes:
            try:
                process.stdin.write(message)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                return b""
            try:
                return await process.stdout.readline()
            except ValueError as error:
                raise ValueError("Garden worker output exceeded its bound") from error

        reply = asyncio.create_task(send_and_read())
        deadline = time.monotonic() + timeout_seconds
        try:
            while True:
                if blocked():
                    raise GardenBusy("Bird inference needs the hardware. Try again when it is idle.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Garden identification exceeded its deadline")
                done, _ = await asyncio.wait({reply}, timeout=min(poll_seconds, remaining))
                if done:
                    break
            line = reply.result()
            if not line.endswith(b"\n") or line.startswith(b"WORKER_ERROR:"):
                # The worker exits after an error or a crash; its status names the failure.
                exit_code = await asyncio.wait_for(process.wait(), max(deadline - time.monotonic(), 0.1))
                if exit_code != 0:
                    raise GardenNativeWorkerFailed(exit_code, worker_error_type(line))
                raise ValueError("Garden worker returned no valid result")
            if not line.startswith(self.result_prefix):
                raise ValueError("Garden worker returned no valid result")
            result = json.loads(line[len(self.result_prefix) :])
            if not isinstance(result, dict):
                raise ValueError("Invalid garden worker result")
            return result
        finally:
            if not reply.done():
                reply.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await reply

    async def _retire(self, reason: str) -> None:
        """Stop the held child, or join a stop already under way, until it is reaped.

        A cancelled caller still waits for the reap and is cancelled afterwards, so no
        cancellation can leave a child running that nothing owns.
        """
        if self._retiring is None or self._retiring.done():
            if self._process is None:
                return
            self._retiring = asyncio.create_task(self._reap(self._process, reason))
        await finish_despite_cancellation(self._retiring)

    async def _reap(self, process: Any, reason: str) -> None:
        try:
            await stop_worker(process)
        except GardenCleanupFailed:
            # Still owned: shutdown tries again rather than forgetting a live child.
            self.stuck = True
            log.error("garden_worker_stop_failed", module=self.module, pid=process.pid, reason=reason)
            raise
        finally:
            with suppress(OSError, RuntimeError):
                process.stdin.close()
        if self._process is process:
            self._process, self._key = None, None
        log.info("garden_worker_stopped", module=self.module, reason=reason, exit_code=process.returncode)

    def _watch_idle(self) -> None:
        if self._monitor is None or self._monitor.done():
            self._monitor = asyncio.create_task(self._release_when_idle(), name=f"{self.module}_idle")

    async def _release_when_idle(self) -> None:
        while self._process is not None:
            await asyncio.sleep(self.poll_seconds)
            if self._lock.locked() or self._process is None:
                continue
            try:
                pressing = self.release()
            except Exception:
                # Bird state that cannot be read is treated as bird work.
                pressing = True
            if pressing:
                reason = "bird_work"
            elif time.monotonic() - self._idle_since >= self.idle_seconds:
                reason = "idle"
            elif self._process.returncode is not None:
                reason = "exited"
            else:
                continue
            async with self._lock:
                try:
                    await self._retire(reason)
                except GardenCleanupFailed:
                    self.on_stuck()
            return
