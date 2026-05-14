import time

from app.services.inference_health import InferenceHealth, RuntimeKey


def test_inference_health_records_success_latency_and_snapshot():
    health = InferenceHealth(min_samples=2, window_size=4)
    key = RuntimeKey("openvino", "intel_gpu", "eu_medium_focalnet_b")

    health.record(key, outcome="ok", latency_seconds=0.25)
    health.record(key, outcome="ok", latency_seconds=0.5)

    snapshot = health.snapshot()
    runtime = snapshot["runtimes"]["openvino/intel_gpu/eu_medium_focalnet_b"]

    assert health.verdict(key) == "healthy"
    assert runtime["verdict"] == "healthy"
    assert runtime["samples"] == 2
    assert runtime["recent_failures"] == 0
    assert runtime["latency_seconds"]["p50"] == 0.375
    assert runtime["latency_seconds"]["p95"] == 0.5


def test_inference_health_marks_unhealthy_after_repeated_failures_and_cooldown():
    health = InferenceHealth(
        min_samples=3,
        window_size=8,
        unhealthy_error_rate=0.5,
        cooldown_seconds=30.0,
    )
    key = RuntimeKey("openvino", "intel_gpu", "eu_medium_focalnet_b")

    health.record(key, outcome="ok", latency_seconds=0.2)
    health.record(key, outcome="timeout", latency_seconds=None)
    health.record(key, outcome="lease_expired", latency_seconds=None)

    snapshot = health.snapshot()
    runtime = snapshot["runtimes"]["openvino/intel_gpu/eu_medium_focalnet_b"]

    assert health.verdict(key) == "unhealthy"
    assert health.cooldown_remaining(key) > 0
    assert runtime["verdict"] == "unhealthy"
    assert runtime["recent_failures"] == 2
    assert runtime["last_outcome"] == "lease_expired"
    assert runtime["cooldown_remaining_seconds"] > 0
    assert runtime["first_recorded_at"] <= time.time()


def test_inference_health_uses_baseline_latency_for_degraded_and_unhealthy_verdicts():
    health = InferenceHealth(
        min_samples=2,
        degraded_latency_multiplier=2.0,
        unhealthy_latency_multiplier=5.0,
    )
    key = RuntimeKey("openvino", "intel_gpu", "eu_medium_focalnet_b")

    health.set_baseline(key, p95_latency_seconds=1.0)
    health.record(key, outcome="ok", latency_seconds=2.5)
    health.record(key, outcome="ok", latency_seconds=3.0)

    assert health.verdict(key) == "degraded"

    health.record(key, outcome="ok", latency_seconds=5.5)
    health.record(key, outcome="ok", latency_seconds=6.0)

    assert health.verdict(key) == "unhealthy"


def test_inference_health_ignores_load_affected_latency_for_verdicts():
    health = InferenceHealth(
        min_samples=2,
        degraded_latency_multiplier=2.0,
        unhealthy_latency_multiplier=5.0,
    )
    key = RuntimeKey("openvino", "intel_gpu", "eu_medium_focalnet_b")

    health.set_baseline(key, p95_latency_seconds=1.0)
    health.record(key, outcome="ok", latency_seconds=6.0, latency_health_eligible=False)
    health.record(key, outcome="ok", latency_seconds=7.0, latency_health_eligible=False)

    snapshot = health.snapshot()
    runtime = snapshot["runtimes"]["openvino/intel_gpu/eu_medium_focalnet_b"]

    assert health.verdict(key) == "healthy"
    assert runtime["latency_seconds"]["p95"] == 7.0
    assert runtime["latency_health_samples"] == 0
    assert runtime["load_affected_latency_samples"] == 2


def test_record_recovery_attaches_context_to_runtime_and_snapshot():
    health = InferenceHealth()
    key = RuntimeKey("openvino", "intel_gpu", "eu_medium_focalnet_b")

    health.record_recovery(
        key,
        {
            "status": "recovered",
            "failed_backend": "openvino",
            "failed_provider": "intel_gpu",
            "recovered_backend": "openvino",
            "recovered_provider": "intel_cpu",
            "detail": "GPU went unhealthy; fell back to CPU",
            "reason": "gpu_unhealthy_fallback",
        },
    )

    snapshot = health.snapshot()
    runtime = snapshot["runtimes"]["openvino/intel_gpu/eu_medium_focalnet_b"]

    assert runtime["last_recovery"]["status"] == "recovered"
    assert runtime["last_recovery"]["reason"] == "gpu_unhealthy_fallback"
    assert isinstance(runtime["last_recovery"]["at"], float)
    assert snapshot["last_recovery"] is not None
    assert snapshot["last_recovery"]["recovered_provider"] == "intel_cpu"

    direct = health.last_recovery(key)
    assert direct is not None
    assert direct["failed_provider"] == "intel_gpu"


def test_record_recovery_replaces_previous_context_and_picks_newest_across_runtimes():
    health = InferenceHealth()
    gpu_key = RuntimeKey("openvino", "intel_gpu", "model_a")
    cpu_key = RuntimeKey("onnxruntime", "cpu", "model_a")

    health.record_recovery(gpu_key, {"status": "recovered", "detail": "first", "at": 100.0})
    health.record_recovery(gpu_key, {"status": "failed", "detail": "second", "at": 200.0})

    assert health.last_recovery(gpu_key)["detail"] == "second"
    assert health.last_recovery(gpu_key)["status"] == "failed"

    health.record_recovery(cpu_key, {"status": "recovered", "detail": "cpu", "at": 300.0})
    assert health.snapshot()["last_recovery"]["detail"] == "cpu"

    assert health.most_recent_recovery()["detail"] == "cpu"


def test_record_recovery_no_op_for_none_payload():
    health = InferenceHealth()
    key = RuntimeKey("openvino", "intel_gpu", "model_a")
    health.record_recovery(key, None)
    assert health.last_recovery(key) is None
    assert health.snapshot()["last_recovery"] is None


def test_record_recovery_stamps_at_when_missing():
    health = InferenceHealth()
    key = RuntimeKey("openvino", "intel_gpu", "model_a")
    before = time.time()
    health.record_recovery(key, {"status": "recovered"})
    after = time.time()
    rec = health.last_recovery(key)
    assert rec is not None
    assert before <= rec["at"] <= after


def test_record_recovery_returns_deep_copies():
    health = InferenceHealth()
    key = RuntimeKey("openvino", "intel_gpu", "model_a")
    payload = {"status": "recovered", "diagnostics": {"k": "v"}}
    health.record_recovery(key, payload)

    snapshot_copy = health.last_recovery(key)
    snapshot_copy["diagnostics"]["k"] = "mutated"
    assert health.last_recovery(key)["diagnostics"]["k"] == "v"
