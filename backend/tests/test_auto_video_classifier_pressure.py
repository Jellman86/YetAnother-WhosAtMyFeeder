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
        classification=types.SimpleNamespace(video_classification_max_concurrent=4)
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
        types.SimpleNamespace(error_diagnostics_history=object()),
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
