import asyncio
import os
import signal
import sys
import threading
import time

import pytest

from app.utils.child_signals import kill_child, terminate_child

pytestmark = pytest.mark.skipif(not hasattr(os, "waitid"), reason="POSIX child status contract")

_ABORT_AT_ONCE = (
    "import os,resource,signal; resource.setrlimit(resource.RLIMIT_CORE,(0,0)); os.kill(os.getpid(),signal.SIGABRT)"
)


def _hold_back_the_event_loop_reaper(monkeypatch) -> threading.Event:
    """asyncio's child watcher, threaded or pidfd, collects the exit status
    with a blocking os.waitpid(pid, 0). Gating that call reproduces, every
    time, the window in which the child has died but the loop has not yet
    collected it: the window a cleanup signal can land in."""
    release = threading.Event()
    real_waitpid = os.waitpid

    def gated_waitpid(pid: int, options: int):
        if options == 0:
            release.wait(10)
        return real_waitpid(pid, options)

    monkeypatch.setattr(os, "waitpid", gated_waitpid)
    return release


def _block_until_exited_unreaped(pid: int) -> None:
    deadline = time.monotonic() + 10
    while os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
        assert time.monotonic() < deadline, "child never exited"
        time.sleep(0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", [kill_child, terminate_child])
async def test_cleanup_signal_after_a_native_fault_keeps_the_real_exit_status(monkeypatch, stop):
    release = _hold_back_the_event_loop_reaper(monkeypatch)
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", _ABORT_AT_ONCE)
    try:
        _block_until_exited_unreaped(process.pid)
        assert process.returncode is None

        stop(process)

        release.set()
        assert await asyncio.wait_for(process.wait(), 10) == -signal.SIGABRT
    finally:
        release.set()
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize(("stop", "expected"), [(kill_child, -signal.SIGKILL), (terminate_child, -signal.SIGTERM)])
async def test_cleanup_signal_reaches_a_running_child(stop, expected):
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(30)")
    try:
        stop(process)
        assert await asyncio.wait_for(process.wait(), 10) == expected
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.asyncio
async def test_cleanup_signal_is_a_no_op_once_the_exit_is_collected():
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
    assert await asyncio.wait_for(process.wait(), 10) == 0

    kill_child(process)
    terminate_child(process)

    assert process.returncode == 0


class _ProcessDouble:
    returncode = None

    def __init__(self) -> None:
        self.calls: list[str] = []

    def kill(self) -> None:
        self.calls.append("kill")

    def terminate(self) -> None:
        self.calls.append("terminate")


def test_cleanup_signal_delegates_to_a_process_double():
    process = _ProcessDouble()

    kill_child(process)
    terminate_child(process)

    assert process.calls == ["kill", "terminate"]
