import json
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError, artifact_digest


def test_native_crash_survives_new_policy_instance_and_blocks_only_same_profile(tmp_path):
    profile = {"model": "birds/eu", "provider": "intel_gpu", "runtime": "test-runtime"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    assert policy.guard() == profile
    assert policy.record(profile, -signal.SIGSEGV)
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: profile, root=tmp_path).guard()
    for change in ({"provider": "intel_npu"}, {"model": "birds/na"}, {"runtime": "new-runtime"}):
        assert NativeCrashQuarantine(lambda: profile | change, root=tmp_path).guard() == profile | change


@pytest.mark.parametrize("exit_code", [None, 0, 1, -signal.SIGTERM, -9])
def test_normal_errors_shutdown_and_oom_signals_do_not_claim_native_crashes(tmp_path, exit_code):
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    assert not policy.record(policy.guard(), exit_code)
    assert not list(tmp_path.glob("*.json"))


def test_corrupt_record_does_not_silently_unblock_the_profile(tmp_path):
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    profile = policy.guard()
    policy.record(profile, -signal.SIGABRT)
    path = next(tmp_path.glob("*.json"))
    path.write_text("broken json")
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: profile, root=tmp_path).guard()


def test_persistence_failure_still_blocks_current_supervisor(tmp_path, monkeypatch):
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    profile = policy.guard()
    monkeypatch.setattr(policy, "_persist", lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    assert policy.record(profile, -signal.SIGSEGV)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()


def test_evidence_contains_only_profile_and_signal_not_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PRIVATE_TOKEN", "must-not-appear")
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    policy.record(policy.guard(), -signal.SIGSEGV)
    content = next(tmp_path.glob("*.json")).read_text()
    assert "must-not-appear" not in content
    assert json.loads(content)["exit_code"] == -signal.SIGSEGV


def test_artifact_identity_changes_with_weights_not_path_or_timestamp(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_bytes(b"weights")
    second.write_bytes(b"weights")
    assert artifact_digest(str(first)) == artifact_digest(str(second))
    first.write_bytes(b"updated")
    assert artifact_digest(str(first)) != artifact_digest(str(second))
    assert artifact_digest(str(tmp_path / "missing")) is None


@pytest.mark.parametrize("replacement", [False, True])
def test_artifact_digest_does_not_reuse_coarse_timestamps_for_changed_weights(tmp_path, monkeypatch, replacement):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"weights")
    timestamp = time.time_ns() if not replacement else time.time_ns() - 10_000_000_000
    original_stat = Path.stat

    def coarse_stat(candidate, *args, **kwargs):
        stat = original_stat(candidate, *args, **kwargs)
        if candidate != path:
            return stat
        return SimpleNamespace(
            st_mode=stat.st_mode,
            st_size=stat.st_size,
            st_mtime_ns=timestamp,
            st_ctime_ns=timestamp,
            st_ino=stat.st_ino,
            st_dev=stat.st_dev,
        )

    monkeypatch.setattr(Path, "stat", coarse_stat)
    before = artifact_digest(str(path))
    if replacement:
        updated = tmp_path / "updated"
        updated.write_bytes(b"updated")
        updated.replace(path)
    else:
        path.write_bytes(b"updated")

    assert artifact_digest(str(path)) != before


def test_memory_quarantine_precedes_persistence(tmp_path):
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    assert policy.remember(policy.guard(), -signal.SIGSEGV)
    assert not list(tmp_path.iterdir())
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()


def test_native_signal_is_batched_as_sanitized_deduplicated_health_telemetry(tmp_path, monkeypatch):
    from app.services import error_diagnostics
    from app.services.telemetry_service import build_health_issue_report

    history = error_diagnostics.ErrorDiagnosticsHistory()
    monkeypatch.setattr(error_diagnostics, "error_diagnostics_history", history)
    profile = {"model_id": "only-model", "provider": "intel_gpu", "private_path": "secret"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    for _ in range(3):
        policy.record(profile, -signal.SIGSEGV)
    report = build_health_issue_report(
        installation_id="test", app_version="test", diagnostics_snapshot=history.snapshot()
    )
    assert len(report["issues"]) == 1
    assert report["issues"][0]["count"] == 1
    assert report["issues"][0]["sample_context"]["error_type"] == "SIGSEGV"
    assert report["issues"][0]["sample_context"]["configured_provider"] == "intel_gpu"
    assert "active_provider" not in report["issues"][0]["sample_context"]
    assert "secret" not in json.dumps(report)


@pytest.mark.parametrize("exit_code", [0xC0000005, -1073741819])
def test_windows_native_fault_blocks_the_exact_profile_and_reports_its_status(tmp_path, monkeypatch, exit_code):
    import app.services.native_crash_quarantine as module
    from app.services import error_diagnostics

    monkeypatch.setattr(module.sys, "platform", "win32")
    history = error_diagnostics.ErrorDiagnosticsHistory()
    monkeypatch.setattr(error_diagnostics, "error_diagnostics_history", history)
    profile = {"model_id": "bird", "provider": "cuda"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    assert policy.record(profile, exit_code)
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: profile, root=tmp_path).guard()
    assert "STATUS_ACCESS_VIOLATION" in json.dumps(history.snapshot())


@pytest.mark.parametrize("exit_code", [1, 0xC000013A, 0xC0000017, 0xDEADBEEF])
def test_windows_normal_shutdown_oom_and_unknown_status_do_not_claim_native_faults(tmp_path, monkeypatch, exit_code):
    import app.services.native_crash_quarantine as module

    monkeypatch.setattr(module.sys, "platform", "win32")
    policy = NativeCrashQuarantine(lambda: {"model_id": "bird"}, root=tmp_path)
    assert not policy.record(policy.guard(), exit_code)


def test_settled_unchanged_weights_reuse_the_hash_cache(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import app.services.native_crash_quarantine as module

    path = tmp_path / "settled.onnx"
    path.write_bytes(b"weights")
    monkeypatch.setattr(module, "time", SimpleNamespace(time_ns=lambda: time.time_ns() + 3_000_000_000))
    hashing = Mock(wraps=module._hash_artifact_file)
    monkeypatch.setattr(module, "_hash_artifact_file", hashing)
    digests = [artifact_digest(str(path)) for _ in range(10)]
    assert len(set(digests)) == 1
    hashing.assert_called_once_with(path)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTSTATUS exit-code handling")
def test_native_windows_synthetic_fault_exit_is_retained_and_blocks_restart(tmp_path):
    import subprocess
    from app.utils.python_subprocess import python_subprocess_launch

    executable, environment = python_subprocess_launch()
    # A synthetic status exercises supervision without causing a driver fault.
    child = subprocess.run(
        [executable, "-c", "import ctypes;ctypes.windll.kernel32.ExitProcess(0xC0000005)"],
        env=environment,
        timeout=5,
    )
    assert child.returncode == 0xC0000005
    profile = {"model_id": "synthetic", "provider": "cuda"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    assert policy.record(profile, child.returncode)
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: profile, root=tmp_path).guard()
