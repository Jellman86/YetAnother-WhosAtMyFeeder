"""Synchronous detector API backed by async, owned native child processes.

Crop geometry already runs in callers' bounded threads. Only this adapter crosses
into native model loading/inference; no GPU object or exception enters the owner.
"""

import asyncio
import atexit
from concurrent.futures import Future
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, Coroutine
import weakref

import numpy as np

from app.services.crop_process_protocol import (
    DEVICE_FAILURE_CODES,
    MAX_MESSAGE_BYTES,
    decode_array,
    encode_array,
    message_bytes,
    parse_message,
    validate_metadata,
)
from app.services.native_crash_quarantine import NativeCrashQuarantine, artifact_digest
from app.utils.child_signals import kill_child, terminate_child
from app.utils.python_subprocess import python_subprocess_launch


class CropProcessError(RuntimeError):
    """Public, credential-free failure after the child has been reaped."""


class CropProcessBusyError(CropProcessError):
    """Queue admission expired without disturbing the active detector call."""


class _Transport:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.sessions: set[_Session] = set()
        self.cleanup_failed = False
        self.unreaped: set[_Session] = set()
        self.accepting = True
        self.quarantines: dict[Path, NativeCrashQuarantine] = {}
        self.thread = threading.Thread(target=self.loop.run_forever, name="crop-process-transport", daemon=True)
        self.thread.start()

    def call(self, operation: Coroutine[Any, Any, Any]) -> Any:
        if threading.current_thread() is self.thread:
            operation.close()
            raise CropProcessError("Crop transport cannot wait on itself")
        future: Future = asyncio.run_coroutine_threadsafe(operation, self.loop)
        return future.result()

    async def close(self) -> None:
        self.accepting = False
        await asyncio.gather(*(session.dispose() for session in list(self.sessions)), return_exceptions=True)


_transport: _Transport | None = None
_transport_lock = threading.Lock()


def _runtime() -> _Transport:
    global _transport
    with _transport_lock:
        if _transport is None:
            _transport = _Transport()
        return _transport


def open_crop_processes() -> None:
    """A new application lifespan can admit work after the preceding shutdown."""
    if _transport is not None:
        _transport.accepting = True


def crop_cleanup_pending() -> bool:
    return _transport is not None and _transport.cleanup_failed


def close_crop_processes() -> None:
    if _transport is not None:
        _transport.call(_transport.close())


atexit.register(close_crop_processes)


class _Session:
    def __init__(
        self,
        model_path: Path,
        provider: str,
        command: list[str],
        profile: dict[str, Any],
        quarantine: NativeCrashQuarantine,
        startup_timeout: float,
        inference_timeout: float,
        queue_timeout: float = 60,
    ) -> None:
        self.model_path, self.provider, self.command = model_path, provider, command
        self.profile, self.quarantine = profile, quarantine
        self.startup_timeout, self.inference_timeout = startup_timeout, inference_timeout
        self.queue_timeout = queue_timeout
        self.disposed = False
        self.launch_task: asyncio.Task | None = None
        self.reap_task: asyncio.Task | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.stderr_task: asyncio.Task | None = None
        self.closed = False
        self.fault_recorded = False
        self.close_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()
        self.metadata: dict[str, Any] = {}

    def _check_launch_allowed(self) -> None:
        if _runtime().cleanup_failed:
            raise CropProcessError("Crop process cleanup is unconfirmed; new native work is blocked")
        if self.disposed or not _runtime().accepting:
            raise CropProcessError("Crop process owner is shutting down")

    async def start(self) -> None:
        self._check_launch_allowed()
        await asyncio.to_thread(self.quarantine.guard, self.profile)
        self._check_launch_allowed()
        self.closed = False
        self.fault_recorded = False
        self.close_task = None
        self.process = None
        _runtime().sessions.add(self)
        executable, environment = python_subprocess_launch(dict(os.environ))
        assert environment is not None
        environment["YAWAMF_CROP_OWNER_PID"] = str(os.getpid())
        command = self.command or [executable, "-m", "app.services.crop_process_worker"]
        try:
            # Publish the launch future before yielding so shutdown owns a child
            # even if process creation has not returned its handle yet.
            self.launch_task = asyncio.create_task(
                asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=MAX_MESSAGE_BYTES + 1,
                    env=environment,
                )
            )
            self.process = await asyncio.shield(self.launch_task)
            if self.closed or self.disposed or not _runtime().accepting:
                raise CropProcessError("Crop process owner is shutting down")
            self.stderr_task = asyncio.create_task(self._drain_stderr())
            async with asyncio.timeout(self.startup_timeout):
                self.metadata = await self.exchange({"model_path": str(self.model_path), "provider": self.provider})
                await self._raise_worker_error(self.metadata)
                validate_metadata(self.metadata)
        except BaseException as error:
            await self._fail(error, "Crop worker failed during model loading")

    async def _fail(self, error: BaseException, message: str) -> None:
        try:
            await self.close()
        except BaseException:
            if isinstance(error, asyncio.CancelledError):
                raise error
            raise
        finally:
            await self.record_fault()
        if isinstance(error, asyncio.CancelledError):
            raise error
        raise CropProcessError(message) from None

    async def _drain_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        # Native banners/errors can contain paths. Consume a bounded chunk at a
        # time without retaining or forwarding any raw provider output.
        while await self.process.stderr.read(4096):
            pass

    async def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.closed or self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise CropProcessError("Crop worker is closed")
        self.process.stdin.write(message_bytes(request))
        await self.process.stdin.drain()
        return parse_message(await self.process.stdout.readline())

    async def infer(self, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        try:
            await asyncio.wait_for(self.lock.acquire(), self.queue_timeout)
        except TimeoutError:
            raise CropProcessBusyError("Crop worker queue deadline exceeded") from None
        try:
            if self.disposed:
                raise CropProcessError("Crop worker is closed")
            # A timeout or ordinary exit does not quarantine a model. The next
            # admitted call may reload, after cleanup and the retained guard.
            if self.closed:
                await self.close()
                await self.start()
            elif self.process is not None and self.process.returncode is not None:
                await self.close()
                await self.record_fault()
                await self.start()
            try:
                async with asyncio.timeout(self.inference_timeout):
                    response = await self.exchange({"feeds": {k: encode_array(v) for k, v in feeds.items()}})
                    await self._raise_worker_error(response)
                    values = response.get("outputs")
                    if not isinstance(values, list) or not 1 <= len(values) <= 16:
                        raise CropProcessError("Crop worker returned invalid outputs")
                    return [decode_array(value) for value in values]
            except BaseException as error:
                await self._fail(error, "Crop worker inference failed")
        finally:
            self.lock.release()

    async def _raise_worker_error(self, response: dict[str, Any]) -> None:
        if not response.get("error"):
            return
        # The child exits without destroying failed native state. Reap before
        # returning an error that can cause the caller to construct CPU.
        assert self.process is not None
        await self.process.wait()
        code = response.get("device_error")
        if isinstance(code, str) and code in DEVICE_FAILURE_CODES:
            self.fault_recorded = True
            self.quarantine.remember_retirement(self.profile)
            await asyncio.to_thread(
                self.quarantine.record_retirement, self.profile, code, "Crop detector device failure"
            )
        raise CropProcessError("Crop worker failed")

    async def record_fault(self) -> None:
        if self.process is not None and self.process.returncode is not None and not self.fault_recorded:
            self.fault_recorded = True
            self.quarantine.remember(self.profile, self.process.returncode)
            await asyncio.to_thread(self.quarantine.record, self.profile, self.process.returncode)

    async def dispose(self) -> None:
        self.disposed = True
        await self.close()

    async def close(self) -> None:
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        task = self.close_task
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _close(self) -> None:
        self.closed = True
        if self.launch_task is not None:
            try:
                self.process = await asyncio.shield(self.launch_task)
            except Exception:
                pass
        if self.process is not None:
            if self.process.returncode is None:
                # Let natural EOF/native exit win before sending termination, so
                # a real SIGABRT is not mistaken for our cleanup signal.
                try:
                    await asyncio.wait_for(asyncio.shield(self.process.wait()), 0.05)
                except TimeoutError:
                    try:
                        terminate_child(self.process)
                    except ProcessLookupError:
                        pass
            try:
                await asyncio.wait_for(asyncio.shield(self.process.wait()), 2)
            except TimeoutError:
                try:
                    kill_child(self.process)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(asyncio.shield(self.process.wait()), 5)
                except BaseException:
                    runtime = _runtime()
                    runtime.cleanup_failed = True
                    runtime.unreaped.add(self)
                    self.reap_task = asyncio.create_task(self._wait_for_reap())
                    from app.services.error_diagnostics import error_diagnostics_history

                    error_diagnostics_history.record(
                        source="crop_detector",
                        component="crop_worker",
                        severity="error",
                        reason_code="crop_cleanup_unconfirmed",
                        message="Crop child cleanup is unconfirmed; new detector launches are blocked until it exits.",
                        context={"model_id": self.profile.get("model_id"), "configured_provider": self.provider},
                    )
                    raise CropProcessError("Crop process cleanup is unconfirmed") from None
        await self._finish_reap()

    async def _wait_for_reap(self) -> None:
        assert self.process is not None
        await self.process.wait()
        await self.record_fault()
        await self._finish_reap()
        runtime = _runtime()
        runtime.unreaped.discard(self)
        runtime.cleanup_failed = bool(runtime.unreaped)
        # A failed close future belongs to the unreaped child. Once reaped,
        # the cached CPU session must be able to pass its guard and reload.
        self.close_task = None

    async def _finish_reap(self) -> None:
        if self.stderr_task is not None:
            try:
                await asyncio.wait_for(self.stderr_task, 1)
            except TimeoutError:
                self.stderr_task.cancel()
        _runtime().sessions.discard(self)


class CropProcessSession:
    def __init__(
        self,
        model_path: Path,
        *,
        provider: str,
        model_id: str,
        command: list[str] | None = None,
        profile: dict[str, Any] | None = None,
        quarantine: NativeCrashQuarantine | None = None,
        startup_timeout: float = 180,
        inference_timeout: float = 45,
        queue_timeout: float = 60,
    ) -> None:
        self._require_caller_thread()
        if profile is None:
            from app.services.model_validation import current_inference_runtime_signature

            profile = {
                "schema": 1,
                "operation": "crop_detector",
                "model_id": model_id,
                "provider": provider,
                "model_sha256": artifact_digest(str(model_path)),
                "external_weights_sha256": artifact_digest(str(model_path) + ".data"),
                "runtime_signature": current_inference_runtime_signature(),
            }
            if not profile["model_sha256"]:
                raise CropProcessError("Crop detector artifact is unavailable")
        runtime = _runtime()
        if quarantine is None:
            root = Path(os.environ.get("CONFIG_DIR", "/config")) / "native-crashes"
            with _transport_lock:
                if root not in runtime.quarantines:
                    runtime.quarantines[root] = NativeCrashQuarantine(lambda: {}, root=root)
                quarantine = runtime.quarantines[root]
        guard = quarantine
        self._session = _Session(
            model_path, provider, command or [], profile, guard, startup_timeout, inference_timeout, queue_timeout
        )
        self._runtime = _runtime()
        self._runtime.call(self._session.start())
        self._finalizer = weakref.finalize(self, self._close_transport, self._runtime, self._session)

    @staticmethod
    def _require_caller_thread() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise CropProcessError("Crop inference must run outside the API event loop")

    @staticmethod
    def _close_transport(runtime: _Transport, session: _Session) -> None:
        operation = session.dispose()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            runtime.call(operation)
        else:
            # Reset can release the last model reference on the API loop.
            # Cleanup stays owned by the transport and shutdown joins it.
            asyncio.run_coroutine_threadsafe(operation, runtime.loop)

    @property
    def pid(self) -> int | None:
        return self._session.process.pid if self._session.process else None

    @property
    def exit_code(self) -> int | None:
        return self._session.process.returncode if self._session.process else None

    def get_inputs(self) -> list[Any]:
        return [SimpleNamespace(**value) for value in self._session.metadata["inputs"]]

    def get_outputs(self) -> list[Any]:
        return [SimpleNamespace(**value) for value in self._session.metadata["outputs"]]

    def get_providers(self) -> list[str]:
        return list(self._session.metadata["providers"])

    def run(self, _names: Any, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        self._require_caller_thread()
        return self._runtime.call(self._session.infer(feeds))

    def close(self) -> None:
        self._finalizer()
