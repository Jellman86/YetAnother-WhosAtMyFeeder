"""Own the actual Python interpreter while preserving its virtual environment."""

import os
import sys


def python_subprocess_launch(environment: dict[str, str] | None = None) -> tuple[str, dict[str, str] | None]:
    if sys.platform != "win32":
        return sys.executable, environment
    # Windows venv launchers redirect through an extra process. CPython's hint
    # keeps venv lookup while the returned PID owns the interpreter directly.
    executable = getattr(sys, "_base_executable", None) or sys.executable
    child_environment = dict(os.environ if environment is None else environment)
    child_environment["__PYVENV_LAUNCHER__"] = sys.executable
    return executable, child_environment
