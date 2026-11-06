"""Unit tests for the per-host model validation record and selection gate.

These are pure: they exercise the eligibility/validation resolver against a temp
eval directory with no live models, network, or classifier.
"""

import json
import pytest

from app.services import model_validation as mv


def _write_eligibility(base, models: dict):
    for model_id, providers in models.items():
        mv.write_eligibility_entry(
            model_id,
            providers,
            run_id="r1",
            image_flavor=mv.get_image_flavor(),
        )


def test_unvalidated_model_is_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    ok, reason = mv.is_model_validated("eva02_large_inat21", active_model_id="rope_vit", bundled_ids=set())
    assert ok is False
    assert reason == "unvalidated"


def test_active_model_is_grandfathered(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    ok, reason = mv.is_model_validated("rope_vit", active_model_id="rope_vit", bundled_ids=set())
    assert ok is True
    assert reason == "active"


def test_bundled_model_is_always_eligible(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    ok, reason = mv.is_model_validated(
        "mobilenet_v2_birds", active_model_id="rope_vit", bundled_ids={"mobilenet_v2_birds"}
    )
    assert ok is True
    assert reason == "bundled"


def test_device_sweep_eligibility_clears_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    _write_eligibility(tmp_path, {"small_birds": ["intel_cpu", "intel_gpu"]})
    ok, reason = mv.is_model_validated("small_birds", active_model_id="rope_vit", bundled_ids=set())
    assert ok is True
    assert reason == "device_sweep"


def test_empty_eligibility_list_does_not_clear_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    _write_eligibility(tmp_path, {"small_birds": []})
    ok, reason = mv.is_model_validated("small_birds", active_model_id="rope_vit", bundled_ids=set())
    assert ok is False


def test_eligibility_from_a_different_image_flavor_cannot_clear_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cuda")
    (tmp_path / "device_eligibility.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "models": {"small_birds": ["cpu"]},
                "model_image_flavors": {"small_birds": "intel"},
            }
        ),
        encoding="utf-8",
    )

    ok, reason = mv.is_model_validated("small_birds", active_model_id="rope_vit", bundled_ids=set())

    assert ok is False
    assert reason == "unvalidated"


def test_legacy_eligibility_requires_revalidation_inside_a_published_image(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cuda")
    (tmp_path / "device_eligibility.json").write_text(
        json.dumps({"models": {"small_birds": ["cpu", "cuda"]}}),
        encoding="utf-8",
    )

    assert mv.host_eligible_providers("small_birds") == []


def test_probe_record_from_a_different_image_flavor_cannot_clear_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    mv.write_validation_record("small_birds", provider="cpu", ok=True, reason="old image")
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cuda")

    ok, reason = mv.is_model_validated("small_birds", active_model_id="rope_vit", bundled_ids=set())

    assert ok is False
    assert reason == "unvalidated"


def test_probe_record_clears_gate_on_any_host(tmp_path, monkeypatch):
    """Unknown development environments can still use the fallback probe record."""
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_validation_record("convnext_large_inat21", provider="cpu", ok=True, reason="probe ok")
    ok, reason = mv.is_model_validated("convnext_large_inat21", active_model_id="rope_vit", bundled_ids=set())
    assert ok is True
    assert reason == "probe"


def test_activation_recommendation_uses_current_eligible_order(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cuda")
    mv.write_eligibility_entry("small_birds", ["cpu", "cuda"], image_flavor="cuda")
    mv.write_validation_record("small_birds", provider="cuda", ok=True, reason="fastest")

    assert mv.activation_provider_recommendation("small_birds") == "cuda"

    mv.write_eligibility_entry("small_birds", ["cpu"], image_flavor="cuda")
    assert mv.activation_provider_recommendation("small_birds") == "cpu"


def test_failed_probe_record_does_not_clear_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_validation_record("convnext_large_inat21", provider="cpu", ok=False, reason="NaN output")
    ok, reason = mv.is_model_validated("convnext_large_inat21", active_model_id="rope_vit", bundled_ids=set())
    assert ok is False


def test_write_then_read_record_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_validation_record("small_birds", provider="intel_gpu", ok=True, reason="finite output")
    rec = mv.read_validation_record("small_birds")
    assert rec is not None
    assert rec["validated"] is True
    assert rec["provider"] == "intel_gpu"
    assert rec["reason"] == "finite output"
    assert rec["checked_at"]


def test_writing_one_record_preserves_others(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_validation_record("small_birds", provider="cpu", ok=True, reason="ok")
    mv.write_validation_record("medium_birds", provider="cpu", ok=False, reason="crash")
    assert mv.read_validation_record("small_birds")["validated"] is True
    assert mv.read_validation_record("medium_birds")["validated"] is False


def test_writing_provider_eligibility_preserves_other_models_and_records_image(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))

    mv.write_eligibility_entry("small_birds", ["cpu", "cuda"], run_id="r1", image_flavor="cuda")
    mv.write_eligibility_entry("medium_birds", ["cpu"], run_id="r2", image_flavor="cuda")

    payload = json.loads((tmp_path / "device_eligibility.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 4
    assert payload["image_flavor"] == "cuda"
    assert payload["run_id"] == "r2"
    assert payload["models"] == {"small_birds": ["cpu", "cuda"], "medium_birds": ["cpu"]}
    assert payload["model_image_flavors"] == {"small_birds": "cuda", "medium_birds": "cuda"}
    assert set(payload["model_runtime_signatures"]) == {"small_birds", "medium_birds"}
    assert mv.host_eligibility_summary() == {
        "verified_providers": ["cpu", "cuda"],
        "generated_at": payload["generated_at"],
        "run_id": "r2",
        "model_count": 2,
    }


def test_runtime_or_model_artifact_change_invalidates_provider_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    mv.write_eligibility_entry(
        "convnext_large_inat21",
        ["intel_gpu", "intel_cpu"],
        image_flavor="intel",
        artifact_sha256="abc123",
    )

    assert mv.host_eligible_providers(
        "convnext_large_inat21",
        artifact_sha256="abc123",
    ) == ["intel_gpu", "intel_cpu"]
    assert (
        mv.host_eligible_providers(
            "convnext_large_inat21",
            artifact_sha256="replacement",
        )
        == []
    )

    monkeypatch.setenv("YAWAMF_INFERENCE_RUNTIME_ID", "replacement-runtime")
    assert (
        mv.host_eligible_providers(
            "convnext_large_inat21",
            artifact_sha256="abc123",
        )
        == []
    )


def test_provider_preference_uses_current_measured_latency_over_stale_recommendation(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("YAWAMF_IMAGE_FLAVOR", raising=False)
    mv.write_eligibility_entry(
        "convnext_large_inat21",
        ["intel_cpu", "intel_gpu", "intel_npu"],
        image_flavor="unknown",
        provider_results=[
            {"provider": "intel_cpu", "ok": True, "latency_ms": 510.0},
            {"provider": "intel_gpu", "ok": True, "latency_ms": 360.0},
            {"provider": "intel_npu", "ok": True, "latency_ms": 140.0},
        ],
    )
    mv.write_validation_record(
        "convnext_large_inat21",
        provider="intel_cpu",
        ok=True,
        reason="stale recommendation",
    )

    assert mv.host_provider_preference_order("convnext_large_inat21") == [
        "intel_npu",
        "intel_gpu",
        "intel_cpu",
    ]


def test_missing_files_fail_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    assert mv.read_validation_record("nope") is None
    assert mv.host_eligible_providers("nope") == []


def test_corrupt_eligibility_file_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    (tmp_path / "device_eligibility.json").write_text("{not json", encoding="utf-8")
    assert mv.host_eligible_providers("small_birds") == []
    ok, reason = mv.is_model_validated("small_birds", active_model_id="x", bundled_ids=set())
    assert ok is False


def test_unrelated_runtime_update_preserves_intel_gpu_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "full")
    signatures = {"intel_gpu": "intel-v1", "cuda": "cuda-v1"}
    monkeypatch.setattr(mv, "current_provider_runtime_signature", lambda provider: signatures[provider])
    mv.write_eligibility_entry("bird", ["intel_gpu", "cuda"], image_flavor="full", artifact_sha256="abc")
    signatures["cuda"] = "cuda-v2"
    monkeypatch.setattr(mv, "current_inference_runtime_signature", lambda: "changed-global-runtime")
    assert mv.host_eligible_providers("bird", artifact_sha256="abc") == ["intel_gpu"]
    assert mv.host_eligibility_summary()["verified_providers"] == ["intel_gpu"]


def test_model_replacement_still_invalidates_provider_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_eligibility_entry("bird", ["intel_gpu"], image_flavor=mv.get_image_flavor(), artifact_sha256="old")
    assert mv.host_eligible_providers("bird", artifact_sha256="new") == []


def test_provider_signature_ignores_unrelated_runtime_packages(monkeypatch):
    versions = {p: "1.0" for p in mv._INFERENCE_RUNTIME_PACKAGES}
    monkeypatch.setattr(mv.importlib_metadata, "version", lambda p: versions[p])
    mv._provider_runtime_signature_for.cache_clear()
    before = mv.current_provider_runtime_signature("intel_gpu")
    versions["onnxruntime-gpu"] = "2.0"
    mv._provider_runtime_signature_for.cache_clear()
    assert mv.current_provider_runtime_signature("intel_gpu") == before
    versions["openvino"] = "2.0"
    mv._provider_runtime_signature_for.cache_clear()
    assert mv.current_provider_runtime_signature("intel_gpu") != before
    mv._provider_runtime_signature_for.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("probe", [mv._probe_one_provider, mv._probe_one_crop_provider])
async def test_cancelled_probe_reaps_a_child_that_exits_during_cancellation(monkeypatch, probe):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    process = SimpleNamespace(
        returncode=None,
        kill=Mock(side_effect=ProcessLookupError),
        communicate=AsyncMock(side_effect=[asyncio.CancelledError(), (b"", None)]),
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(asyncio.CancelledError):
        await probe("intel_gpu", model_id="test")
    assert process.communicate.await_count == 2


def test_runtime_identity_changes_with_bound_driver_without_module_versions(tmp_path, monkeypatch):
    device = tmp_path / "class/drm/card0/device"
    device.mkdir(parents=True)
    drivers = tmp_path / "bus/pci/drivers"
    for name in ("i915", "xe"):
        (drivers / name).mkdir(parents=True)
    binding = device / "driver"
    binding.symlink_to(drivers / "i915")
    original = mv._bound_device_drivers
    monkeypatch.setattr(mv, "_bound_device_drivers", lambda: original(tmp_path))
    before = mv._runtime_identity("intel", "")
    binding.unlink()
    binding.symlink_to(drivers / "xe")
    after = mv._runtime_identity("intel", "")

    assert before["device_drivers"] == {"class/drm/card0/device": "i915"}
    assert after["device_drivers"] == {"class/drm/card0/device": "xe"}
    assert mv._identity_digest(before) != mv._identity_digest(after)
    assert mv._runtime_identity("intel", "") == after


def test_bound_device_drivers_keep_missing_or_broken_binding_unknown(tmp_path):
    for category, name in (("drm", "card0"), ("accel", "accel0")):
        device = tmp_path / "class" / category / name / "device"
        device.mkdir(parents=True)
        (device / "driver").symlink_to(tmp_path / "missing-driver")

    assert mv._bound_device_drivers(tmp_path) == {
        "class/drm/card0/device": None,
        "class/accel/accel0/device": None,
    }


def test_bound_device_drivers_handles_inaccessible_binding(tmp_path, monkeypatch):
    from pathlib import Path

    device = tmp_path / "class/drm/card0/device"
    device.mkdir(parents=True)
    monkeypatch.setattr(Path, "resolve", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))

    assert mv._bound_device_drivers(tmp_path) == {"class/drm/card0/device": None}


def test_legacy_signature_matches_identity_before_driver_binding_was_recorded(monkeypatch):
    identity = mv._runtime_identity("intel", "test-abi")
    old_identity = {key: value for key, value in identity.items() if key != "device_drivers"}
    monkeypatch.setattr(mv, "_runtime_identity", lambda *args: dict(identity))
    mv._legacy_runtime_signature_for.cache_clear()
    try:
        assert mv._legacy_runtime_signature_for("intel", "test-abi") == mv._identity_digest(old_identity)
    finally:
        mv._legacy_runtime_signature_for.cache_clear()


def test_provider_evidence_expires_when_bound_driver_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    bindings = {"class/drm/card0/device": "i915"}
    monkeypatch.setattr(mv, "_bound_device_drivers", lambda: dict(bindings))
    mv._provider_runtime_signature_for.cache_clear()
    try:
        mv.write_eligibility_entry("bird", ["intel_gpu"], artifact_sha256="abc")
        assert mv.host_eligible_providers("bird", artifact_sha256="abc") == ["intel_gpu"]
        bindings["class/drm/card0/device"] = "xe"
        mv._provider_runtime_signature_for.cache_clear()
        assert mv.host_eligible_providers("bird", artifact_sha256="abc") == []
    finally:
        mv._provider_runtime_signature_for.cache_clear()


@pytest.mark.parametrize("provider", ["cpu", "intel_cpu", "cuda", "intel_npu"])
def test_gpu_driver_binding_does_not_expire_unrelated_provider_evidence(monkeypatch, provider):
    bindings = {"class/drm/card0/device": "i915", "class/accel/accel0/device": "intel_vpu"}
    monkeypatch.setattr(mv, "_bound_device_drivers", lambda: dict(bindings))
    mv._provider_runtime_signature_for.cache_clear()
    try:
        before = mv.current_provider_runtime_signature(provider)
        bindings["class/drm/card0/device"] = "xe"
        mv._provider_runtime_signature_for.cache_clear()
        assert mv.current_provider_runtime_signature(provider) == before
    finally:
        mv._provider_runtime_signature_for.cache_clear()


def test_bound_device_drivers_ignore_display_connectors(tmp_path):
    for name in ("card1", "card1-DP-1", "card1-HDMI-A-1"):
        (tmp_path / "class/drm" / name / "device").mkdir(parents=True)

    assert mv._bound_device_drivers(tmp_path) == {"class/drm/card1/device": None}
