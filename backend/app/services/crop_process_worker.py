"""Private detector process; exit without native teardown on every failure."""

import os
import queue
import sys
import threading
from typing import Any

from app.services.crop_process_protocol import (
    DEVICE_FAILURE_CODES,
    decode_array,
    encode_array,
    read_message,
    write_message,
)


def _device_error(error: BaseException) -> str | None:
    import re

    seen: set[int] = set()
    while error is not None and id(error) not in seen and len(seen) < 8:
        seen.add(id(error))
        text = str(error)[:20000]
        for code in sorted(DEVICE_FAILURE_CODES):
            if code in text:
                return code
        if re.search(r"clWaitForEvents[^\n]{0,150}(-14|DEVICE)", text):
            return "CL_EXEC_STATUS_ERROR_FOR_EVENTS_IN_WAIT_LIST"
        error = error.__cause__ or error.__context__
    return None


def _bind_owner() -> None:
    if sys.platform != "linux":
        return
    import ctypes
    import signal

    # The kernel backstop does not need the GIL, unlike the pipe reader. It
    # follows the spawning transport thread, which lives for the owner process.
    # Include its PID so an owner lost before prctl cannot leave an orphan.
    expected = int(os.environ.get("YAWAMF_CROP_OWNER_PID", str(os.getppid())))
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise RuntimeError("Cannot establish crop process ownership")
    if os.getppid() != expected:
        os._exit(0)


def main() -> None:
    writer = os.fdopen(os.dup(sys.stdout.fileno()), "wb", closefd=True)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    requests: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)

    def receive() -> None:
        while True:
            try:
                message = read_message(sys.stdin.buffer)
            except BaseException:
                # EOF means the owner died, including when its worker crashed.
                # No native cleanup hooks may keep this process alive afterward.
                os._exit(0)
            requests.put(message)

    threading.Thread(target=receive, name="crop-owner-pipe", daemon=True).start()
    try:
        _bind_owner()
        request = requests.get()
        from app.services.bird_crop_service import BirdCropService

        service = BirdCropService()
        session = service._create_native_session(
            request["model_path"], provider=request["provider"], model_id="crop-worker"
        )

        def ports(values: list[Any]) -> list[dict[str, Any]]:
            return [
                {
                    "name": str(v.name),
                    "shape": [int(x) if isinstance(x, int) else str(x) for x in v.shape],
                    "type": str(getattr(v, "type", "tensor(float)")),
                }
                for v in values
            ]

        write_message(
            writer,
            {
                "ready": True,
                "inputs": ports(session.get_inputs()),
                "outputs": ports(session.get_outputs()),
                "providers": session.get_providers(),
            },
        )
        while True:
            request = requests.get()
            feeds = {name: decode_array(value) for name, value in request["feeds"].items()}
            outputs = session.run(None, feeds)
            if "CUDAExecutionProvider" in session.get_providers():
                from app.utils.cuda_runtime import verify_cuda_session_provider

                verify_cuda_session_provider(session)
            write_message(writer, {"outputs": [encode_array(value) for value in outputs]})
    except BaseException as error:
        # Keep the original exception/traceback/native references alive until
        # os._exit: clearing them killed the API during GPU-to-CPU fallback.
        try:
            write_message(writer, {"error": "inference_failed", "device_error": _device_error(error)})
        finally:
            os._exit(3)


if __name__ == "__main__":
    main()
