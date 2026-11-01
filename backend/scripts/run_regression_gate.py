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

# The application lane took 297 to 450 s on GitHub-hosted runners across the
# eleven CI runs after the pure lane split off, and one slower runner reached
# 93% of it at 480 s with nothing hung. Ten minutes still stops a real teardown
# hang well inside the job's 20-minute limit.
TEST_TIMEOUT_SECONDS = 600
# Pure tests need no database or app, so they run first in their own process:
# that proves they still do not, and fails fast on a broken decision rule.
PURE_TEST_TIMEOUT_SECONDS = 120


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
    coverage = [sys.executable, "-m", "coverage"]
    commands = [
        ([*coverage, "erase"], 30),
        ([*coverage, "run", "-m", "pytest", "tests/pure", "-q", "--tb=short"], PURE_TEST_TIMEOUT_SECONDS),
        (
            [*coverage, "run", "--append", "-m", "pytest", "tests/", "--ignore=tests/pure"]
            + ["-q", "--tb=short", "--durations=20"],
            TEST_TIMEOUT_SECONDS,
        ),
        ([*coverage, "report"], 30),
    ]
    for command, timeout in commands:
        result = run(command, timeout)
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
