"""The same bounded, fail-closed backend gate for local runs, PRs and images."""

import os
from pathlib import Path
import signal
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.utils.python_subprocess import python_subprocess_launch  # noqa: E402

TEST_TIMEOUT_SECONDS = 480


def run(command: list[str], timeout: int) -> int:
    executable, environment = python_subprocess_launch()
    if command[0] == sys.executable:
        command = [executable, *command[1:]]
    process = subprocess.Popen(command, cwd=BACKEND, env=environment, start_new_session=os.name == "posix")
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # A printed pytest summary is not successful process exit: leaked workers
        # and teardown hangs must stop an image from being published.
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
        print(f"Regression gate timed out after {timeout}s: {command}", file=sys.stderr)
        return 124


def main() -> int:
    commands = [
        ([sys.executable, "-m", "coverage", "erase"], 30),
        (
            [sys.executable, "-m", "coverage", "run", "-m", "pytest", "tests/", "-q", "--tb=short", "--durations=20"],
            TEST_TIMEOUT_SECONDS,
        ),
        ([sys.executable, "-m", "coverage", "report"], 30),
    ]
    for command, timeout in commands:
        result = run(command, timeout)
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
