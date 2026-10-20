import signal

import pytest

from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError


@pytest.fixture
def blocked(tmp_path):
    legacy = {"model_id": "bird", "provider": "intel_gpu", "runtime_signature": "old"}
    current = legacy | {"runtime_signature": "bound-driver", "legacy_runtime_signature": "old"}
    policy = NativeCrashQuarantine(lambda: current, root=tmp_path)
    policy.record(legacy, -signal.SIGSEGV)
    return policy, current, legacy, tmp_path


def test_exact_profile_approval_preserves_incidents_and_does_not_release_legacy_alias_for_other_profiles(blocked):
    policy, current, legacy, root = blocked
    evidence = {path.name: path.read_bytes() for path in root.glob("*.json")}
    token = policy.capture_revalidation(current)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(current)
    assert policy.release_after_revalidation(current, token)
    assert policy.guard(current) == current
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(current | {"runtime_signature": "different-driver"})
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(legacy)
    assert {path.name: path.read_bytes() for path in root.glob("*.json")} == evidence


def test_new_in_memory_fault_invalidates_approval_before_persistence(blocked):
    policy, current, _, _ = blocked
    token = policy.capture_revalidation(current)
    assert policy.release_after_revalidation(current, token)
    policy.remember(current, -signal.SIGSEGV)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(current)
    assert not policy.release_after_revalidation(current, token)


def test_incident_recorded_during_probe_prevents_release(blocked):
    policy, current, _, _ = blocked
    token = policy.capture_revalidation(current)
    policy.record_retirement(current, "device_lost", "fixture")
    assert not policy.release_after_revalidation(current, token)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(current)


def test_release_requires_matching_profile_and_restart_requires_new_owner_check(blocked):
    policy, current, _, root = blocked
    token = policy.capture_revalidation(current)
    assert not policy.release_after_revalidation(current | {"model_id": "other"}, token)
    assert policy.release_after_revalidation(current, token)
    restarted = NativeCrashQuarantine(lambda: current, root=root)
    with pytest.raises(NativeCrashQuarantinedError):
        restarted.guard()


def test_unblocked_profile_cannot_start_revalidation(tmp_path):
    profile = {"model_id": "bird", "provider": "cpu"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    with pytest.raises(ValueError, match="not quarantined"):
        policy.capture_revalidation(profile)


def test_auxiliary_weights_change_invalidates_approval_and_preserves_earlier_negative_alias(blocked):
    policy, current, legacy, _ = blocked
    original_key = policy._key(current)
    expanded = current | {
        "auxiliary_artifacts": {"crop": {"fast": {"weights": "one"}}},
        "legacy_profile_keys": [original_key, policy._key(legacy)],
    }
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(expanded)
    token = policy.capture_revalidation(expanded)
    assert policy.release_after_revalidation(expanded, token)
    changed = expanded | {"auxiliary_artifacts": {"crop": {"fast": {"weights": "two"}}}}
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(changed)
    assert policy.worker_approval(changed) is None
