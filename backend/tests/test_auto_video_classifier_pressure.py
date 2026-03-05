from unittest.mock import patch

from app.services.auto_video_classifier_service import AutoVideoClassifierService


def _mqtt_status(level: str, in_flight: int = 0, capacity: int = 200) -> dict:
    return {
        "pressure_level": level,
        "in_flight": in_flight,
        "in_flight_capacity": capacity,
    }


def test_mqtt_pressure_throttle_normal_keeps_configured_concurrency():
    service = AutoVideoClassifierService()
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("normal")):
        state = service._get_mqtt_throttle_state(configured_max=4)
    assert state["throttled"] is False
    assert state["effective_max_concurrent"] == 4


def test_mqtt_pressure_throttle_elevated_reduces_to_half():
    service = AutoVideoClassifierService()
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("elevated")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 3


def test_mqtt_pressure_throttle_high_caps_to_one():
    service = AutoVideoClassifierService()
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("high")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 1


def test_mqtt_pressure_throttle_critical_pauses_background_processing():
    service = AutoVideoClassifierService()
    with patch("app.services.mqtt_service.mqtt_service.get_status", return_value=_mqtt_status("critical")):
        state = service._get_mqtt_throttle_state(configured_max=6)
    assert state["throttled"] is True
    assert state["effective_max_concurrent"] == 0
