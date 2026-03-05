from datetime import datetime, timedelta, timezone

from app.utils.issue22_soak_harness import SoakSample, SoakThresholds, evaluate_soak_run


def _sample(
    at: datetime,
    *,
    status: str = "ok",
    frigate_count: int,
    birdnet_count: int,
    frigate_age: float | None,
    birdnet_age: float | None,
    pressure: str = "normal",
    reconnects: int = 0,
) -> SoakSample:
    return SoakSample(
        observed_at=at,
        health_status=status,
        mqtt_pressure_level=pressure,
        mqtt_topic_liveness_reconnects=reconnects,
        mqtt_frigate_count=frigate_count,
        mqtt_birdnet_count=birdnet_count,
        mqtt_frigate_age_seconds=frigate_age,
        mqtt_birdnet_age_seconds=birdnet_age,
    )


def test_evaluate_soak_run_passes_for_healthy_stream():
    start = datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=10, birdnet_count=100, frigate_age=0.5, birdnet_age=0.2),
        _sample(start + timedelta(seconds=10), frigate_count=12, birdnet_count=102, frigate_age=0.6, birdnet_age=0.3),
        _sample(start + timedelta(seconds=20), frigate_count=14, birdnet_count=104, frigate_age=0.7, birdnet_age=0.4),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=0.5,
        max_pressure_level="high",
        frigate_stall_age_seconds=45.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is True
    assert result["stall_incidents"] == []
    assert result["frigate_delta"] == 4
    assert result["birdnet_delta"] == 4


def test_evaluate_soak_run_fails_when_frigate_stalls_while_birdnet_advances():
    start = datetime(2026, 3, 5, 9, 30, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=50, birdnet_count=200, frigate_age=2.0, birdnet_age=1.0),
        _sample(start + timedelta(seconds=10), frigate_count=50, birdnet_count=201, frigate_age=70.0, birdnet_age=1.0),
        _sample(start + timedelta(seconds=20), frigate_count=50, birdnet_count=202, frigate_age=80.0, birdnet_age=1.1),
        _sample(start + timedelta(seconds=30), frigate_count=50, birdnet_count=203, frigate_age=95.0, birdnet_age=1.2),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=0,
        min_birdnet_messages_delta=1,
        max_degraded_ratio=0.5,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert len(result["stall_incidents"]) == 1
    assert any("frigate stream stalled" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_pressure_exceeds_limit():
    start = datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=1, birdnet_count=1, frigate_age=1.0, birdnet_age=1.0, pressure="normal"),
        _sample(start + timedelta(seconds=10), frigate_count=2, birdnet_count=2, frigate_age=1.0, birdnet_age=1.0, pressure="critical"),
    ]
    thresholds = SoakThresholds(
        min_samples=2,
        min_frigate_messages_delta=1,
        min_birdnet_messages_delta=1,
        max_degraded_ratio=1.0,
        max_pressure_level="high",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert any("pressure level exceeded" in reason.lower() for reason in result["failure_reasons"])
