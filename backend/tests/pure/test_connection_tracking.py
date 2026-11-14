"""The connection trackers report only what was observed: a state is never assumed."""

from datetime import datetime, timedelta, timezone

from app.services.connection_tracking import FrigateReachabilityTracker, MqttConnectionTracker

T0 = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def test_mqtt_tracker_starts_stopped_and_reports_nothing_measured():
    tracker = MqttConnectionTracker()
    status = tracker.snapshot(server="mqtt", port=1883)
    assert status.state == "stopped"
    assert status.connected_since is None
    assert status.last_attempt_at is None
    assert status.last_error is None


def test_mqtt_tracker_first_attempt_is_connecting_then_connected():
    tracker = MqttConnectionTracker()
    tracker.attempting(T0)
    assert tracker.state == "connecting"
    tracker.connected(T0 + timedelta(seconds=2))
    status = tracker.snapshot(server="mqtt", port=1883)
    assert status.state == "connected"
    assert status.connected_since == "2026-11-13T18:00:02Z"
    assert status.last_attempt_at == "2026-11-13T18:00:00Z"


def test_mqtt_tracker_failed_attempt_reports_disconnected_with_the_error():
    tracker = MqttConnectionTracker()
    tracker.attempting(T0)
    tracker.failed(T0 + timedelta(seconds=1), "[Errno -2] Name or service not known")
    status = tracker.snapshot(server="mqtt.invalid", port=1883)
    assert status.state == "disconnected"
    assert status.server == "mqtt.invalid"
    assert status.last_failure_at == "2026-11-13T18:00:01Z"
    assert status.last_error == "[Errno -2] Name or service not known"
    assert status.connected_since is None


def test_mqtt_tracker_retry_after_failure_stays_disconnected_until_it_connects():
    # A retry is not a reason to stop saying the broker is down.
    tracker = MqttConnectionTracker()
    tracker.attempting(T0)
    tracker.failed(T0, "refused")
    tracker.attempting(T0 + timedelta(seconds=30))
    status = tracker.snapshot(server="mqtt", port=1883)
    assert status.state == "disconnected"
    assert status.last_attempt_at == "2026-11-13T18:00:30Z"
    tracker.connected(T0 + timedelta(seconds=31))
    assert tracker.state == "connected"


def test_mqtt_tracker_dropped_session_is_disconnected():
    tracker = MqttConnectionTracker()
    tracker.attempting(T0)
    tracker.connected(T0)
    tracker.failed(T0 + timedelta(minutes=5), "Disconnected during message iteration")
    assert tracker.snapshot(server="mqtt", port=1883).state == "disconnected"


def test_mqtt_tracker_keeps_long_errors_short():
    tracker = MqttConnectionTracker()
    tracker.failed(T0, "x" * 1000)
    error = tracker.snapshot(server="mqtt", port=1883).last_error
    assert error is not None and len(error) <= 200


def test_mqtt_tracker_announces_only_state_changes():
    changes: list[str] = []
    tracker = MqttConnectionTracker(on_change=lambda: changes.append(tracker.state))
    tracker.attempting(T0)
    tracker.failed(T0, "refused")
    tracker.attempting(T0)
    tracker.failed(T0, "refused")
    tracker.connected(T0)
    tracker.stopped()
    assert changes == ["connecting", "disconnected", "connected", "stopped"]


def test_mqtt_tracker_not_configured_and_stopped_clear_the_session():
    tracker = MqttConnectionTracker()
    tracker.attempting(T0)
    tracker.connected(T0)
    tracker.not_configured()
    status = tracker.snapshot(server="", port=1883)
    assert status.state == "not_configured"
    assert status.connected_since is None
    tracker.stopped()
    assert tracker.snapshot(server="", port=1883).state == "stopped"


def test_frigate_tracker_is_unchecked_until_a_request_is_made():
    tracker = FrigateReachabilityTracker()
    status = tracker.snapshot(url="http://frigate:5000", availability="unknown")
    assert status.state == "unchecked"
    assert status.checked_at is None
    assert tracker.age_seconds(T0) is None


def test_frigate_tracker_any_answer_below_500_means_reachable():
    # A missing event (404) is still Frigate answering.
    tracker = FrigateReachabilityTracker()
    tracker.record_response(404, T0)
    status = tracker.snapshot(url="http://frigate:5000", availability="online")
    assert status.state == "reachable"
    assert status.last_success_at == "2026-11-13T18:00:00Z"
    assert status.last_failure is None
    assert status.availability == "online"


def test_frigate_tracker_classifies_failures():
    tracker = FrigateReachabilityTracker()
    tracker.record_response(503, T0)
    assert tracker.snapshot(url="u", availability="unknown").last_failure == "server_error"
    tracker.record_response(401, T0)
    assert tracker.snapshot(url="u", availability="unknown").last_failure == "unauthorized"
    tracker.record_failure("timeout", T0)
    status = tracker.snapshot(url="u", availability="unknown")
    assert status.state == "unreachable"
    assert status.last_failure == "timeout"


def test_frigate_tracker_latest_request_decides_and_success_clears_failure_kind():
    tracker = FrigateReachabilityTracker()
    tracker.record_failure("connection", T0)
    tracker.record_response(200, T0 + timedelta(seconds=10))
    status = tracker.snapshot(url="u", availability="unknown")
    assert status.state == "reachable"
    assert status.last_failure is None
    # The earlier failure is still on record.
    assert status.last_failure_at == "2026-11-13T18:00:00Z"
    assert tracker.age_seconds(T0 + timedelta(seconds=40)) == 30


def test_frigate_tracker_announces_only_state_changes():
    changes: list[str] = []
    tracker = FrigateReachabilityTracker(on_change=lambda: changes.append(tracker.state))
    tracker.record_failure("connection", T0)
    tracker.record_failure("timeout", T0)
    tracker.record_response(200, T0)
    tracker.record_response(200, T0)
    assert changes == ["unreachable", "reachable"]
