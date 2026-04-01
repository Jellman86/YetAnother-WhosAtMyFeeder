from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "custom_components" / "yawamf"


def _install_common_test_modules():
    for name in [
        "aiohttp",
        "custom_components",
        "custom_components.yawamf",
        "custom_components.yawamf.const",
        "custom_components.yawamf.coordinator",
        "custom_components.yawamf.sensor",
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
    ]:
        sys.modules.pop(name, None)

    aiohttp_mod = types.ModuleType("aiohttp")

    class ClientTimeout:
        def __init__(self, total=None):
            self.total = total

    aiohttp_mod.ClientTimeout = ClientTimeout
    sys.modules["aiohttp"] = aiohttp_mod

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(REPO_ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components_pkg

    yawamf_pkg = types.ModuleType("custom_components.yawamf")
    yawamf_pkg.__path__ = [str(PACKAGE_DIR)]
    sys.modules["custom_components.yawamf"] = yawamf_pkg

    homeassistant_pkg = types.ModuleType("homeassistant")
    homeassistant_pkg.__path__ = []
    sys.modules["homeassistant"] = homeassistant_pkg

    components_pkg = types.ModuleType("homeassistant.components")
    components_pkg.__path__ = []
    sys.modules["homeassistant.components"] = components_pkg

    helpers_pkg = types.ModuleType("homeassistant.helpers")
    helpers_pkg.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers_pkg

    sensor_mod = types.ModuleType("homeassistant.components.sensor")

    class SensorEntity:
        def async_write_ha_state(self):
            self._write_count = getattr(self, "_write_count", 0) + 1

    class SensorStateClass:
        TOTAL_INCREASING = "total_increasing"

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"

    sensor_mod.SensorEntity = SensorEntity
    sensor_mod.SensorStateClass = SensorStateClass
    sensor_mod.SensorDeviceClass = SensorDeviceClass
    sys.modules["homeassistant.components.sensor"] = sensor_mod

    config_entries_mod = types.ModuleType("homeassistant.config_entries")
    config_entries_mod.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries_mod

    core_mod = types.ModuleType("homeassistant.core")
    core_mod.HomeAssistant = object
    core_mod.callback = lambda func: func
    sys.modules["homeassistant.core"] = core_mod

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")

    class DeviceInfo(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    device_registry_mod.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_mod

    entity_platform_mod = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform_mod.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_mod

    update_coordinator_mod = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __class_getitem__(cls, _item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator

    class DataUpdateCoordinator:
        def __class_getitem__(cls, _item):
            return cls

        def __init__(self, hass, logger, *, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}

        async def async_config_entry_first_refresh(self):
            self.data = await self._async_update_data()

    class UpdateFailed(Exception):
        pass

    update_coordinator_mod.CoordinatorEntity = CoordinatorEntity
    update_coordinator_mod.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator_mod.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_mod

    const_spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.const",
        PACKAGE_DIR / "const.py",
    )
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules["custom_components.yawamf.const"] = const_module
    assert const_spec.loader is not None
    const_spec.loader.exec_module(const_module)


def _load_sensor_module():
    _install_common_test_modules()

    coordinator_mod = types.ModuleType("custom_components.yawamf.coordinator")
    coordinator_mod.YAWAMFDataUpdateCoordinator = object
    sys.modules["custom_components.yawamf.coordinator"] = coordinator_mod

    spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.sensor",
        PACKAGE_DIR / "sensor.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yawamf.sensor"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_coordinator_and_sensor_modules():
    _install_common_test_modules()

    aiohttp_mod = sys.modules["aiohttp"]

    class _ResponseWrapper:
        def __init__(self, response):
            self._response = response
            self.status = response.status_code

        def raise_for_status(self):
            self._response.raise_for_status()

        async def json(self):
            return self._response.json()

    class _RequestContext:
        def __init__(self, session, method, url, **kwargs):
            self._session = session
            self._method = method
            self._url = url
            self._kwargs = kwargs
            self._response = None

        async def __aenter__(self):
            from urllib import request

            data = None
            if "json" in self._kwargs and self._kwargs["json"] is not None:
                data = json.dumps(self._kwargs["json"]).encode("utf-8")
            req = request.Request(
                self._url,
                data=data,
                method=self._method,
                headers=self._kwargs.get("headers") or {},
            )
            if data is not None and "Content-Type" not in req.headers:
                req.add_header("Content-Type", "application/json")
            response = request.urlopen(req, timeout=5)
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else None
            response.close()
            self._response = types.SimpleNamespace(
                status_code=response.status,
                _payload=payload,
                raise_for_status=lambda: None if 200 <= response.status < 400 else (_ for _ in ()).throw(RuntimeError(response.status)),
                json=lambda: payload,
            )
            return _ResponseWrapper(self._response)

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class ClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            return _RequestContext(self, "GET", url, **kwargs)

        def post(self, url, **kwargs):
            return _RequestContext(self, "POST", url, **kwargs)

    aiohttp_mod.ClientSession = ClientSession

    coord_spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.coordinator",
        PACKAGE_DIR / "coordinator.py",
    )
    coordinator_module = importlib.util.module_from_spec(coord_spec)
    sys.modules["custom_components.yawamf.coordinator"] = coordinator_module
    assert coord_spec.loader is not None
    coord_spec.loader.exec_module(coordinator_module)

    sensor_spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.sensor",
        PACKAGE_DIR / "sensor.py",
    )
    sensor_module = importlib.util.module_from_spec(sensor_spec)
    sys.modules["custom_components.yawamf.sensor"] = sensor_module
    assert sensor_spec.loader is not None
    sensor_spec.loader.exec_module(sensor_module)

    return coordinator_module, sensor_module


class _JsonHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        handler = self.routes.get(("GET", self.path))
        if handler is None:
            self.send_response(404)
            self.end_headers()
            return
        status, payload = handler()
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class _JsonServer:
    def __init__(self, routes):
        self._routes = routes
        self._server = None
        self._thread = None

    def __enter__(self):
        handler = type("Handler", (_JsonHandler,), {})
        handler.routes = self._routes
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb):
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        assert self._thread is not None
        self._thread.join(timeout=5)
        return False


class _Coordinator:
    def __init__(self, latest):
        self.entry_id = "entry-1"
        self.url = "http://yawamf.local"
        self.data = {
            "latest": latest,
            "total_today": 2,
        }


def test_last_bird_sensor_updates_for_new_event_even_when_species_repeats():
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "Northern Cardinal",
            "frigate_event": "evt-1",
            "detection_time": "2026-04-01T10:15:00Z",
            "camera_name": "front",
        }
    )
    sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)

    sensor._handle_coordinator_update()
    sensor._handle_coordinator_update()

    coordinator.data["latest"] = {
        "display_name": "Northern Cardinal",
        "frigate_event": "evt-2",
        "detection_time": "2026-04-01T10:16:00Z",
        "camera_name": "front",
    }
    sensor._handle_coordinator_update()

    assert sensor._write_count == 2


def test_last_bird_sensor_attributes_ignore_non_mapping_latest():
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(["not", "a", "mapping"])
    sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)

    assert sensor.extra_state_attributes == {}


def test_event_and_timestamp_sensors_expose_latest_detection_state():
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "Blue Jay",
            "frigate_event": "evt-55",
            "detection_time": "2026-04-01T11:22:33Z",
            "camera_name": "deck",
        }
    )

    event_sensor = sensor_module.YAWAMFLastDetectionEventSensor(coordinator)
    timestamp_sensor = sensor_module.YAWAMFLastDetectionTimestampSensor(coordinator)

    assert event_sensor.native_value == "evt-55"
    assert event_sensor.extra_state_attributes["species"] == "Blue Jay"
    assert timestamp_sensor.native_value == datetime(2026, 4, 1, 11, 22, 33, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_component_polling_populates_sensor_state_from_daily_summary():
    coordinator_module, sensor_module = _load_coordinator_and_sensor_modules()
    payload = {
        "latest_detection": {
            "display_name": "American Goldfinch",
            "frigate_event": "evt-123",
            "detection_time": "2026-04-01T19:31:45Z",
            "camera_name": "feeder",
            "score": 0.98,
        },
        "total_count": 7,
        "top_species": [{"species": "American Goldfinch", "count": 4, "latest_event": "evt-123"}],
    }

    with _JsonServer({("GET", "/api/stats/daily-summary"): lambda: (200, payload)}) as base_url:
        session = sys.modules["aiohttp"].ClientSession()
        coordinator = coordinator_module.YAWAMFDataUpdateCoordinator(
            hass=object(),
            logger=logging.getLogger("yawamf-test"),
            config_entry=types.SimpleNamespace(entry_id="entry-1"),
            session=session,
            url=base_url,
            username=None,
            password=None,
            api_key=None,
            update_interval=coordinator_module.timedelta(seconds=30),
        )

        await coordinator.async_config_entry_first_refresh()

    bird_sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)
    event_sensor = sensor_module.YAWAMFLastDetectionEventSensor(coordinator)
    timestamp_sensor = sensor_module.YAWAMFLastDetectionTimestampSensor(coordinator)

    assert coordinator.data["latest"]["frigate_event"] == "evt-123"
    assert coordinator.data["total_today"] == 7
    assert bird_sensor.native_value == "American Goldfinch"
    assert event_sensor.native_value == "evt-123"
    assert timestamp_sensor.native_value == datetime(2026, 4, 1, 19, 31, 45, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_component_polling_discards_non_mapping_latest_detection():
    coordinator_module, sensor_module = _load_coordinator_and_sensor_modules()
    payload = {
        "latest_detection": ["bad-payload"],
        "total_count": 2,
        "top_species": [],
    }

    with _JsonServer({("GET", "/api/stats/daily-summary"): lambda: (200, payload)}) as base_url:
        session = sys.modules["aiohttp"].ClientSession()
        coordinator = coordinator_module.YAWAMFDataUpdateCoordinator(
            hass=object(),
            logger=logging.getLogger("yawamf-test"),
            config_entry=types.SimpleNamespace(entry_id="entry-1"),
            session=session,
            url=base_url,
            username=None,
            password=None,
            api_key=None,
            update_interval=coordinator_module.timedelta(seconds=30),
        )

        await coordinator.async_config_entry_first_refresh()

    bird_sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)
    event_sensor = sensor_module.YAWAMFLastDetectionEventSensor(coordinator)

    assert coordinator.data["latest"] is None
    assert bird_sensor.native_value is None
    assert bird_sensor.extra_state_attributes == {}
    assert event_sensor.native_value is None
