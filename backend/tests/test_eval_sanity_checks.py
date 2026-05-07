"""Tests for backend/app/services/eval/sanity_checks.py — pure functions."""
from __future__ import annotations

from app.services.eval import sanity_checks


def test_latency_drift_high_triggers():
    out = sanity_checks.latency_drift({"startup_benchmark_ms": 100, "mean_latency_ms": 600})
    assert out and out["code"] == "latency_drift_high"


def test_latency_drift_within_threshold_silent():
    assert sanity_checks.latency_drift({"startup_benchmark_ms": 100, "mean_latency_ms": 400}) is None


def test_latency_drift_missing_inputs_silent():
    assert sanity_checks.latency_drift({"mean_latency_ms": 500}) is None
    assert sanity_checks.latency_drift({"startup_benchmark_ms": 100}) is None


def test_high_abstention_triggers():
    assert sanity_checks.high_abstention({"abstention_rate": 0.25})["code"] == "high_abstention"


def test_high_abstention_below_threshold_silent():
    assert sanity_checks.high_abstention({"abstention_rate": 0.05}) is None


def test_low_shared_core_triggers():
    out = sanity_checks.low_shared_core({"shared_core_top1": 0.3})
    assert out and out["code"] == "low_shared_core"


def test_low_shared_core_at_threshold_silent():
    assert sanity_checks.low_shared_core({"shared_core_top1": 0.5}) is None


def test_provider_fallback_active_when_cpu_replaces_accelerated():
    out = sanity_checks.provider_fallback({"requested_provider": "openvino", "active_provider": "cpu"})
    assert out and out["code"] == "provider_fallback_active"


def test_provider_fallback_silent_when_match():
    assert sanity_checks.provider_fallback({"requested_provider": "cpu", "active_provider": "cpu"}) is None


def test_incomplete_install_when_not_ready():
    out = sanity_checks.incomplete_install({"ready": False, "ready_reason": "missing labels"})
    assert out and out["code"] == "incomplete_install"


def test_incomplete_install_silent_when_ready():
    assert sanity_checks.incomplete_install({
        "ready": True, "labels_file_present": True, "model_config_present": True
    }) is None


def test_inference_health_unhealthy_triggers():
    assert sanity_checks.inference_health_unhealthy({"inference_health_verdict": "unhealthy"})["code"] == "inference_health_unhealthy"


def test_inference_health_unhealthy_silent_when_healthy():
    assert sanity_checks.inference_health_unhealthy({"inference_health_verdict": "healthy"}) is None


def test_region_mismatch_eu_model_in_us():
    out = sanity_checks.region_mismatch({"model_id": "eu_medium_focalnet_b"}, "US-CA")
    assert out and out["code"] == "region_mismatch"


def test_region_mismatch_na_model_in_uk():
    out = sanity_checks.region_mismatch({"model_id": "small_birds/na"}, "GB")
    assert out and out["code"] == "region_mismatch"


def test_region_mismatch_silent_for_aligned():
    assert sanity_checks.region_mismatch({"model_id": "eu_medium_focalnet_b"}, "GB") is None
    assert sanity_checks.region_mismatch({"model_id": "small_birds/na"}, "US-CA") is None


def test_region_mismatch_silent_when_no_region():
    assert sanity_checks.region_mismatch({"model_id": "eu_medium"}, None) is None


def test_collect_returns_all_applicable_warnings():
    model = {
        "model_id": "eu_medium_focalnet_b",
        "ready": True,
        "labels_file_present": True,
        "model_config_present": True,
        "startup_benchmark_ms": 100,
        "mean_latency_ms": 1000,
        "abstention_rate": 0.5,
        "shared_core_top1": 0.1,
        "active_provider": "cpu",
        "requested_provider": "openvino",
        "inference_health_verdict": "unhealthy",
    }
    warnings = sanity_checks.collect(model, region_label="US-CA")
    codes = {w["code"] for w in warnings}
    assert {
        "latency_drift_high",
        "high_abstention",
        "low_shared_core",
        "provider_fallback_active",
        "inference_health_unhealthy",
        "region_mismatch",
    } <= codes


def test_collect_empty_when_clean():
    model = {
        "model_id": "convnext_large_inat21",
        "ready": True,
        "labels_file_present": True,
        "model_config_present": True,
        "startup_benchmark_ms": 200,
        "mean_latency_ms": 220,
        "abstention_rate": 0.02,
        "shared_core_top1": 0.85,
        "active_provider": "cpu",
        "requested_provider": "cpu",
        "inference_health_verdict": "healthy",
    }
    assert sanity_checks.collect(model, region_label=None) == []
