from app.services.error_diagnostics import ErrorDiagnosticsHistory


def test_ring_buffer_evicts_oldest_and_keeps_newest_first():
    history = ErrorDiagnosticsHistory(max_events=3)

    history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="drop_a",
        message="Drop A",
        severity="warning",
    )
    history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="drop_b",
        message="Drop B",
        severity="error",
    )
    history.record(
        source="notification_dispatcher",
        component="dispatcher",
        reason_code="queue_full",
        message="Queue full",
        severity="critical",
    )
    history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="drop_c",
        message="Drop C",
        severity="warning",
    )

    snapshot = history.snapshot(limit=10)
    assert snapshot["total_events"] == 3
    assert snapshot["returned_events"] == 3
    assert [event["reason_code"] for event in snapshot["events"]] == ["drop_c", "queue_full", "drop_b"]


def test_snapshot_supports_filters_and_summary_counters():
    history = ErrorDiagnosticsHistory(max_events=10)

    history.record(
        source="event_pipeline",
        component="event_processor",
        stage="classify_snapshot",
        reason_code="stage_timeout",
        message="Stage timed out",
        severity="error",
        event_id="evt-1",
        context={"timeout_seconds": 30},
    )
    history.record(
        source="event_pipeline",
        component="event_processor",
        stage="save_and_notify",
        reason_code="stage_failure",
        message="Stage failed",
        severity="critical",
        event_id="evt-2",
    )
    history.record(
        source="notification_dispatcher",
        component="notification_dispatcher",
        reason_code="job_timeout",
        message="Notification timed out",
        severity="error",
    )

    filtered = history.snapshot(limit=5, component="event_processor", severity="error")

    assert filtered["capacity"] == 10
    assert filtered["total_events"] == 3
    assert filtered["returned_events"] == 1
    assert filtered["severity_counts"] == {"error": 1}
    assert filtered["component_counts"] == {"event_processor": 1}
    assert len(filtered["events"]) == 1
    assert filtered["events"][0]["event_id"] == "evt-1"


def test_snapshot_preserves_distinct_overload_reason_codes():
    history = ErrorDiagnosticsHistory(max_events=10)

    history.record(
        source="event_pipeline",
        component="event_processor",
        stage="classify_snapshot",
        reason_code="drop_classify_snapshot_overloaded",
        message="Dropped event due to classify_snapshot_overloaded",
        severity="warning",
        event_id="evt-overload-1",
        context={"stage": "classify_snapshot"},
    )
    history.record(
        source="event_pipeline",
        component="event_processor",
        stage="classify_snapshot",
        reason_code="stage_timeout",
        message="Stage classify_snapshot timed out after 30s",
        severity="error",
        event_id="evt-timeout-1",
    )

    snapshot = history.snapshot(limit=10, component="event_processor")

    assert [event["reason_code"] for event in snapshot["events"]] == [
        "stage_timeout",
        "drop_classify_snapshot_overloaded",
    ]
