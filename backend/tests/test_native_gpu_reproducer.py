import json
import signal

import pytest

from scripts.reproduce_native_gpu_crash import child_environment, classify_outcome, run_child


@pytest.mark.parametrize(
    ("code", "report", "timeout", "expected"),
    [
        (0, {"phase": "complete", "ok": True}, False, "passed"),
        (0, {"phase": "compile", "ok": True}, False, "incomplete"),
        (0, {}, False, "incomplete"),
        (-signal.SIGSEGV, {"phase": "compile"}, False, "native_crash"),
        (1, {"phase": "error"}, False, "failed"),
        (-signal.SIGKILL, {}, True, "timeout"),
    ],
)
def test_only_complete_clean_child_exit_passes(code, report, timeout, expected):
    assert classify_outcome(code, report, timed_out=timeout) == expected


def test_child_environment_does_not_inherit_credentials_or_production_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("YA_WAMF_API_KEY", "secret")
    monkeypatch.setenv("OPENVINO_CACHE_DIR", "/production/cache")
    environment = child_environment(tmp_path)
    assert "YA_WAMF_API_KEY" not in environment
    assert "OPENVINO_CACHE_DIR" not in environment
    assert "HOME" not in environment
    assert environment["XDG_CACHE_HOME"] == str(tmp_path / "driver-cache")


def test_runner_retains_incomplete_report_and_log(tmp_path):
    import sys

    report = tmp_path / "report.json"
    command = [sys.executable, "-c", f"import json;open({str(report)!r},'w').write(json.dumps({{'phase':'compile'}}))"]
    result = run_child(command, tmp_path, report, timeout=5)
    assert result["outcome"] == "incomplete"
    assert result["report"]["phase"] == "compile"
    assert json.loads(report.read_text()) == {"phase": "compile"}


def test_timeout_is_bounded_and_not_a_native_crash(tmp_path):
    import sys

    result = run_child(
        [sys.executable, "-c", "import time;time.sleep(30)"], tmp_path, tmp_path / "report.json", timeout=0.1
    )
    assert result["outcome"] == "timeout"
