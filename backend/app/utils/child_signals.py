"""Signal asyncio child processes without stealing their exit status.

Before Python 3.13, asyncio's ``Process.kill()`` and ``Process.terminate()``
go through ``subprocess.Popen.send_signal``, which first polls the child with
``waitpid(WNOHANG)``. If the child has already died but the event loop has not
collected it yet, that poll reaps it, and the loop's child watcher then reports
exit status 255. A native SIGSEGV or SIGABRT would be recorded as an ordinary
exit and escape quarantine. The event loop must stay the only reaper, so the
child is inspected without being collected (``WNOWAIT``) and only a child that
is still running is signalled.
"""

import asyncio
import os
import signal
from typing import Any

# Windows has neither waitid nor reaping; its Process.kill is already safe.
_CAN_SIGNAL_WITHOUT_REAPING = hasattr(os, "waitid")


def kill_child(process: Any) -> None:
    _signal_child(process, kill=True)


def terminate_child(process: Any) -> None:
    _signal_child(process, kill=False)


def _signal_child(process: Any, *, kill: bool) -> None:
    """Raises ProcessLookupError, as Process.kill does, if the child vanished."""
    if process.returncode is not None:
        return
    if not (_CAN_SIGNAL_WITHOUT_REAPING and isinstance(process, asyncio.subprocess.Process)):
        if kill:
            process.kill()
        else:
            process.terminate()
        return
    try:
        exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        # Already collected; the loop is about to publish the status. The pid
        # may belong to an unrelated process by now, so it must not be signalled.
        return
    if exited is None:
        os.kill(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
