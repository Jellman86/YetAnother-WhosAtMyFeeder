from app.services.telemetry_service import build_health_issue_report


def test_health_issue_report_groups_and_sanitizes_diagnostics():
    snapshot = {
        "captured_at": "2026-05-03T18:00:00+00:00",
        "total_events": 3,
        "returned_events": 3,
        "severity_counts": {"error": 2, "info": 1},
        "component_counts": {"video_classifier": 2, "startup": 1},
        "events": [
            {
                "timestamp": "2026-05-03T17:55:00+00:00",
                "source": "backend",
                "component": "video_classifier",
                "stage": "classify",
                "reason_code": "video_timeout",
                "message": "Timed out on /media/frigate/front/event-123.mp4",
                "severity": "error",
                "event_id": "event-123",
                "context": {
                    "event_id": "event-123",
                    "clip_path": "/media/frigate/front/event-123.mp4",
                    "camera": "front",
                    "configured_provider": "intel_gpu",
                    "active_provider": "cpu",
                    "timeout_seconds": 180,
                    "queue_depth": 4,
                    "freeform_error": "contains raw path /config/media/file.jpg",
                },
            },
            {
                "timestamp": "2026-05-03T17:56:00+00:00",
                "source": "backend",
                "component": "video_classifier",
                "stage": "classify",
                "reason_code": "video_timeout",
                "message": "Timed out on another event",
                "severity": "warning",
                "context": {
                    "configured_provider": "intel_gpu",
                    "active_provider": "cpu",
                    "timeout_seconds": 180,
                },
            },
            {
                "timestamp": "2026-05-03T17:57:00+00:00",
                "source": "backend",
                "component": "startup",
                "reason_code": "startup_note",
                "message": "informational",
                "severity": "info",
                "context": {"status": "ok"},
            },
        ],
    }

    report = build_health_issue_report(
        installation_id="00000000-0000-0000-0000-000000000000",
        app_version="2.9.14-dev+abc1234",
        diagnostics_snapshot=snapshot,
    )

    assert report is not None
    assert report["schema_version"] == "2026-05-03.health-issues.v1"
    assert len(report["issues"]) == 1

    issue = report["issues"][0]
    assert issue["component"] == "video_classifier"
    assert issue["reason_code"] == "video_timeout"
    assert issue["severity"] == "error"
    assert issue["count"] == 2
    assert issue["fingerprint"]
    assert issue["sample_context"] == {
        "configured_provider": "intel_gpu",
        "active_provider": "cpu",
        "timeout_seconds": 180,
        "queue_depth": 4,
    }

    rendered = str(report)
    assert "event-123" not in rendered
    assert "front" not in rendered
    assert "/media" not in rendered
    assert "/config" not in rendered
