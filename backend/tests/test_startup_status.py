import json

from app.services.startup_status import StartupStatusPublisher


def test_startup_status_publishes_monotonic_phase_progress_atomically(tmp_path):
    status_path = tmp_path / "startup-status.json"
    publisher = StartupStatusPublisher(status_path)

    publisher.publish("loading_model", 35)
    publisher.publish("detecting_hardware", 20)

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "starting"
    assert payload["phase"] == "detecting_hardware"
    assert payload["progress"] == 35
    assert payload["started_at"]
    assert payload["updated_at"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_startup_status_ready_is_terminal_for_late_startup_updates(tmp_path):
    status_path = tmp_path / "startup-status.json"
    publisher = StartupStatusPublisher(status_path)

    publisher.publish("database", 70)
    publisher.mark_ready()
    publisher.publish("starting_services", 90)

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["phase"] == "ready"
    assert payload["progress"] == 100


def test_startup_status_failure_exposes_only_bounded_operational_fields(tmp_path):
    status_path = tmp_path / "startup-status.json"
    publisher = StartupStatusPublisher(status_path)

    publisher.publish("database", 70)
    publisher.mark_failed("database")

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload == {
        "status": "failed",
        "phase": "database",
        "progress": 70,
        "started_at": payload["started_at"],
        "updated_at": payload["updated_at"],
    }


def test_startup_status_is_a_safe_noop_without_a_configured_path():
    publisher = StartupStatusPublisher(None)

    publisher.publish("loading_model", 35)
    publisher.mark_ready()

    assert publisher.snapshot()["status"] == "ready"
    assert publisher.snapshot()["progress"] == 100
