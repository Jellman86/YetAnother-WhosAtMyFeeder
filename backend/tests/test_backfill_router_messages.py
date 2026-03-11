from app.routers.backfill import BackfillJobStatus, _build_running_message, _build_skipped_message


def test_build_skipped_message_without_reasons():
    assert _build_skipped_message(0, None) == ""
    assert _build_skipped_message(3, None) == "3 skipped"


def test_build_skipped_message_already_exists_only():
    assert _build_skipped_message(4, {"already_exists": 4}) == "4 already existed"


def test_build_skipped_message_reports_invalid_scores():
    assert _build_skipped_message(2, {"invalid_score": 2}) == "2 had invalid classifier scores"


def test_build_skipped_message_mixed_reasons():
    msg = _build_skipped_message(
        17,
        {
            "already_exists": 5,
            "invalid_score": 2,
            "low_confidence": 7,
            "blocked_label": 3,
        },
    )
    assert msg == "5 already existed, 2 had invalid classifier scores, 10 skipped by filters/validation"


def test_build_running_message_reports_scanning_when_total_unknown():
    job = BackfillJobStatus(id="job-1", kind="detections", status="running")
    assert _build_running_message(job, {}) == "Scanning historical events"


def test_build_running_message_reports_live_pressure_pause():
    job = BackfillJobStatus(
        id="job-2",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(job, {"background_throttled": True})
        == "Paused while live detections use classifier capacity"
    )


def test_build_running_message_reports_classifier_recovery_pause():
    job = BackfillJobStatus(
        id="job-3",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "background_throttled": True,
                "worker_pools": {
                    "live": {"circuit_open": True},
                    "background": {"circuit_open": False},
                },
            },
        )
        == "Paused while classifier workers recover"
    )


def test_build_running_message_reports_classifier_recovery_mid_run():
    job = BackfillJobStatus(
        id="job-4",
        kind="detections",
        status="running",
        processed=48,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "worker_pools": {
                    "live": {"circuit_open": False},
                    "background": {"circuit_open": True},
                },
            },
        )
        == "Waiting for classifier workers to recover"
    )
