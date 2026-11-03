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


def expanded_profile():
    base = {"model_id": "bird", "provider": "intel_gpu", "runtime_signature": "runtime", "model_sha256": "weights"}
    return base | {
        "auxiliary_artifacts": {"crop": {"fast": {"weights": "one"}}},
        "video_frames": 15,
        "legacy_profile_keys": [NativeCrashQuarantine._key(base)],
    }


@pytest.mark.parametrize("retirement", [False, True])
@pytest.mark.parametrize("persist", [False, True])
@pytest.mark.parametrize(
    "change", [{"video_frames": 14}, {"auxiliary_artifacts": {"crop": {"fast": {"weights": "two"}}}}]
)
def test_auxiliary_changes_cannot_release_new_negative_evidence(tmp_path, retirement, persist, change):
    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    if retirement:
        if persist:
            policy.record_retirement(profile, "CL_OUT_OF_RESOURCES", "fixture")
        else:
            policy.remember_retirement(profile)
    elif persist:
        policy.record(profile, -signal.SIGSEGV)
    else:
        policy.remember(profile, -signal.SIGSEGV)
    changed = profile | change
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(changed)
    if persist:
        with pytest.raises(NativeCrashQuarantinedError):
            NativeCrashQuarantine(lambda: changed, root=tmp_path).guard()


@pytest.mark.parametrize("retirement", [False, True])
def test_pre_fix_expanded_records_remain_blocking_without_rewriting_them(tmp_path, retirement):
    profile = expanded_profile()
    old_key = NativeCrashQuarantine._key(profile)
    # Reproduce the old on-disk format, with no stable-base alias.
    record = {"profile": profile, "exit_code": None if retirement else -signal.SIGSEGV}
    if retirement:
        record["retirement"] = {"error_code": "CL_OUT_OF_RESOURCES", "detail": "fixture"}
    import json

    path = tmp_path / f"{old_key}.json"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    changed = profile | {"video_frames": 14}
    policy = NativeCrashQuarantine(lambda: changed, root=tmp_path)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
    assert policy.guard(changed | {"provider": "cpu"})
    assert policy.guard(changed | {"model_sha256": "other"})


def test_approval_covers_only_full_profile_and_sibling_fault_revokes_it(tmp_path):
    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    token = policy.capture_revalidation(profile)
    assert policy.release_after_revalidation(profile, token)
    assert policy.guard(profile)
    approval = policy.worker_approval(profile)
    changed = profile | {"video_frames": 14}
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(changed)
    assert policy.worker_approval(changed) is None
    with pytest.raises(NativeCrashQuarantinedError):
        NativeCrashQuarantine(lambda: changed, root=tmp_path, inherited_approval=approval).guard()
    policy.remember_retirement(changed)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(profile)
    assert not policy.release_after_revalidation(profile, token)


def test_new_legacy_expanded_file_invalidates_cached_lookup(tmp_path):
    import json

    profile = expanded_profile()
    changed = profile | {"video_frames": 14}
    policy = NativeCrashQuarantine(lambda: changed, root=tmp_path)
    assert policy.guard()
    (tmp_path / f"{policy._key(profile)}.json").write_text(
        json.dumps({"profile": profile, "exit_code": -signal.SIGSEGV})
    )
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()


def test_a_sibling_incident_keeps_the_original_full_profile_record(tmp_path):
    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    path = tmp_path / f"{policy._key(profile)}.json"
    original = path.read_bytes()
    policy.record_retirement(profile | {"video_frames": 14}, "CL_OUT_OF_RESOURCES", "new fixture incident")
    assert path.read_bytes() == original


@pytest.mark.parametrize("content", ["broken json", "{}", "x" * 65537])
def test_unidentifiable_old_evidence_fails_closed_without_echoing_it(tmp_path, content):
    profile = expanded_profile()
    (tmp_path / ("a" * 64 + ".json")).write_text(content)
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    with pytest.raises(NativeCrashQuarantinedError, match="could not be verified"):
        policy.guard()
    assert policy.worker_approval(profile) is None


def test_legacy_lookup_does_not_trust_a_recent_coarse_directory_timestamp(tmp_path, monkeypatch):
    import json
    import time

    profile = expanded_profile()
    changed = profile | {"video_frames": 14}
    policy = NativeCrashQuarantine(lambda: changed, root=tmp_path)
    stamp = time.time_ns()
    monkeypatch.setattr(policy, "_directory_identity", lambda: (1, 2, stamp, stamp))
    assert policy.guard()
    (tmp_path / f"{policy._key(profile)}.json").write_text(
        json.dumps({"profile": profile, "exit_code": -signal.SIGSEGV})
    )
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()


def test_legacy_index_io_does_not_delay_remembering_a_new_fault(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time
    from pathlib import Path

    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    entered, release = threading.Event(), threading.Event()
    original_open = Path.open

    def slow_open(path, *args, **kwargs):
        if path.parent == tmp_path and args == ("rb",):
            entered.set()
            assert release.wait(3)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", slow_open)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(policy.guard)
        try:
            assert entered.wait(3)
            started = time.monotonic()
            assert policy.remember_retirement(profile | {"video_frames": 14})
            assert time.monotonic() - started < 0.5
        finally:
            release.set()
        with pytest.raises(NativeCrashQuarantinedError):
            future.result(timeout=3)


def test_incident_directory_change_during_owner_check_requires_a_fresh_check(tmp_path):
    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    token = policy.capture_revalidation(profile)
    other = profile | {"model_id": "other"}
    policy.record(other, -signal.SIGSEGV)
    assert not policy.release_after_revalidation(profile, token)
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()


def test_in_place_corruption_of_a_cached_legacy_record_fails_closed(tmp_path, monkeypatch):
    import json

    profile = expanded_profile()
    changed = profile | {"video_frames": 14}
    path = tmp_path / f"{NativeCrashQuarantine._key(profile)}.json"
    path.write_text(json.dumps({"profile": profile, "exit_code": -signal.SIGSEGV}))
    policy = NativeCrashQuarantine(lambda: changed, root=tmp_path)
    monkeypatch.setattr(policy, "_directory_identity", lambda: (1, 2, 3, 4))
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard()
    path.write_text("corrupt")
    with pytest.raises(ValueError, match="could not be verified"):
        policy.capture_revalidation(changed)


def test_an_excessive_legacy_index_fails_closed(tmp_path, monkeypatch):
    import json
    from app.services import native_crash_quarantine as module

    profile = expanded_profile()
    monkeypatch.setattr(module, "_MAX_INCIDENT_FILES", 2)
    for number in range(3):
        old = profile | {"model_id": f"fixture-{number}"}
        (tmp_path / f"{NativeCrashQuarantine._key(old)}.json").write_text(json.dumps({"profile": old}))
    with pytest.raises(NativeCrashQuarantinedError, match="could not be verified"):
        NativeCrashQuarantine(lambda: profile, root=tmp_path).guard()


@pytest.mark.parametrize("change", [{"provider": "cpu"}, {"model_id": "other"}, {"model_sha256": "other"}])
def test_gpu_negative_aliases_cannot_follow_a_different_primary_profile(tmp_path, change):
    profile = expanded_profile()
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    # CPU recovery and provider validation override fields in a captured source
    # profile; its old alias metadata must not carry the GPU block with it.
    other = profile | change
    assert policy.guard(other) == other
    assert NativeCrashQuarantine(lambda: other, root=tmp_path).guard() == other
