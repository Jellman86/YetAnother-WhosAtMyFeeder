"""An owner-approved isolated launch never becomes permission to retry in the API process."""

import signal

import pytest

from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError


PROFILE = {"model_id": "bird", "provider": "intel_gpu", "model_sha256": "weights"}


def approved(tmp_path):
    policy = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path)
    policy.record(PROFILE, -signal.SIGABRT)
    token = policy.capture_revalidation(PROFILE)
    assert policy.release_after_revalidation(PROFILE, token)
    return policy


def test_only_a_fresh_owner_approval_can_authorize_the_matching_worker(tmp_path):
    parent = approved(tmp_path)
    evidence = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    approval = parent.worker_approval(PROFILE)
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: PROFILE, root=tmp_path).guard()
    worker = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path, inherited_approval=approval)
    assert worker.guard() == PROFILE
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == evidence


def test_an_isolated_approval_does_not_authorize_api_process_native_fallback(tmp_path):
    parent = approved(tmp_path)
    assert parent.guard() == PROFILE
    with pytest.raises(NativeCrashQuarantinedError):
        parent.guard_in_process()


def test_new_child_incident_revokes_inherited_authority_even_without_persistence(tmp_path):
    parent = approved(tmp_path)
    worker = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path, inherited_approval=parent.worker_approval(PROFILE))
    worker.guard()
    worker.remember(PROFILE, -signal.SIGABRT)
    with pytest.raises(NativeCrashQuarantinedError):
        worker.guard()
    with pytest.raises(NativeCrashQuarantinedError):
        worker.guard()


def test_saved_evidence_changed_before_worker_launch_stays_blocking(tmp_path):
    parent = approved(tmp_path)
    approval = parent.worker_approval(PROFILE)
    parent.record(PROFILE, -signal.SIGABRT)
    worker = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path, inherited_approval=approval)
    with pytest.raises(NativeCrashQuarantinedError):
        worker.guard()
    assert parent.worker_approval(PROFILE) is None


def test_another_profiles_fault_cannot_reuse_inherited_authority(tmp_path):
    parent = approved(tmp_path)
    other = PROFILE | {"model_sha256": "other-weights"}
    parent.record(other, -signal.SIGABRT)
    worker = NativeCrashQuarantine(lambda: other, root=tmp_path, inherited_approval=parent.worker_approval(PROFILE))
    with pytest.raises(NativeCrashQuarantinedError):
        worker.guard()
