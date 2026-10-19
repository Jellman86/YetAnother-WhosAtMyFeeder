"""Parent-owned deadline, memory, pressure and reaping for an owner diagnostic."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
from typing import Any

from app.utils.image_io import MAX_IMAGE_BYTES
from app.utils.python_subprocess import python_subprocess_launch

MAX_VIDEO_BYTES = 32 * 1024 * 1024
PROBE_TIMEOUT_SECONDS = 300.0
CLEANUP_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 0.25


class ProbeCleanupFailed(RuntimeError):
    """A diagnostic still owns native resources; another attempt is unsafe."""


def available_memory() -> int:
    """Physical and known container headroom; unreadable usage counters fail closed."""
    from app.services.host_facts import _read_cgroup_memory_limit

    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    available = values["MemAvailable"]
    limit = _read_cgroup_memory_limit()
    if limit is not None:
        try:
            current = int(Path("/sys/fs/cgroup/memory.current").read_text())
        except OSError:
            current = int(Path("/sys/fs/cgroup/memory/memory.usage_in_bytes").read_text())
        available = min(available, max(0, limit - current))
    return available


def group_usage(group: int) -> tuple[int, int]:
    rss = alive = 0
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal():
            continue
        belongs_to_probe = False
        try:
            if os.getpgid(int(directory.name)) != group:
                continue
            belongs_to_probe = True
            entries = {}
            for line in (directory / "status").read_text().splitlines():
                key, value = line.split(":", 1)
                entries[key] = value.strip()
            if not entries.get("State", "").startswith("Z"):
                alive += 1
                rss += int(entries.get("VmRSS", "0 kB").split()[0]) * 1024
        except ProcessLookupError:
            continue
        except FileNotFoundError:
            continue
        except PermissionError:
            if belongs_to_probe:
                raise ValueError("Diagnostic memory usage is no longer observable.") from None
            continue
    return rss, alive


def memory_budget() -> int:
    from app.services.model_manager import model_manager

    path = Path(model_manager.get_active_model_spec()["model_path"])
    size = path.stat().st_size
    external = Path(str(path) + ".data")
    if external.exists():
        size += external.stat().st_size
    return max(1024**3, min(8 * 1024**3, size * 4))


def stage_inputs(root: Path, images: list[bytes], video: bytes) -> list[str]:
    if len(images) != 3 or any(not image or len(image) > MAX_IMAGE_BYTES for image in images):
        raise ValueError("Choose three images within the classifier upload limit.")
    if not video or len(video) > MAX_VIDEO_BYTES:
        raise ValueError("Choose a short bird clip no larger than 32 MiB.")
    paths = []
    for index, image in enumerate(images):
        path = root / f"photo-{index}.image"
        path.write_bytes(image)
        paths.append(str(path))
    (root / "clip.video").write_bytes(video)
    return paths


async def finish_owned_io(task: asyncio.Task[Any]) -> Any:
    result, cancelled = await _settle(task)
    if cancelled:
        raise asyncio.CancelledError
    return result


async def _settle(task: asyncio.Task[Any]) -> tuple[Any, bool]:
    """Keep ownership of creation/cleanup results even when the caller disconnects."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


async def reap(process: Any) -> None:
    waiter: asyncio.Task[Any] | None = None
    try:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        waiter = asyncio.create_task(process.wait())
        deadline = time.monotonic() + CLEANUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            _, alive = await asyncio.to_thread(group_usage, process.pid)
            if waiter.done() and alive == 0:
                waiter.result()
                return
            await asyncio.wait({waiter}, timeout=min(_POLL_SECONDS, max(0, deadline - time.monotonic())))
        raise ProbeCleanupFailed("Diagnostic process cleanup is still pending")
    except ProbeCleanupFailed:
        raise
    except Exception:
        # Failure to signal or observe the group is not evidence of reaping.
        # Retain ownership and lock out retries just as for a cleanup deadline.
        raise ProbeCleanupFailed("Diagnostic process cleanup could not be verified") from None
    finally:
        if waiter is not None:
            waiter.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)


async def run_profile_probe(
    profile: dict[str, Any], images: list[bytes], video: bytes, pressure: Callable[[], str | None]
) -> dict[str, Any]:
    if os.name != "posix" or not await asyncio.to_thread(Path("/proc/self/status").exists):
        raise ValueError("The external process memory guard is unavailable on this platform.")
    budget = await asyncio.to_thread(memory_budget)
    reserve = 512 * 1024**2
    if await asyncio.to_thread(available_memory) < budget + reserve:
        raise ValueError("There is not enough observable memory headroom for this diagnostic.")
    if reason := pressure():
        raise ValueError(reason)
    base = Path(os.environ.get("CONFIG_DIR", "/config")) / "native-revalidation-work"

    def create_workspace() -> Path:
        base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="check-", dir=base))

    root, cancelled = await _settle(asyncio.create_task(asyncio.to_thread(create_workspace)))
    process = None
    completion = None
    try:
        if cancelled:
            raise asyncio.CancelledError
        paths = await finish_owned_io(asyncio.create_task(asyncio.to_thread(stage_inputs, root, images, video)))
        executable, environment = python_subprocess_launch()
        backend = Path(__file__).resolve().parents[2]
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                executable,
                "-m",
                "scripts.probe_native_profile",
                cwd=str(backend),
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        process, cancelled = await _settle(spawn)
        if cancelled:
            raise asyncio.CancelledError
        payload = json.dumps(
            {
                "profile": profile,
                "images": paths,
                "video": str(root / "clip.video"),
                "result": str(root / "result.json"),
            }
        ).encode()
        completion = asyncio.create_task(process.communicate(payload))
        deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
        while not completion.done():
            if reason := pressure():
                raise ValueError(reason)
            rss, _ = await asyncio.to_thread(group_usage, process.pid)
            if rss > budget or await asyncio.to_thread(available_memory) < reserve:
                raise ValueError("The diagnostic exceeded its monitored memory budget.")
            if time.monotonic() >= deadline:
                raise ValueError("The isolated diagnostic exceeded its deadline.")
            await asyncio.wait({completion}, timeout=_POLL_SECONDS)
        completion.result()
        if process.returncode != 0:
            raise ValueError(
                f"The isolated diagnostic exited with code {process.returncode}. The profile remains blocked."
            )

        def read_result() -> dict[str, Any]:
            path = root / "result.json"
            if path.stat().st_size > 65536:
                raise ValueError("The diagnostic report exceeded its size limit.")
            return json.loads(path.read_text())

        return await asyncio.to_thread(read_result)
    finally:

        async def cleanup() -> None:
            try:
                if process is not None:
                    await reap(process)
            finally:
                if completion is not None and not completion.done():
                    completion.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await completion
            # Failed reaping deliberately retains the workspace and denies another
            # attempt: native code may still be using those private input files.
            await asyncio.to_thread(shutil.rmtree, root)

        await finish_owned_io(asyncio.create_task(cleanup()))
