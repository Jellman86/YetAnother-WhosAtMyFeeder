import importlib
import sys
import types
from unittest.mock import patch


def _mqtt_status(level: str, in_flight: int = 0, capacity: int = 200) -> dict:
    return {
        "pressure_level": level,
        "in_flight": in_flight,
        "in_flight_capacity": capacity,
    }


def _build_service(monkeypatch):
    class _Logger:
        def debug(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    fake_classifier = types.SimpleNamespace(get_admission_status=lambda: {"live": {"queued": 0, "running": 0}})
    fake_settings = types.SimpleNamespace(
        classification=types.SimpleNamespace(video_classification_max_concurrent=4),
        maintenance=types.SimpleNamespace(max_concurrent=1),
    )

    monkeypatch.setitem(sys.modules, "structlog", types.SimpleNamespace(get_logger=lambda: _Logger()))
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(Image=object))
    monkeypatch.setitem(sys.modules, "app.config", types.SimpleNamespace(settings=fake_settings))
    monkeypatch.setitem(sys.modules, "app.services.frigate_client", types.SimpleNamespace(frigate_client=object()))
    monkeypatch.setitem(
        sys.modules,
        "app.services.high_quality_snapshot_service",
        types.SimpleNamespace(high_quality_snapshot_service=object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.classifier_service",
        types.SimpleNamespace(
            get_classifier=lambda: fake_classifier,
            VideoClassificationWorkerError=RuntimeError,
        ),
    )
    monkeypatch.setitem(sys.modules, "app.services.broadcaster", types.SimpleNamespace(broadcaster=object()))
    monkeypatch.setitem(sys.modules, "app.services.media_cache", types.SimpleNamespace(media_cache=object()))
    monkeypatch.setitem(
        sys.modules,
        "app.services.video_classification_waiter",
        types.SimpleNamespace(video_classification_waiter=object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.error_diagnostics",
        types.SimpleNamespace(
            error_diagnostics_history=types.SimpleNamespace(record=lambda **kwargs: None)
        ),
    )
    monkeypatch.setitem(sys.modules, "app.database", types.SimpleNamespace(get_db=lambda: None))
    monkeypatch.setitem(
        sys.modules,
        "app.repositories.detection_repository",
        types.SimpleNamespace(DetectionRepository=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.utils.tasks",
        types.SimpleNamespace(create_background_task=lambda coro, name=None: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.mqtt_service",
        types.SimpleNamespace(mqtt_service=types.SimpleNamespace(get_status=lambda: _mqtt_status("normal"))),
    )
    sys.modules.pop("app.services.auto_video_classifier_service", None)
    module = importlib.import_module("app.services.auto_video_classifier_service")
    service = module.AutoVideoClassifierService()
    return service


def test_mqtt_pressure_throttle_normal_keeps_configured_concurrency(monkeypatch):
    service = _build_service(monkeypatch)
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        state = service._get_mqtt_throttle_state(configured_max=4)
    assert state["throttled"] is False
    assert state["effective_max_concurrent"] == 4


def test_get_status_reports_processing_when_video_jobs_are_active(monkeypatch):
    service = _build_service(monkeypatch)
    service._active_tasks = {"evt-active": types.SimpleNamespace(done=lambda: False)}

    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        status = service.get_status()

    assert status["active"] == 1
    assert status["status"] == "processing"


def test_mqtt_pressure_throttle_elevated_reduces_to_half(monkeypatch):
    service = _build_service(monkeypatch)
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("elevated")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 3


def test_mqtt_pressure_throttle_high_caps_to_one(monkeypatch):
    service = _build_service(monkeypatch)
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("high")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 1


def test_mqtt_pressure_throttle_critical_pauses_background_processing(monkeypatch):
    service = _build_service(monkeypatch)
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("critical")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 0


def test_live_queued_pressure_pauses_new_video_starts(monkeypatch):
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 2, "running": 0}}},
    )()

    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        state = service._get_mqtt_throttle_state(configured_max=4)

    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 0
    assert state["throttled_for_live_pressure"] is True
    assert state["throttled_for_mqtt_pressure"] is False
    assert state["live_pressure_active"] is True
    assert state["live_queued"] == 2
    assert state["live_in_flight"] == 0


def test_live_running_pressure_pauses_new_video_starts(monkeypatch):
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 0, "running": 1}}},
    )()

    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        state = service._get_mqtt_throttle_state(configured_max=4)

    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 0
    assert state["throttled_for_live_pressure"] is True
    assert state["live_pressure_active"] is True
    assert state["live_queued"] == 0
    assert state["live_in_flight"] == 1


def test_mqtt_and_live_pressure_are_reported_separately(monkeypatch):
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 0, "running": 0}}},
    )()

    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("high", in_flight=9, capacity=10)):
        state = service._get_mqtt_throttle_state(configured_max=6)

    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 1
    assert state["throttled_for_mqtt_pressure"] is True
    assert state["throttled_for_live_pressure"] is False
    assert state["live_pressure_active"] is False


def test_starved_maintenance_queue_gets_single_video_slot_under_live_pressure(monkeypatch):
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 1, "running": 1}}},
    )()
    service._pending_metadata = {
        "evt-maint-starved": {
            "source": "maintenance",
            "queued_at": 0.0,
        }
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=10.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        state = service._get_mqtt_throttle_state(configured_max=4)

    assert state["throttled"] is True
    assert state["throttled_for_live_pressure"] is True
    assert state["maintenance_starvation_relief_active"] is True
    assert state["effective_max_concurrent"] == 1


def test_starved_maintenance_queue_stays_paused_when_mqtt_pressure_is_critical(monkeypatch):
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 1, "running": 1}}},
    )()
    service._pending_metadata = {
        "evt-maint-starved": {
            "source": "maintenance",
            "queued_at": 0.0,
        }
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=10.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("critical")):
        state = service._get_mqtt_throttle_state(configured_max=4)

    assert state["maintenance_starvation_relief_active"] is False
    assert state["effective_max_concurrent"] == 0


def test_maintenance_guardrail_status_reports_deprioritized_queue(monkeypatch):
    # Deprioritized requires critical MQTT (disables starvation relief) + live pressure + age >= 15s < 90s
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 2, "running": 0}}},
    )()
    service._pending_metadata = {
        "evt-maint-1": {"source": "maintenance", "queued_at": 0.0},
        "evt-maint-2": {"source": "maintenance", "queued_at": 5.0},
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=20.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("critical")):
        status = service.get_maintenance_guardrail_status()

    assert status["pending_maintenance"] == 2
    assert status["active_maintenance"] == 0
    assert status["maintenance_state"] == "deprioritized"
    assert status["coalesce_analyze_unknowns"] is True
    assert status["reject_new_work"] is False
    assert "deprioritized" in str(status["maintenance_status_message"]).lower()


def test_maintenance_guardrail_status_rejects_when_queue_is_stalled(monkeypatch):
    # Stalled state requires critical MQTT pressure (disables starvation relief) + live pressure + old queue
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 1, "running": 1}}},
    )()
    service._pending_metadata = {
        "evt-maint-starved": {"source": "maintenance", "queued_at": 0.0},
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=95.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("critical")):
        status = service.get_maintenance_guardrail_status()

    assert status["maintenance_state"] == "stalled"
    assert status["coalesce_analyze_unknowns"] is True
    assert status["reject_new_work"] is True
    assert "stalled" in str(status["maintenance_status_message"]).lower()


def test_maintenance_guardrail_status_shows_queued_during_starvation_relief(monkeypatch):
    # Under live pressure with non-critical MQTT, starvation relief activates and state is queued/running (not stalled)
    service = _build_service(monkeypatch)
    service._classifier = type(
        "FakeClassifier",
        (),
        {"get_admission_status": lambda self: {"live": {"queued": 1, "running": 1}}},
    )()
    service._pending_metadata = {
        "evt-maint-starved": {"source": "maintenance", "queued_at": 0.0},
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=95.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        status = service.get_maintenance_guardrail_status()

    assert status["maintenance_state"] == "queued"
    assert status["coalesce_analyze_unknowns"] is True
    assert status["reject_new_work"] is True  # Still reject due to oldest_age >= 45s
    assert "stalled" not in str(status["maintenance_status_message"]).lower()


def test_maintenance_guardrail_status_keeps_active_work_running_without_false_stall(monkeypatch):
    service = _build_service(monkeypatch)
    service._active_metadata = {
        "evt-maint-active": {"source": "maintenance", "started_at": 0.0},
    }
    service._maintenance_last_progress_at = 0.0

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=180.0), \
         patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        status = service.get_maintenance_guardrail_status()

    assert status["pending_maintenance"] == 0
    assert status["active_maintenance"] == 1
    assert status["maintenance_state"] == "running"
    assert status["coalesce_analyze_unknowns"] is True
    assert status["reject_new_work"] is False
    assert "running" in str(status["maintenance_status_message"]).lower()


def test_maintenance_guardrail_status_counts_external_maintenance_slots(monkeypatch):
    service = _build_service(monkeypatch)

    coordinator = importlib.import_module("app.services.maintenance_coordinator").maintenance_coordinator
    coordinator._holders = {"backfill:job-1": "backfill"}

    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        status = service.get_maintenance_guardrail_status()

    assert status["active_external_maintenance"] == 1
    assert status["active_maintenance"] == 1
    assert status["coalesce_analyze_unknowns"] is True
    assert status["maintenance_state"] == "running"


# ---------------------------------------------------------------------------
# Stuck-task (coordinator slot leak) detection -- aligned with Milirey issue #33
# bundle data: maintenance_coordinator={capacity:1, available:0} with
# seconds_since_progress=919, active_maintenance=1.
# ---------------------------------------------------------------------------

def test_cancel_stuck_tasks_cancels_task_past_age_limit(monkeypatch):
    """A task held longer than _MAX_JOB_AGE_SECONDS is cancelled to release the coordinator."""
    service = _build_service(monkeypatch)
    module = importlib.import_module("app.services.auto_video_classifier_service")

    cancelled = []

    class StuckTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append("evt-stuck")

    service._active_tasks = {"evt-stuck": StuckTask()}
    service._active_metadata = {
        "evt-stuck": {
            "source": "maintenance",
            "started_at": 0.0,
            "maintenance_holder_id": "maintenance:evt-stuck",
        }
    }

    max_age = module._MAX_JOB_AGE_SECONDS
    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=max_age + 1):
        count = service._cancel_stuck_tasks()

    assert count == 1
    assert "evt-stuck" in cancelled


def test_cancel_stuck_tasks_ignores_tasks_within_age_limit(monkeypatch):
    """Tasks running within the age limit are left untouched."""
    service = _build_service(monkeypatch)

    cancelled = []

    class RunningTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append("evt-running")

    service._active_tasks = {"evt-running": RunningTask()}
    service._active_metadata = {
        "evt-running": {
            "source": "maintenance",
            "started_at": 0.0,
        }
    }

    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=100.0):
        count = service._cancel_stuck_tasks()

    assert count == 0
    assert not cancelled


def test_cancel_stuck_tasks_skips_already_done_tasks(monkeypatch):
    """Tasks that are already done are never cancelled, even if they look old."""
    service = _build_service(monkeypatch)

    cancelled = []

    class DoneTask:
        def done(self):
            return True

        def cancel(self):
            cancelled.append("evt-done")

    service._active_tasks = {"evt-done": DoneTask()}
    service._active_metadata = {
        "evt-done": {"source": "maintenance", "started_at": 0.0}
    }

    module = importlib.import_module("app.services.auto_video_classifier_service")
    max_age = module._MAX_JOB_AGE_SECONDS
    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=max_age + 60):
        count = service._cancel_stuck_tasks()

    assert count == 0
    assert not cancelled


def test_coordinator_slot_available_after_stuck_task_cancelled(monkeypatch):
    """Simulates Milirey's bundle: coordinator.available=0, job running for 920s.

    The job hung in replace_from_clip_bytes (ONNX bird-crop / HQ snapshot generation)
    after successful frame scoring.  With the 10-minute watchdog limit the job should
    be cancelled well before 920 seconds, releasing the coordinator slot for the 719
    queued jobs.
    """
    service = _build_service(monkeypatch)
    module = importlib.import_module("app.services.auto_video_classifier_service")

    cancel_calls = []

    class HungClassificationTask:
        """Mimics a task stuck in replace_from_clip_bytes after frame scoring."""

        def done(self):
            return False

        def cancel(self):
            cancel_calls.append(True)

    # Replicate the exact state from the diagnostic bundle:
    # - one maintenance job active for ~920 seconds
    # - no pending queue (coordinator is the bottleneck)
    service._active_tasks = {"evt-1234abcd": HungClassificationTask()}
    service._active_metadata = {
        "evt-1234abcd": {
            "source": "maintenance",
            "started_at": 0.0,
            "maintenance_holder_id": "maintenance:evt-1234abcd",
        }
    }
    service._maintenance_last_progress_at = 0.0

    max_age = module._MAX_JOB_AGE_SECONDS  # 600s (10 min)
    assert max_age == 600, "Watchdog limit should be 10 minutes"

    # At 300s a healthy job is still within normal bounds — must NOT be cancelled.
    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=300.0):
        count_at_300 = service._cancel_stuck_tasks()
    assert count_at_300 == 0, "Job at 300s is within tolerance"

    # At 920s the job is past the 600s limit — should be cancelled.
    # (Milirey's bundle showed seconds_since_progress=919 before we had a timeout.)
    with patch("app.services.auto_video_classifier_service.time.monotonic", return_value=920.0):
        count_at_920 = service._cancel_stuck_tasks()

    assert count_at_920 == 1, "Job at 920s must be cancelled (past 600s limit)"
    assert cancel_calls, "task.cancel() must be called to trigger the done-callback"
