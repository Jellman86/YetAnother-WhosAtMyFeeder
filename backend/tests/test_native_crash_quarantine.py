import json
import signal

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


@pytest.mark.parametrize("exit_code", [None, 0, 1, -signal.SIGTERM, -signal.SIGKILL])
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


def test_memory_quarantine_precedes_persistence(tmp_path):
    policy = NativeCrashQuarantine(lambda: {"model": "bird"}, root=tmp_path)
    assert policy.remember(policy.guard(), -signal.SIGSEGV)
    assert not list(tmp_path.iterdir())
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()
