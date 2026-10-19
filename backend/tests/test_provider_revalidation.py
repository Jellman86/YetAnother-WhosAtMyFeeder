from unittest.mock import AsyncMock

import pytest

from app.services import provider_revalidation as recovery
from app.services import model_validation as validation
from app.services.provider_revalidation import guard_revalidation_profile


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    spec = {"model_id": "bird", "artifact_sha256": "abc"}
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"old-{provider}")
    validation.write_eligibility_entry("bird", ["cpu", "intel_gpu"], image_flavor="intel", artifact_sha256="abc")
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: f"new-{provider}")
    probe = AsyncMock(
        return_value={
            "eligible_providers": ["cpu", "intel_gpu"],
            "providers": [],
            "image_flavor": "intel",
            "artifact_sha256": "abc",
        }
    )
    monkeypatch.setattr(recovery, "sweep_model_devices", probe)
    reload = AsyncMock()
    monkeypatch.setattr(recovery, "reload_active_classifier", reload)
    monkeypatch.setattr(recovery, "guard_revalidation_profile", lambda *_args: None)
    return probe, reload


@pytest.mark.asyncio
async def test_stale_accelerator_is_revalidated_once_and_reloaded(environment):
    probe, reload = environment
    runner = recovery.ProviderRevalidation()
    await runner.run()
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_gpu"})
    reload.assert_awaited_once()
    assert runner.status()["state"] == "succeeded"
    assert "intel_gpu" in validation.host_eligible_providers("bird", artifact_sha256="abc")
    await recovery.ProviderRevalidation().run()
    assert probe.await_count == 1


@pytest.mark.asyncio
async def test_failed_revalidation_does_not_loop_after_restart(environment):
    probe, reload = environment
    probe.return_value["eligible_providers"] = ["cpu"]
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"
    await recovery.ProviderRevalidation().run()
    assert probe.await_count == 1
    reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_revalidation_never_publishes_after_model_changes(environment, monkeypatch):
    probe, reload = environment

    async def changed(*args, **kwargs):
        monkeypatch.setattr(recovery, "active_configuration", lambda: ({"model_id": "other"}, "intel_gpu"))
        return {"eligible_providers": ["intel_gpu"], "providers": []}

    probe.side_effect = changed
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "superseded"
    assert validation.host_eligible_providers("bird", artifact_sha256="abc") == []
    reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_unproven_provider_is_never_automatically_validated(environment, monkeypatch):
    probe, reload = environment
    monkeypatch.setattr(
        recovery, "active_configuration", lambda: ({"model_id": "bird", "artifact_sha256": "abc"}, "intel_npu")
    )
    await recovery.ProviderRevalidation().run()
    probe.assert_not_awaited()
    reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_recovery_calls_share_one_attempt(environment):
    import asyncio

    probe, reload = environment
    runner = recovery.ProviderRevalidation()
    await asyncio.gather(runner.run(), runner.run())
    assert probe.await_count == 1
    assert reload.await_count == 1


@pytest.mark.asyncio
async def test_cancelled_recovery_records_interruption_without_retry(environment):
    import asyncio

    probe, reload = environment
    probe.side_effect = asyncio.CancelledError
    runner = recovery.ProviderRevalidation()
    with pytest.raises(asyncio.CancelledError):
        await runner.run()
    assert runner.status()["state"] == "interrupted"
    await recovery.ProviderRevalidation().run()
    assert probe.await_count == 1
    reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_does_not_discard_other_current_provider_evidence(environment, monkeypatch):
    probe, reload = environment
    data = validation._read_current_eligibility_payload()
    data["models"]["bird"].append("intel_npu")
    data["model_provider_signatures"]["bird"]["intel_npu"] = "new-intel_npu"
    validation._write_json_atomic(validation._eval_root() / validation.ELIGIBILITY_FILENAME, data)
    await recovery.ProviderRevalidation().run()
    assert set(validation.host_eligible_providers("bird", artifact_sha256="abc")) == {"cpu", "intel_gpu", "intel_npu"}


@pytest.mark.asyncio
async def test_automatic_revalidation_never_probes_a_legacy_quarantined_profile(environment, tmp_path, monkeypatch):
    import signal
    from app.services.native_crash_quarantine import NativeCrashQuarantine

    probe, reload = environment
    legacy = {"model_id": "bird", "model_sha256": "abc", "provider": "intel_gpu", "runtime_signature": "old"}
    profile = legacy | {"runtime_signature": "driver-aware", "legacy_runtime_signature": "old"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path / "incidents")
    policy.record(legacy, -signal.SIGSEGV)
    evidence_path = next((tmp_path / "incidents").glob("*.json"))
    evidence = evidence_path.read_bytes()
    from types import SimpleNamespace
    from app.services import classifier_service

    classifier = SimpleNamespace(_native_launch_profile=lambda: profile, _native_crash_quarantine=policy)
    monkeypatch.setattr(classifier_service, "get_classifier", lambda: classifier)
    monkeypatch.setattr(recovery, "guard_revalidation_profile", guard_revalidation_profile)
    runner = recovery.ProviderRevalidation()
    await runner.run()
    probe.assert_not_awaited()
    reload.assert_not_awaited()
    assert "quarantin" in runner.status()["reason"].lower()
    assert evidence_path.read_bytes() == evidence
    assert not (tmp_path / "provider_revalidation.json").exists()


@pytest.mark.parametrize("change", [{"model_id": "other"}, {"model_sha256": "other"}, {"provider": "intel_npu"}])
def test_revalidation_guard_rejects_a_different_active_profile(monkeypatch, change):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services import classifier_service

    profile = {"model_id": "bird", "model_sha256": "abc", "provider": "intel_gpu"} | change
    policy = Mock()
    classifier = SimpleNamespace(_native_launch_profile=lambda: profile, _native_crash_quarantine=policy)
    monkeypatch.setattr(classifier_service, "get_classifier", lambda: classifier)
    with pytest.raises(recovery._RevalidationProfileChanged):
        recovery.guard_revalidation_profile({"model_id": "bird", "artifact_sha256": "abc"}, "intel_gpu")
    policy.guard.assert_not_called()


def test_revalidation_guard_uses_real_legacy_quarantine_evidence(monkeypatch, tmp_path):
    import signal
    from types import SimpleNamespace
    from app.services import classifier_service
    from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError

    legacy = {"model_id": "bird", "model_sha256": "abc", "provider": "auto", "runtime_signature": "old"}
    current = legacy | {"runtime_signature": "bound-driver", "legacy_runtime_signature": "old"}
    policy = NativeCrashQuarantine(lambda: current, root=tmp_path)
    policy.record(legacy, -signal.SIGSEGV)
    classifier = SimpleNamespace(_native_launch_profile=lambda: current, _native_crash_quarantine=policy)
    monkeypatch.setattr(classifier_service, "get_classifier", lambda: classifier)
    with pytest.raises(NativeCrashQuarantinedError):
        recovery.guard_revalidation_profile({"model_id": "bird", "artifact_sha256": "abc"}, "auto")


@pytest.mark.asyncio
async def test_profile_change_before_revalidation_does_not_probe_or_consume_attempt(environment, monkeypatch, tmp_path):
    probe, reload = environment

    def changed(*_args):
        raise recovery._RevalidationProfileChanged()

    monkeypatch.setattr(recovery, "guard_revalidation_profile", changed)
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "superseded"
    probe.assert_not_awaited()
    reload.assert_not_awaited()
    assert not (tmp_path / "provider_revalidation.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("requested", ["intel_gpu", "auto"])
async def test_unblocked_matching_profile_can_still_be_automatically_revalidated(
    environment, monkeypatch, tmp_path, requested
):
    from types import SimpleNamespace
    from app.services import classifier_service
    from app.services.native_crash_quarantine import NativeCrashQuarantine

    probe, reload = environment
    spec = {"model_id": "bird", "artifact_sha256": "abc"}
    profile = {"model_id": "bird", "model_sha256": "abc", "provider": requested, "runtime_signature": "new"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path / "incidents")
    classifier = SimpleNamespace(_native_launch_profile=lambda: profile, _native_crash_quarantine=policy)
    monkeypatch.setattr(classifier_service, "get_classifier", lambda: classifier)
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, requested))
    monkeypatch.setattr(recovery, "guard_revalidation_profile", guard_revalidation_profile)
    if requested == "auto":
        monkeypatch.setattr(validation, "read_validation_record", lambda *_args: {"provider": "intel_gpu"})
    runner = recovery.ProviderRevalidation()
    await runner.run()
    probe.assert_awaited_once()
    reload.assert_awaited_once()
    assert runner.status()["state"] == "succeeded"
