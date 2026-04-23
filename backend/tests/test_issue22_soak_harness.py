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
    reconnect_reason: str | None = None,
    event_started: int | None = None,
    event_completed: int | None = None,
    event_dropped: int | None = None,
    event_critical_failures: int | None = 0,
    live_image_admission_timeouts: int | None = 0,
    live_image_abandoned: int | None = 0,
    classify_snapshot_timeouts: int | None = 0,
    classify_snapshot_overloaded: int | None = 0,
    video_pending: int | None = 0,
    video_active: int | None = 0,
    video_failure_count: int | None = 0,
    video_circuit_open: bool | None = False,
) -> SoakSample:
    return SoakSample(
        observed_at=at,
        health_status=status,
        mqtt_pressure_level=pressure,
        mqtt_topic_liveness_reconnects=reconnects,
        mqtt_last_reconnect_reason=reconnect_reason,
        mqtt_frigate_count=frigate_count,
        mqtt_birdnet_count=birdnet_count,
        mqtt_frigate_age_seconds=frigate_age,
        mqtt_birdnet_age_seconds=birdnet_age,
        event_started_count=event_started if event_started is not None else frigate_count,
        event_completed_count=event_completed if event_completed is not None else frigate_count,
        event_dropped_count=event_dropped if event_dropped is not None else 0,
        event_critical_failures=event_critical_failures,
        live_image_admission_timeouts=live_image_admission_timeouts,
        live_image_abandoned=live_image_abandoned,
        classify_snapshot_timeouts=classify_snapshot_timeouts,
        classify_snapshot_overloaded=classify_snapshot_overloaded,
        video_pending_count=video_pending,
        video_active_count=video_active,
        video_failure_count=video_failure_count,
        video_circuit_open=video_circuit_open,
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


def test_evaluate_soak_run_fails_when_event_pipeline_starts_but_never_completes():
    start = datetime(2026, 3, 5, 10, 30, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=100, birdnet_count=200, frigate_age=1.0, birdnet_age=1.0, event_started=50, event_completed=50),
        _sample(start + timedelta(seconds=10), frigate_count=101, birdnet_count=201, frigate_age=1.2, birdnet_age=1.1, event_started=52, event_completed=50),
        _sample(start + timedelta(seconds=20), frigate_count=102, birdnet_count=202, frigate_age=1.1, birdnet_age=1.0, event_started=54, event_completed=50),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["event_started_delta"] == 4
    assert result["event_completed_delta"] == 0
    assert any("completed-events did not advance" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_critical_failures_grow_during_ingress():
    start = datetime(2026, 3, 5, 11, 0, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=200, birdnet_count=300, frigate_age=1.0, birdnet_age=1.0, event_started=120, event_completed=120, event_critical_failures=0),
        _sample(start + timedelta(seconds=10), frigate_count=204, birdnet_count=304, frigate_age=1.1, birdnet_age=1.0, event_started=124, event_completed=122, event_critical_failures=2),
        _sample(start + timedelta(seconds=20), frigate_count=208, birdnet_count=308, frigate_age=1.0, birdnet_age=1.1, event_started=128, event_completed=124, event_critical_failures=4),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["frigate_delta"] == 8
    assert result["birdnet_delta"] == 8
    assert result["event_critical_failures_delta"] == 4
    assert any("critical failures increased" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_live_admission_timeouts_increase():
    start = datetime(2026, 3, 5, 11, 30, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=300, birdnet_count=400, frigate_age=1.0, birdnet_age=1.0, live_image_admission_timeouts=0),
        _sample(start + timedelta(seconds=10), frigate_count=304, birdnet_count=404, frigate_age=1.0, birdnet_age=1.1, live_image_admission_timeouts=2),
        _sample(start + timedelta(seconds=20), frigate_count=308, birdnet_count=408, frigate_age=1.1, birdnet_age=1.0, live_image_admission_timeouts=5),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["live_image_admission_timeouts_delta"] == 5
    assert any("live image admission timeouts increased" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_live_image_abandoned_increases():
    start = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=300, birdnet_count=400, frigate_age=1.0, birdnet_age=1.0, live_image_abandoned=0),
        _sample(start + timedelta(seconds=10), frigate_count=304, birdnet_count=404, frigate_age=1.0, birdnet_age=1.1, live_image_abandoned=2),
        _sample(start + timedelta(seconds=20), frigate_count=308, birdnet_count=408, frigate_age=1.1, birdnet_age=1.0, live_image_abandoned=5),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["live_image_abandoned_delta"] == 5
    assert any("live image abandoned work increased" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_classify_snapshot_drop_reasons_increase():
    start = datetime(2026, 4, 23, 12, 30, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=300, birdnet_count=400, frigate_age=1.0, birdnet_age=1.0, classify_snapshot_timeouts=0, classify_snapshot_overloaded=0),
        _sample(start + timedelta(seconds=10), frigate_count=304, birdnet_count=404, frigate_age=1.0, birdnet_age=1.1, classify_snapshot_timeouts=2, classify_snapshot_overloaded=1),
        _sample(start + timedelta(seconds=20), frigate_count=308, birdnet_count=408, frigate_age=1.1, birdnet_age=1.0, classify_snapshot_timeouts=5, classify_snapshot_overloaded=3),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["classify_snapshot_timeout_delta"] == 5
    assert result["classify_snapshot_overloaded_delta"] == 3
    assert any("classify_snapshot_timeout drops increased" in reason for reason in result["failure_reasons"])
    assert any("classify_snapshot_overloaded drops increased" in reason for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_expected_stall_reconnect_does_not_happen():
    start = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=10, birdnet_count=30, frigate_age=1.0, birdnet_age=1.0, reconnects=0),
        _sample(start + timedelta(seconds=10), frigate_count=10, birdnet_count=31, frigate_age=70.0, birdnet_age=1.0, reconnects=0),
        _sample(start + timedelta(seconds=20), frigate_count=10, birdnet_count=32, frigate_age=80.0, birdnet_age=1.0, reconnects=0),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=0,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=10.0,
        min_topic_liveness_reconnects_delta=1,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["topic_liveness_reconnects_delta"] == 0
    assert any("reconnect" in reason.lower() for reason in result["failure_reasons"])


def test_evaluate_soak_run_fails_when_video_circuit_opens():
    start = datetime(2026, 3, 5, 12, 30, tzinfo=timezone.utc)
    samples = [
        _sample(start + timedelta(seconds=0), frigate_count=20, birdnet_count=40, frigate_age=1.0, birdnet_age=1.0, video_pending=4, video_failure_count=0, video_circuit_open=False),
        _sample(start + timedelta(seconds=10), frigate_count=21, birdnet_count=41, frigate_age=1.0, birdnet_age=1.0, video_pending=18, video_failure_count=2, video_circuit_open=True),
        _sample(start + timedelta(seconds=20), frigate_count=22, birdnet_count=42, frigate_age=1.0, birdnet_age=1.0, video_pending=12, video_failure_count=3, video_circuit_open=False),
    ]
    thresholds = SoakThresholds(
        min_samples=3,
        min_frigate_messages_delta=2,
        min_birdnet_messages_delta=2,
        max_degraded_ratio=1.0,
        max_pressure_level="critical",
        frigate_stall_age_seconds=60.0,
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=20.0,
        allow_video_circuit_open=False,
        max_video_pending=10,
        max_video_failure_count_delta=0,
    )

    result = evaluate_soak_run(samples, thresholds)

    assert result["passed"] is False
    assert result["video_circuit_open_observed"] is True
    assert result["video_failure_count_delta"] == 3
    assert any("video" in reason.lower() for reason in result["failure_reasons"])
