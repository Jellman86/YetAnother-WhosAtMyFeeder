"""Process-wide clocks and sleeps that a test may patch but must put back.

`monkeypatch.setattr("app.x.time.time", ...)` replaces `time.time` for the
whole process, not for `app.x`. When two patches of the same attribute are
undone in the wrong order, the fake clock outlives its test, and an unrelated
test much later fails or hangs on a timestamp from 2023.
"""

import asyncio
import time
from collections.abc import Callable

PROCESS_GLOBALS: dict[str, tuple[object, str]] = {
    "time.time": (time, "time"),
    "time.monotonic": (time, "monotonic"),
    "time.perf_counter": (time, "perf_counter"),
    "time.sleep": (time, "sleep"),
    "asyncio.sleep": (asyncio, "sleep"),
}


def snapshot() -> dict[str, Callable[..., object]]:
    return {name: getattr(owner, attribute) for name, (owner, attribute) in PROCESS_GLOBALS.items()}


def restore_leaked(originals: dict[str, Callable[..., object]]) -> list[str]:
    """Put back every global that no longer matches `originals` and name what was leaked."""
    leaked = []
    for name, (owner, attribute) in PROCESS_GLOBALS.items():
        if getattr(owner, attribute) is not originals[name]:
            setattr(owner, attribute, originals[name])
            leaked.append(name)
    return leaked
