"""Unit tests for the per-host model validation record and selection gate.

These are pure: they exercise the eligibility/validation resolver against a temp
eval directory with no live models, network, or classifier.
"""

import json

from app.services import model_validation as mv


def _write_eligibility(base, models: dict):
    (base / "device_eligibility.json").write_text(
        json.dumps({"generated_at": "2026-07-17T00:00:00Z", "run_id": "r1", "models": models}),
        encoding="utf-8",
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


def test_probe_record_clears_gate_on_any_host(tmp_path, monkeypatch):
    """A CPU-only or CUDA host has no device_eligibility.json entry; the host-agnostic
    probe record is what clears the gate there."""
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    mv.write_validation_record("convnext_large_inat21", provider="cpu", ok=True, reason="probe ok")
    ok, reason = mv.is_model_validated("convnext_large_inat21", active_model_id="rope_vit", bundled_ids=set())
    assert ok is True
    assert reason == "probe"


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
