import asyncio
import os
import inspect
import sys
from base64 import b64decode
from io import BytesIO
from typing import Any, Awaitable, Callable

from PIL import Image

from .classifier_worker_protocol import (
    build_error_event,
    build_heartbeat_event,
    build_progress_event,
    build_ready_event,
    build_runtime_recovery_event,
    build_result_event,
    decode_protocol_message,
    encode_protocol_message,
)

WORKER_PROTOCOL_STREAM_LIMIT_BYTES = 4 * 1024 * 1024


class _StdoutWriter:
    def __init__(self, stream: Any | None = None) -> None:
        self._stream = stream or sys.stdout.buffer

    def write(self, data: bytes) -> None:
        self._stream.write(data)

    async def drain(self) -> None:
        await asyncio.to_thread(self._stream.flush)

    def close(self) -> None:
        self._stream.flush()
        close = getattr(self._stream, "close", None)
        if callable(close):
            close()


class ClassifierWorkerProcess:
    def __init__(
        self,
        *,
        reader: asyncio.StreamReader,
        writer: Any,
        classify_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]],
        classify_video_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]] | None = None,
        worker_generation: int,
        heartbeat_interval_seconds: float = 1.0,
        runtime_recovery_getter: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.classify_fn = classify_fn
        self.classify_video_fn = classify_video_fn
        self.worker_generation = int(worker_generation)
        self.heartbeat_interval_seconds = max(0.01, float(heartbeat_interval_seconds))
        self.runtime_recovery_getter = runtime_recovery_getter
        self._closed = False
        self._busy = False
        self._current_request_id: str | None = None

    @staticmethod
    def encode_message(message: dict[str, Any]) -> bytes:
        return encode_protocol_message(message)

    async def run(self) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            await self._emit(build_ready_event(worker_generation=self.worker_generation))
            while not self._closed:
                raw = await self.reader.readline()
                if not raw:
                    break
                message = decode_protocol_message(raw)
                if message["type"] == "shutdown":
                    break
                if message["type"] == "classify":
                    await self._handle_classify(message)
                if message["type"] == "classify_video":
                    await self._handle_classify_video(message)
        finally:
            self._closed = True
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            close = getattr(self.writer, "close", None)
            if callable(close):
                close()

    async def _emit(self, message: dict[str, Any]) -> None:
        self.writer.write(encode_protocol_message(message))
        await self.writer.drain()

    async def _heartbeat_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            if self._closed:
                return
            await self._emit(
                build_heartbeat_event(
                    worker_generation=self.worker_generation,
                    request_id=self._current_request_id,
                    busy=self._busy,
                )
            )

    async def _handle_classify(self, message: dict[str, Any]) -> None:
        self._busy = True
        self._current_request_id = str(message["request_id"])
        try:
            before_recovery = self._runtime_recovery_snapshot()
            classify_kwargs = {
                "image_b64": message["image_b64"],
                "camera_name": message.get("camera_name"),
                "model_id": message.get("model_id"),
            }
            if "input_context" in message:
                classify_kwargs["input_context"] = message.get("input_context")
            results = await self._run_classify(**classify_kwargs)
            after_recovery = self._runtime_recovery_snapshot()
            if after_recovery is not None and after_recovery != before_recovery:
                await self._emit(
                    build_runtime_recovery_event(
                        worker_generation=self.worker_generation,
                        request_id=str(message["request_id"]),
                        work_id=str(message["work_id"]),
                        lease_token=int(message["lease_token"]),
                        recovery=after_recovery,
                    )
                )
            await self._emit(
                build_result_event(
                    worker_generation=self.worker_generation,
                    request_id=str(message["request_id"]),
                    work_id=str(message["work_id"]),
                    lease_token=int(message["lease_token"]),
                    results=results,
                )
            )
        except Exception as exc:
            await self._emit(
                build_error_event(
                    worker_generation=self.worker_generation,
                    request_id=str(message["request_id"]),
                    work_id=str(message["work_id"]),
                    lease_token=int(message["lease_token"]),
                    error=str(exc),
                )
            )
        finally:
            self._busy = False
            self._current_request_id = None

    async def _handle_classify_video(self, message: dict[str, Any]) -> None:
        self._busy = True
        self._current_request_id = str(message["request_id"])
        try:
            before_recovery = self._runtime_recovery_snapshot()
            loop = asyncio.get_running_loop()

            def _progress_callback(*args, **kwargs):
                current = kwargs.get("current_frame", kwargs.get("current"))
                total = kwargs.get("total_frames", kwargs.get("total"))
                score = kwargs.get("frame_score", kwargs.get("score"))
                label = kwargs.get("top_label", kwargs.get("label"))
                frame_thumb = kwargs.get("frame_thumb")
                frame_index = kwargs.get("frame_index")
                clip_total = kwargs.get("clip_total")
                model_name = kwargs.get("model_name")

                if current is None and len(args) > 0:
                    current = args[0]
                if total is None and len(args) > 1:
                    total = args[1]
                if score is None and len(args) > 2:
                    score = args[2]
                if label is None and len(args) > 3:
                    label = args[3]
                if frame_thumb is None and len(args) > 4:
                    frame_thumb = args[4]
                if frame_index is None and len(args) > 5:
                    frame_index = args[5]
                if clip_total is None and len(args) > 6:
                    clip_total = args[6]
                if model_name is None and len(args) > 7:
                    model_name = args[7]

                if current is None or total is None or score is None or label is None:
                    return None

                future = asyncio.run_coroutine_threadsafe(
                    self._emit_progress(
                        request_id=str(message["request_id"]),
                        work_id=str(message["work_id"]),
                        lease_token=int(message["lease_token"]),
                        current=current,
                        total=total,
                        score=score,
                        label=label,
                        frame_thumb=frame_thumb,
                        frame_index=frame_index,
                        clip_total=clip_total,
                        model_name=model_name,
                    ),
                    loop,
                )
                try:
                    future.result(timeout=1.0)
                except Exception:
                    # Progress delivery is best-effort; do not fail the classification
                    # if the parent process is slow to consume progress updates.
                    return None

            results = await self._run_classify_video(
                video_path=message["video_path"],
                stride=int(message.get("stride") or 5),
                max_frames=message.get("max_frames"),
                progress_callback=_progress_callback,
                input_context=message.get("input_context"),
            )
            after_recovery = self._runtime_recovery_snapshot()
            if after_recovery is not None and after_recovery != before_recovery:
                await self._emit(
                    build_runtime_recovery_event(
                        worker_generation=self.worker_generation,
                        request_id=str(message["request_id"]),
                        work_id=str(message["work_id"]),
                        lease_token=int(message["lease_token"]),
                        recovery=after_recovery,
                    )
                )
            await self._emit(
                build_result_event(
                    worker_generation=self.worker_generation,
                    request_id=str(message["request_id"]),
                    work_id=str(message["work_id"]),
                    lease_token=int(message["lease_token"]),
                    results=results,
                )
            )
        except Exception as exc:
            await self._emit(
                build_error_event(
                    worker_generation=self.worker_generation,
                    request_id=str(message["request_id"]),
                    work_id=str(message["work_id"]),
                    lease_token=int(message["lease_token"]),
                    error=str(exc),
                )
            )
        finally:
            self._busy = False
            self._current_request_id = None

    def _runtime_recovery_snapshot(self) -> dict[str, Any] | None:
        if self.runtime_recovery_getter is None:
            return None
        recovery = self.runtime_recovery_getter()
        if recovery is None:
            return None
        return dict(recovery)

    def _classify_accepts_input_context(self) -> bool:
        try:
            signature = inspect.signature(self.classify_fn)
        except (TypeError, ValueError):
            return False
        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD or param.name == "input_context"
            for param in signature.parameters.values()
        )

    def _classify_video_accepts_input_context(self) -> bool:
        if self.classify_video_fn is None:
            return False
        try:
            signature = inspect.signature(self.classify_video_fn)
        except (TypeError, ValueError):
            return False
        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD or param.name == "input_context"
            for param in signature.parameters.values()
        )

    async def _run_classify(self, **kwargs: Any) -> list[dict[str, Any]]:
        if "input_context" in kwargs and not self._classify_accepts_input_context():
            kwargs = dict(kwargs)
            kwargs.pop("input_context", None)

        if inspect.iscoroutinefunction(self.classify_fn):
            return list(await self.classify_fn(**kwargs))
        return list(await asyncio.to_thread(self.classify_fn, **kwargs))

    async def _run_classify_video(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self.classify_video_fn is None:
            raise RuntimeError("video classification is not configured")
        if "input_context" in kwargs and not self._classify_video_accepts_input_context():
            kwargs = dict(kwargs)
            kwargs.pop("input_context", None)
        if inspect.iscoroutinefunction(self.classify_video_fn):
            return list(await self.classify_video_fn(**kwargs))
        return list(await asyncio.to_thread(self.classify_video_fn, **kwargs))

    async def _emit_progress(
        self,
        *,
        request_id: str,
        work_id: str,
        lease_token: int,
        current: int,
        total: int,
        score: float,
        label: str,
        frame_thumb: str | None = None,
        frame_index: int | None = None,
        clip_total: int | None = None,
        model_name: str | None = None,
    ) -> None:
        await self._emit(
            build_progress_event(
                worker_generation=self.worker_generation,
                request_id=request_id,
                work_id=work_id,
                lease_token=lease_token,
                current_frame=current,
                total_frames=total,
                frame_score=score,
                top_label=label,
                frame_thumb=frame_thumb,
                frame_index=frame_index,
                clip_total=clip_total,
                model_name=model_name,
            )
        )


async def run_worker_main(
    *,
    classify_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]],
    classify_video_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]] | None = None,
    worker_generation: int = 1,
    heartbeat_interval_seconds: float = 1.0,
    writer: Any | None = None,
    runtime_recovery_getter: Callable[[], dict[str, Any] | None] | None = None,
) -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=WORKER_PROTOCOL_STREAM_LIMIT_BYTES)
    protocol = asyncio.StreamReaderProtocol(reader)
    try:
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    except (PermissionError, OSError):
        reader.feed_eof()
    worker = ClassifierWorkerProcess(
        reader=reader,
        writer=writer or _StdoutWriter(),
        classify_fn=classify_fn,
        classify_video_fn=classify_video_fn,
        worker_generation=worker_generation,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        runtime_recovery_getter=runtime_recovery_getter,
    )
    await worker.run()


def _build_default_classify_fn() -> Callable[..., list[dict[str, Any]]]:
    if os.getenv("YA_WAMF_CLASSIFIER_WORKER_TEST_MODE") == "1":
        def _test_classify_fn(**_kwargs: Any) -> list[dict[str, Any]]:
            return [{"label": "WorkerTest", "score": 0.99}]

        return _test_classify_fn

    from .classifier_service import ClassifierService

    service = ClassifierService(worker_process_mode=True)

    def _classify_fn(
        *,
        image_b64: str,
        camera_name: str | None,
        model_id: str | None,
        input_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        image = Image.open(BytesIO(b64decode(image_b64.encode("ascii")))).convert("RGB")
        return service.classify(image, camera_name=camera_name, model_id=model_id, input_context=input_context)

    _classify_fn._runtime_recovery_getter = lambda: service._last_runtime_recovery  # type: ignore[attr-defined]
    _classify_fn._video_classify_fn = service.classify_video  # type: ignore[attr-defined]
    return _classify_fn


def main() -> None:
    worker_generation = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    heartbeat_interval_seconds = float(os.getenv("CLASSIFIER_WORKER_HEARTBEAT_INTERVAL_SECONDS", "1.0"))
    protocol_stdout = os.fdopen(os.dup(sys.stdout.fileno()), "wb", closefd=True)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    asyncio.run(
        run_worker_main(
            classify_fn=(classify_fn := _build_default_classify_fn()),
            classify_video_fn=getattr(classify_fn, "_video_classify_fn", None),
            worker_generation=worker_generation,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            writer=_StdoutWriter(protocol_stdout),
            runtime_recovery_getter=getattr(classify_fn, "_runtime_recovery_getter", None),
        )
    )


if __name__ == "__main__":
    main()
