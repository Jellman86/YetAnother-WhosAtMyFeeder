"""Keep tests discoverable and release enforcement aligned with PR checks."""

import importlib.util
import configparser
from pathlib import Path
import subprocess
from unittest.mock import MagicMock

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("regression_gate", ROOT / "backend/scripts/run_regression_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_root_python_tests_cannot_silently_escape_the_backend_gate():
    orphaned = list((ROOT / "tests").rglob("test_*.py"))
    assert not orphaned, f"Move Python regressions into backend/tests: {orphaned}"


def test_pr_and_publish_use_the_same_gate_without_coverage_overrides():
    for filename in ("ci.yml", "build-and-push.yml"):
        content = (ROOT / ".github/workflows" / filename).read_text()
        workflow = yaml.safe_load(content)
        runs = [step.get("run", "") for job in workflow["jobs"].values() for step in job.get("steps", [])]
        assert sum("python scripts/run_regression_gate.py" in command for command in runs) == 1
        assert "--fail-under=" not in content


def test_telemetry_pr_gate_runs_tests_not_just_build():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["telemetry-worker"]["steps"]
    assert any(step.get("run") == "npm test" for step in steps)


def test_branch_coverage_floor_cannot_be_accidentally_weakened():
    config = configparser.ConfigParser()
    config.read(ROOT / "backend/.coveragerc")
    assert config.getboolean("run", "branch")
    assert config.getfloat("report", "fail_under") >= 70


@pytest.mark.parametrize("returncode", [1, 124, -9])
@pytest.mark.parametrize("failing_lane", [1, 2], ids=["pure", "application"])
def test_failed_or_timed_out_tests_do_not_get_rescued_by_coverage(monkeypatch, returncode, failing_lane):
    run = MagicMock(side_effect=[0] * failing_lane + [returncode])
    monkeypatch.setattr(gate, "run", run)
    assert gate.main() == returncode
    assert run.call_count == failing_lane + 1


def test_coverage_failure_is_not_ignored(monkeypatch):
    monkeypatch.setattr(gate, "run", MagicMock(side_effect=[0, 0, 0, 2]))
    assert gate.main() == 2


def test_pure_tests_run_alone_and_every_test_is_covered_once(monkeypatch):
    run = MagicMock(return_value=0)
    monkeypatch.setattr(gate, "run", run)
    assert gate.main() == 0
    pure, application = (call.args[0] for call in run.call_args_list[1:3])
    assert pure[pure.index("pytest") + 1 :][0] == "tests/pure"
    assert "--append" not in pure
    assert "--append" in application
    assert {"tests/", "--ignore=tests/pure"} <= set(application)


def test_hung_test_process_is_reaped_and_fails(monkeypatch):
    process = MagicMock(pid=12345)
    process.wait.side_effect = [subprocess.TimeoutExpired("pytest", 1), -9]
    monkeypatch.setattr(gate.subprocess, "Popen", MagicMock(return_value=process))
    kill = MagicMock()
    monkeypatch.setattr(gate.os, "killpg", kill, raising=False)
    assert gate.run(["pytest"], 1) == 124
    assert process.wait.call_count == 2
    if gate.os.name == "posix":
        kill.assert_called_once_with(12345, gate.signal.SIGKILL)
    else:
        process.kill.assert_called_once()


def test_the_application_lane_deadline_stays_inside_the_ci_job_limit():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job_seconds = workflow["jobs"]["backend"]["timeout-minutes"] * 60
    # Installation, migration checks and the pure lane run before the application lane.
    assert gate.PURE_TEST_TIMEOUT_SECONDS + gate.TEST_TIMEOUT_SECONDS <= job_seconds - 5 * 60
