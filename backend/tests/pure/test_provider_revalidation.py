from unittest.mock import ANY, AsyncMock

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
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_gpu"}, provider_guard=ANY)
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


@pytest.mark.asyncio
async def test_runtime_refresh_checks_intel_cpu_before_narrowing_model_choices(environment, monkeypatch):
    from app.services.classifier_service import _apply_host_validated_provider_policy, _provider_capability_contract

    probe, _reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "supported_inference_providers": ["cpu", "intel_cpu"],
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu", "intel_npu"],
    }
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    probe.return_value["eligible_providers"] = ["cpu", "intel_cpu", "intel_gpu"]
    probe.return_value["providers"] = [
        {"provider": provider, "ok": True} for provider in ("cpu", "intel_cpu", "intel_gpu")
    ]
    await recovery.ProviderRevalidation().run()
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_cpu", "intel_gpu"}, provider_guard=ANY)
    resolved = _apply_host_validated_provider_policy(spec, model_id="bird")
    assert "intel_cpu" in resolved["supported_inference_providers"]
    caps = {"ort_available": True, "openvino_available": True, "intel_cpu_available": True, "intel_gpu_available": True}
    contract = _provider_capability_contract(
        caps=caps,
        packaged_providers=("cpu", "intel_cpu", "intel_gpu"),
        supported_providers=resolved["supported_inference_providers"],
        active_backend="openvino",
        active_provider="intel_gpu",
        provider_order=resolved["host_provider_preference_order"],
    )
    assert "intel_cpu" in contract["available_providers"]
    assert "intel_cpu" in contract["provider_preference_order"]


@pytest.mark.asyncio
async def test_failed_intel_cpu_check_does_not_block_passing_accelerator_or_become_eligible(environment, monkeypatch):
    probe, reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
    }
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    probe.return_value["providers"] = [{"provider": "intel_cpu", "ok": False, "finite": False}]
    runner = recovery.ProviderRevalidation()
    await runner.run()
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_cpu", "intel_gpu"}, provider_guard=ANY)
    assert runner.status()["state"] == "succeeded"
    assert "intel_cpu" not in validation.host_eligible_providers("bird", artifact_sha256="abc")
    reload.assert_awaited_once()
    await recovery.ProviderRevalidation().run()
    assert probe.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "packaged,declared,expected",
    [
        (("cpu", "intel_gpu"), ["cpu", "intel_cpu", "intel_gpu"], {"cpu", "intel_gpu"}),
        (("cpu", "intel_cpu", "intel_gpu"), ["cpu", "intel_gpu"], {"cpu", "intel_gpu"}),
        (
            ("cpu", "intel_cpu", "intel_gpu"),
            ["cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"],
            {"cpu", "intel_cpu", "intel_gpu"},
        ),
    ],
)
async def test_startup_checks_only_packaged_declared_cpu_routes_and_selected_accelerator(
    environment, monkeypatch, packaged, declared, expected
):
    probe, _reload = environment
    monkeypatch.setattr(
        recovery,
        "active_configuration",
        lambda: (
            {"model_id": "bird", "artifact_sha256": "abc", "candidate_inference_providers": declared},
            "intel_gpu",
        ),
    )
    monkeypatch.setattr(validation, "packaged_inference_providers", lambda _flavor: packaged)
    await recovery.ProviderRevalidation().run()
    probe.assert_awaited_once_with("bird", only_providers=expected, provider_guard=ANY)


@pytest.mark.asyncio
async def test_new_failed_cpu_probe_overrides_passing_evidence_published_during_check(environment, monkeypatch):
    probe, _reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
    }
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))

    async def probe_with_intervening_pass(*_args, **_kwargs):
        data = validation._read_current_eligibility_payload()
        data["models"]["bird"].append("intel_cpu")
        data["model_provider_signatures"]["bird"]["intel_cpu"] = "new-intel_cpu"
        validation._write_json_atomic(validation._eval_root() / validation.ELIGIBILITY_FILENAME, data)
        assert "intel_cpu" in validation.host_eligible_providers("bird", artifact_sha256="abc")
        return probe.return_value

    probe.side_effect = probe_with_intervening_pass
    probe.return_value["providers"] = [
        {"provider": "cpu", "ok": True},
        {"provider": "intel_cpu", "ok": False},
        {"provider": "intel_gpu", "ok": True},
    ]
    await recovery.ProviderRevalidation().run()
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_cpu", "intel_gpu"}, provider_guard=ANY)
    assert "intel_cpu" not in validation.host_eligible_providers("bird", artifact_sha256="abc")


@pytest.mark.asyncio
async def test_current_intel_cpu_evidence_is_retained_without_extra_native_probe(environment, monkeypatch):
    probe, _reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
    }
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    data = validation._read_current_eligibility_payload()
    data["models"]["bird"].append("intel_cpu")
    data["model_provider_signatures"]["bird"]["intel_cpu"] = "new-intel_cpu"
    validation._write_json_atomic(validation._eval_root() / validation.ELIGIBILITY_FILENAME, data)
    await recovery.ProviderRevalidation().run()
    probe.assert_awaited_once_with("bird", only_providers={"cpu", "intel_gpu"}, provider_guard=ANY)
    assert "intel_cpu" in validation.host_eligible_providers("bird", artifact_sha256="abc")


@pytest.mark.asyncio
async def test_failed_accelerator_still_retains_passing_cpu_routes_without_reloading(environment, monkeypatch):
    probe, reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
    }
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    probe.return_value.update(
        eligible_providers=["cpu", "intel_cpu"],
        providers=[
            {"provider": "cpu", "ok": True},
            {"provider": "intel_cpu", "ok": True},
            {"provider": "intel_gpu", "ok": False},
        ],
    )
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"
    assert set(validation.host_eligible_providers("bird", artifact_sha256="abc")) == {"cpu", "intel_cpu"}
    reload.assert_not_awaited()
    assert validation.read_validation_record("bird") is None
    await recovery.ProviderRevalidation().run()
    assert probe.await_count == 1


@pytest.mark.parametrize("target", ["cpu", "intel_cpu"])
def test_probe_guard_refuses_quarantined_cpu_target_without_mutating_crash_evidence(tmp_path, monkeypatch, target):
    import signal
    from types import SimpleNamespace
    from app.services import classifier_service
    from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError

    profile = {"model_id": "bird", "model_sha256": "abc", "provider": "intel_gpu", "runtime_signature": "current"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path / "incidents")
    policy.record(profile | {"provider": target}, -signal.SIGSEGV)
    evidence = next((tmp_path / "incidents").glob("*.json"))
    before = evidence.read_bytes()
    monkeypatch.setattr(
        classifier_service,
        "get_classifier",
        lambda: SimpleNamespace(_native_launch_profile=lambda: profile, _native_crash_quarantine=policy),
    )
    with pytest.raises(NativeCrashQuarantinedError):
        guard_revalidation_profile({"model_id": "bird", "artifact_sha256": "abc"}, "intel_gpu", target)
    assert evidence.read_bytes() == before


@pytest.mark.asyncio
async def test_malformed_optional_report_does_not_discard_valid_eligibility(environment):
    probe, _reload = environment
    probe.return_value["providers"] = [{}, None, {"provider": "cpu", "ok": True}]
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "succeeded"
    assert "intel_gpu" in validation.host_eligible_providers("bird", artifact_sha256="abc")


@pytest.mark.asyncio
async def test_failed_accelerator_does_not_claim_cpu_results_retained_when_write_fails(environment, monkeypatch):
    probe, _reload = environment
    probe.return_value.update(
        eligible_providers=["cpu"], providers=[{"provider": "cpu", "ok": True}, {"provider": "intel_gpu", "ok": False}]
    )
    monkeypatch.setattr(validation, "write_eligibility_entry", lambda *_args, **_kwargs: None)
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "failed"
    assert "retained" not in runner.status()["reason"]


@pytest.mark.asyncio
async def test_automatic_sweep_never_spawns_quarantined_intel_cpu_probe(environment, tmp_path, monkeypatch):
    import signal
    from types import SimpleNamespace
    from app.services import classifier_service
    from app.services.model_manager import model_manager
    from app.services.native_crash_quarantine import NativeCrashQuarantine

    _mock_sweep, reload = environment
    spec = {
        "model_id": "bird",
        "artifact_sha256": "abc",
        "runtime": "onnx",
        "candidate_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
    }
    profile = {"model_id": "bird", "model_sha256": "abc", "provider": "intel_gpu", "runtime_signature": "current"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path / "incidents")
    policy.record(profile | {"provider": "intel_cpu"}, -signal.SIGSEGV)
    evidence = next((tmp_path / "incidents").glob("*.json"))
    before = evidence.read_bytes()
    monkeypatch.setattr(recovery, "active_configuration", lambda: (spec, "intel_gpu"))
    monkeypatch.setattr(recovery, "guard_revalidation_profile", guard_revalidation_profile)
    monkeypatch.setattr(recovery, "sweep_model_devices", validation.sweep_model_devices)
    monkeypatch.setattr(
        classifier_service,
        "get_classifier",
        lambda: SimpleNamespace(_native_launch_profile=lambda: profile, _native_crash_quarantine=policy),
    )
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
        },
    )
    monkeypatch.setattr(model_manager, "get_active_model_spec", lambda: spec)
    calls = []

    async def probe(provider, **_kwargs):
        calls.append(provider)
        return {
            "compile": {"ok": True},
            "output_summary": {"finite_count": 2, "element_count": 2},
            "per_image_top_indices": [[1, 0]],
            "inference_latency_ms": 10,
        }

    monkeypatch.setattr(validation, "_probe_one_provider", probe)
    runner = recovery.ProviderRevalidation()
    await runner.run()
    assert runner.status()["state"] == "succeeded"
    assert calls == ["cpu", "intel_gpu"]
    assert set(validation.host_eligible_providers("bird", artifact_sha256="abc")) == {"cpu", "intel_gpu"}
    assert evidence.read_bytes() == before
    reload.assert_awaited_once()
