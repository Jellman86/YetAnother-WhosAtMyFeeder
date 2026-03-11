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
    build_ready_event,
    build_result_event,
    decode_protocol_message,
    encode_protocol_message,
)


class _StdoutWriter:
    def write(self, data: bytes) -> None:
        sys.stdout.buffer.write(data)

    async def drain(self) -> None:
        await asyncio.to_thread(sys.stdout.buffer.flush)

    def close(self) -> None:
        sys.stdout.buffer.flush()


class ClassifierWorkerProcess:
    def __init__(
        self,
        *,
        reader: asyncio.StreamReader,
        writer: Any,
        classify_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]],
        worker_generation: int,
        heartbeat_interval_seconds: float = 1.0,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.classify_fn = classify_fn
        self.worker_generation = int(worker_generation)
        self.heartbeat_interval_seconds = max(0.01, float(heartbeat_interval_seconds))
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
            results = await self._run_classify(
                image_b64=message["image_b64"],
                camera_name=message.get("camera_name"),
                model_id=message.get("model_id"),
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

    async def _run_classify(self, **kwargs: Any) -> list[dict[str, Any]]:
        if inspect.iscoroutinefunction(self.classify_fn):
            return list(await self.classify_fn(**kwargs))
        return list(await asyncio.to_thread(self.classify_fn, **kwargs))


async def run_worker_main(
    *,
    classify_fn: Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]],
    worker_generation: int = 1,
    heartbeat_interval_seconds: float = 1.0,
) -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    worker = ClassifierWorkerProcess(
        reader=reader,
        writer=_StdoutWriter(),
        classify_fn=classify_fn,
        worker_generation=worker_generation,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    await worker.run()


def _build_default_classify_fn() -> Callable[..., list[dict[str, Any]]]:
    if os.getenv("YA_WAMF_CLASSIFIER_WORKER_TEST_MODE") == "1":
        def _test_classify_fn(**_kwargs: Any) -> list[dict[str, Any]]:
            return [{"label": "WorkerTest", "score": 0.99}]

        return _test_classify_fn

    from .classifier_service import ClassifierService

    service = ClassifierService(worker_process_mode=True)

    def _classify_fn(*, image_b64: str, camera_name: str | None, model_id: str | None) -> list[dict[str, Any]]:
        image = Image.open(BytesIO(b64decode(image_b64.encode("ascii")))).convert("RGB")
        return service.classify(image, camera_name=camera_name, model_id=model_id)

    return _classify_fn


def main() -> None:
    worker_generation = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    heartbeat_interval_seconds = float(os.getenv("CLASSIFIER_WORKER_HEARTBEAT_INTERVAL_SECONDS", "1.0"))
    asyncio.run(
        run_worker_main(
            classify_fn=_build_default_classify_fn(),
            worker_generation=worker_generation,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )
    )


if __name__ == "__main__":
    main()
