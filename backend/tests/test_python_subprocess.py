import os
import sys

import pytest

from app.utils.python_subprocess import python_subprocess_launch


@pytest.mark.parametrize("restricted", [False, True])
def test_windows_launch_owns_base_interpreter_and_preserves_the_child_environment(monkeypatch, restricted):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\venv\Scripts\python.exe")
    monkeypatch.setattr(sys, "_base_executable", r"C:\Python312\python.exe")
    monkeypatch.setenv("UNRELATED_SECRET", "private")
    provided = {"PATH": "test", "CLASSIFICATION__INFERENCE_PROVIDER": "cpu"} if restricted else None
    executable, environment = python_subprocess_launch(provided)
    assert executable == sys._base_executable
    assert environment["__PYVENV_LAUNCHER__"] == sys.executable
    if restricted:
        assert "UNRELATED_SECRET" not in environment
        assert provided == {"PATH": "test", "CLASSIFICATION__INFERENCE_PROVIDER": "cpu"}
    else:
        assert environment["UNRELATED_SECRET"] == "private"
    assert "__PYVENV_LAUNCHER__" not in os.environ


def test_non_windows_launch_keeps_executable_and_explicit_environment(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    provided = {"PATH": "test"}
    assert python_subprocess_launch(provided) == (sys.executable, provided)
    assert python_subprocess_launch() == (sys.executable, None)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows virtual environment launcher ownership")
def test_native_windows_child_pid_and_venv_match_the_owned_interpreter():
    import json
    import subprocess

    executable, environment = python_subprocess_launch()
    command = "import json,os,sys;print(json.dumps({'pid':os.getpid(),'prefix':sys.prefix}))"
    with subprocess.Popen([executable, "-c", command], env=environment, stdout=subprocess.PIPE) as child:
        stdout, _ = child.communicate(timeout=5)
        report = json.loads(stdout)
        assert child.returncode == 0
        assert report["pid"] == child.pid
        assert report["prefix"] == sys.prefix
