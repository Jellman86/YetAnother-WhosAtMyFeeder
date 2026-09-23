"""Bounded, same-artifact CPU recovery without loading native code in the parent."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable

from .classifier_worker_client import ClassifierWorkerClient
from .classifier_worker_protocol import build_classify_request, build_classify_video_request
from .native_crash_quarantine import NativeCrashQuarantine


class NativeCpuRecoveryUnavailable(RuntimeError):
    """CPU recovery could not meet the identity or workload deadline contract."""


class NativeCpuRecovery:
    def __init__(
        self,
        profile_getter: Callable[[], dict[str, Any]],
        quarantine: NativeCrashQuarantine,
        *,
        worker_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._profile_getter = profile_getter
        self._quarantine = quarantine
        self._worker_factory = worker_factory or self._new_worker
        self._lock = asyncio.Lock()
        self._worker: Any = None
        self._profile: dict[str, Any] | None = None
        self._source_profile: dict[str, Any] | None = None
        self._states: dict[str, dict[str, Any]] = {}
        self._reported_states: set[tuple[str, str]] = set()
        self._generation = 0
        self._closed = False
        self._cleanup_pending = False

    def _new_worker(self) -> ClassifierWorkerClient:
        self._generation += 1
        return ClassifierWorkerClient(
            worker_name="native-cpu",
            worker_generation=self._generation,
            heartbeat_timeout_seconds=5,
            inference_provider_override="cpu",
        )

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._states.items()}

    def _state(self, priority: str, status: str, runtime: dict[str, Any] | None = None) -> None:
        self._states[priority] = {
            "status": status,
            "reason": "native_crash_same_model_cpu",
            "at": time.time(),
            "recovered": status == "degraded",
            "runtime": runtime,
        }
        if status in {"degraded", "failed"} and (priority, status) not in self._reported_states:
            self._reported_states.add((priority, status))
            from .error_diagnostics import error_diagnostics_history

            error_diagnostics_history.record(
                source="classifier",
                component="classifier_worker",
                severity="warning",
                reason_code=f"native_cpu_recovery_{status}",
                message="Same-model isolated CPU recovery completed."
                if status == "degraded"
                else "Same-model isolated CPU recovery did not meet the workload contract.",
                context={
                    "status": status,
                    "worker_pool": priority,
                    "model_id": (self._profile or {}).get("model_id"),
                    "active_provider": (runtime or {}).get("active_provider"),
                },
            )

    async def refresh_profile(self) -> None:
        async with self._lock:
            if (
                self._source_profile is not None
                and await asyncio.to_thread(self._profile_getter) != self._source_profile
            ):
                await self._close_worker()
                self._profile = self._source_profile = None
                self._states.clear()
                self._reported_states.clear()

    def _validate_runtime(self, runtime: Any) -> dict[str, Any]:
        if not isinstance(runtime, dict) or runtime.get("active_provider") not in {"cpu", "intel_cpu", "tflite"}:
            raise NativeCpuRecoveryUnavailable("CPU worker did not confirm a CPU provider")
        assert self._profile is not None
        for field in ("model_id", "model_sha256", "external_weights_sha256", "labels_sha256"):
            if runtime.get(field) != self._profile.get(field):
                raise NativeCpuRecoveryUnavailable("CPU worker loaded a different artifact")
        if not runtime.get("model_sha256"):
            raise NativeCpuRecoveryUnavailable("CPU worker artifact identity is unavailable")
        return dict(runtime)

    async def _close_worker(self) -> None:
        worker = self._worker
        if worker is None:
            return
        # Keep ownership on failed cleanup, so another request cannot replace
        # an unreaped native process. Client.kill is bounded and cancellation-safe.
        self._cleanup_pending = True
        await worker.kill()
        await worker.wait_closed()
        exit_code = worker.get_status().get("exit_code")
        native_fault = self._quarantine.remember(self._profile, exit_code)
        self._worker = None
        self._cleanup_pending = False
        if native_fault:
            await asyncio.to_thread(self._quarantine.record, self._profile, exit_code)

    async def shutdown(self) -> None:
        self._closed = True
        async with self._lock:
            await self._close_worker()

    async def _next_event(self) -> dict[str, Any]:
        event_task = asyncio.create_task(self._worker.next_event())
        closed_task = asyncio.create_task(self._worker.wait_closed())
        try:
            done, _ = await asyncio.wait({event_task, closed_task}, return_when=asyncio.FIRST_COMPLETED)
            if closed_task in done:
                raise NativeCpuRecoveryUnavailable("CPU worker exited")
            return event_task.result()
        finally:
            for task in (event_task, closed_task):
                task.cancel()
            await asyncio.gather(event_task, closed_task, return_exceptions=True)

    async def run(
        self,
        *,
        priority: str,
        timeout_seconds: float,
        payload: dict[str, Any],
        progress_callback: Callable[..., Any] | None = None,
    ) -> list[dict[str, Any]]:
        acquired = False
        started = False
        try:
            # Queueing, model load, identity checks and inference share one budget.
            # A CPU taking 45 seconds cannot be called recovered for a 35s live job.
            async with asyncio.timeout(timeout_seconds):
                await self._lock.acquire()
                acquired = True
                if self._closed:
                    raise NativeCpuRecoveryUnavailable("CPU recovery is shut down")
                if self._cleanup_pending:
                    await self._close_worker()
                profile = await asyncio.to_thread(self._profile_getter)
                if profile.get("provider") in {"cpu", "intel_cpu", "tflite"}:
                    raise NativeCpuRecoveryUnavailable("The failing profile already uses CPU")
                cpu_profile = profile | {"provider": "cpu"}
                if cpu_profile != self._profile:
                    await self._close_worker()
                    self._profile = cpu_profile
                    self._source_profile = profile
                    self._states.clear()
                    self._reported_states.clear()
                if self._states.get(priority, {}).get("status") == "failed":
                    raise NativeCpuRecoveryUnavailable("CPU recovery already failed for this workload")
                await asyncio.to_thread(self._quarantine.guard, cpu_profile)
                started = True
                self._state(priority, "recovering")
                if self._worker is None:
                    self._worker = self._worker_factory()
                    await self._worker.start()
                    await self._worker.wait_until_ready(timeout_seconds=timeout_seconds)
                self._validate_runtime(self._worker.get_status().get("runtime"))
                request_id = f"cpu-{time.monotonic_ns()}"
                build = build_classify_video_request if priority == "video" else build_classify_request
                message = build(
                    worker_generation=self._worker.worker_generation,
                    request_id=request_id,
                    work_id=request_id,
                    lease_token=1,
                    **payload,
                )
                await self._worker.send(message)
                while True:
                    event = await self._next_event()
                    if event.get("type") == "exit":
                        raise NativeCpuRecoveryUnavailable("CPU worker exited")
                    if any(
                        event.get(key) != message[key]
                        for key in ("worker_generation", "request_id", "work_id", "lease_token")
                    ):
                        continue
                    if event["type"] == "error":
                        raise NativeCpuRecoveryUnavailable("CPU worker inference failed")
                    if event["type"] == "progress" and progress_callback is not None:
                        try:
                            result = progress_callback(
                                *(
                                    event.get(key)
                                    for key in (
                                        "current_frame",
                                        "total_frames",
                                        "frame_score",
                                        "top_label",
                                        "frame_thumb",
                                        "frame_index",
                                        "clip_total",
                                        "model_name",
                                        "frame_offset_seconds",
                                    )
                                )
                            )
                            if inspect.isawaitable(result):
                                await result
                        except Exception:
                            pass  # Progress is best effort, never a classification result.
                    if event["type"] == "result":
                        runtime = self._validate_runtime(event.get("runtime"))
                        self._state(priority, "degraded", runtime)
                        return event["results"]
        except BaseException as exc:
            if acquired and started:
                self._state(priority, "failed")
                try:
                    await self._close_worker()
                except Exception as cleanup_error:
                    if isinstance(exc, asyncio.CancelledError):
                        raise exc from cleanup_error
                    raise NativeCpuRecoveryUnavailable("CPU worker cleanup is still pending") from cleanup_error
            if isinstance(exc, asyncio.CancelledError):
                raise
            if not isinstance(exc, Exception):
                raise
            raise NativeCpuRecoveryUnavailable("Same-model CPU recovery unavailable within workload budget") from exc
        finally:
            if acquired:
                self._lock.release()
