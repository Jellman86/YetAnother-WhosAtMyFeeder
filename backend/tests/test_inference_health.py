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
