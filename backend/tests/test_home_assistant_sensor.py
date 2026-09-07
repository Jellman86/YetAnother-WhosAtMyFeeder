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
        "custom_components.yawamf.camera",
        "custom_components.yawamf.ingress",
        "custom_components.yawamf.config_flow",
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.camera",
        "homeassistant.components.http",
        "homeassistant.components.frontend",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.data_entry_flow",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "voluptuous",
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

    exceptions_mod = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryAuthFailed(HomeAssistantError):
        pass

    exceptions_mod.HomeAssistantError = HomeAssistantError
    exceptions_mod.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    sys.modules["homeassistant.exceptions"] = exceptions_mod

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

        @property
        def available(self):
            return getattr(self.coordinator, "last_update_success", True)

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
            from urllib.error import HTTPError

            try:
                response = request.urlopen(req, timeout=5)
            except HTTPError as http_error:
                response = http_error
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else None
            response.close()
            self._response = types.SimpleNamespace(
                status_code=response.status,
                _payload=payload,
                raise_for_status=lambda: (
                    None if 200 <= response.status < 400 else (_ for _ in ()).throw(RuntimeError(response.status))
                ),
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


def _load_ingress_module():
    _install_common_test_modules()

    aiohttp_web_mod = types.ModuleType("aiohttp.web")
    aiohttp_web_mod.StreamResponse = object
    aiohttp_web_mod.Request = object

    class _HTTPException(Exception):
        def __init__(self, *args, text=None, **kwargs):
            super().__init__(text or self.__class__.__name__)
            self.text = text

    aiohttp_web_mod.HTTPBadGateway = type("HTTPBadGateway", (_HTTPException,), {})
    aiohttp_web_mod.HTTPUnauthorized = type("HTTPUnauthorized", (_HTTPException,), {})
    aiohttp_web_mod.HTTPNotFound = type("HTTPNotFound", (_HTTPException,), {})
    sys.modules["aiohttp.web"] = aiohttp_web_mod
    sys.modules["aiohttp"].web = aiohttp_web_mod

    http_mod = types.ModuleType("homeassistant.components.http")

    class HomeAssistantView:
        pass

    http_mod.HomeAssistantView = HomeAssistantView
    sys.modules["homeassistant.components.http"] = http_mod

    coordinator_mod = types.ModuleType("custom_components.yawamf.coordinator")
    coordinator_mod.YAWAMFDataUpdateCoordinator = object
    sys.modules["custom_components.yawamf.coordinator"] = coordinator_mod

    spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.ingress",
        PACKAGE_DIR / "ingress.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yawamf.ingress"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_camera_module():
    _install_common_test_modules()

    camera_mod = types.ModuleType("homeassistant.components.camera")

    class Camera:
        def __init__(self):
            pass

    camera_mod.Camera = Camera
    sys.modules["homeassistant.components.camera"] = camera_mod

    coordinator_mod = types.ModuleType("custom_components.yawamf.coordinator")
    coordinator_mod.YAWAMFDataUpdateCoordinator = object
    sys.modules["custom_components.yawamf.coordinator"] = coordinator_mod

    spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.camera",
        PACKAGE_DIR / "camera.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yawamf.camera"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_config_flow_module(session):
    """Load config_flow.py against stubs; ``session`` is what async_get_clientsession returns."""
    _install_common_test_modules()

    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Required = lambda key, default=None: key
    vol.Optional = lambda key, default=None: key
    vol.All = lambda *validators: validators
    vol.Coerce = lambda kind: kind
    vol.Range = lambda min=None, max=None: (min, max)
    sys.modules["voluptuous"] = vol

    config_entries_mod = sys.modules["homeassistant.config_entries"]

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            pass

        def __init__(self):
            self.context = {}
            self.forms = []
            self.aborts = []

        def async_show_form(self, *, step_id, data_schema, errors=None):
            self.forms.append({"step_id": step_id, "errors": errors or {}})
            return {"type": "form", "step_id": step_id, "errors": errors or {}}

        def async_abort(self, *, reason):
            self.aborts.append(reason)
            return {"type": "abort", "reason": reason}

    class OptionsFlow:
        pass

    config_entries_mod.ConfigFlow = ConfigFlow
    config_entries_mod.OptionsFlow = OptionsFlow

    data_entry_flow_mod = types.ModuleType("homeassistant.data_entry_flow")
    data_entry_flow_mod.FlowResult = dict
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_mod

    aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = lambda hass: session
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_mod

    spec = importlib.util.spec_from_file_location(
        "custom_components.yawamf.config_flow",
        PACKAGE_DIR / "config_flow.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.yawamf.config_flow"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _RecordingSession:
    """A fake aiohttp session that answers from a table and records every request."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def _request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        status, payload = self._responses.get((method, url.split("?")[0].rsplit("/", 1)[-1]), (404, None))
        response = types.SimpleNamespace(
            status=status,
            raise_for_status=lambda: None if status < 400 else (_ for _ in ()).throw(RuntimeError(status)),
        )

        async def _json():
            return payload

        async def _read():
            return payload if isinstance(payload, bytes) else b""

        response.json = _json
        response.read = _read

        class _Context:
            async def __aenter__(self_inner):
                return response

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Context()

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def request(self, method, url, **kwargs):
        return self._request(method, url, **kwargs)


class _JsonHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        self._answer("GET")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._answer("POST")

    def _answer(self, method):
        handler = self.routes.get((method, self.path))
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


def test_daily_count_sensor_models_rolling_24h_measurement_not_monotonic_total():
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "Blue Jay",
            "frigate_event": "evt-55",
            "detection_time": "2026-04-01T11:22:33Z",
            "camera_name": "deck",
        }
    )
    coordinator.data["count_24h"] = 7
    coordinator.data.pop("total_today", None)

    sensor = sensor_module.YAWAMFDailyCountSensor(coordinator)

    assert getattr(sensor, "_attr_state_class", None) is None
    assert "24h" in sensor._attr_name
    assert sensor.native_value == 7


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
    assert coordinator.data["count_24h"] == 7
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


# ---------------------------------------------------------------------------
# Malformed daily-summary payload resilience
# ---------------------------------------------------------------------------


def test_sensors_handle_latest_detection_missing_frigate_event():
    """latest_detection with missing frigate_event should not crash sensors."""
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "House Sparrow",
            # frigate_event key missing entirely
            "detection_time": "2026-04-01T12:00:00Z",
            "camera_name": "feeder",
        }
    )

    bird_sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)
    event_sensor = sensor_module.YAWAMFLastDetectionEventSensor(coordinator)

    assert bird_sensor.native_value == "House Sparrow"
    assert event_sensor.native_value is None


def test_sensors_handle_non_string_detection_time():
    """A numeric or None detection_time must not crash the timestamp sensor."""
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "Mourning Dove",
            "frigate_event": "evt-ts-bad",
            "detection_time": 12345,
            "camera_name": "feeder",
        }
    )

    timestamp_sensor = sensor_module.YAWAMFLastDetectionTimestampSensor(coordinator)
    # Non-parseable timestamp should return None, not raise.
    assert timestamp_sensor.native_value is None


def test_sensors_handle_string_total_count():
    """total_count as a string should fall back to 0 instead of crashing."""
    coordinator_module, sensor_module = _load_coordinator_and_sensor_modules()
    coordinator = _Coordinator(
        {
            "display_name": "House Finch",
            "frigate_event": "evt-tc",
            "detection_time": "2026-04-01T12:00:00Z",
            "camera_name": "feeder",
        }
    )
    coordinator.data["count_24h"] = "not-a-number"

    count_sensor = sensor_module.YAWAMFDailyCountSensor(coordinator)
    # The sensor should handle non-int gracefully.
    value = count_sensor.native_value
    assert value is None or isinstance(value, int)


def test_ingress_rewrites_runtime_icon_assets_and_manifest_paths():
    ingress_module = _load_ingress_module()

    body = """
    <html><head>
    <link rel="icon" href="/favicon.png?v=1" />
    </head><body>
    <script>const icon = "/pwa-192x192.png?v=1"; const api = '/api/stats/daily-summary';</script>
    {"start_url": "/", "scope": "/", "icons": [{"src": "/pwa-512x512.png?v=1"}]}
    </body></html>
    """

    rewritten = ingress_module._rewrite_root_paths(body)

    assert 'window.__YAWAMF_APP_BASE_PATH="/api/yawamf/ingress";' in rewritten
    assert 'href="/api/yawamf/ingress/favicon.png?v=1"' in rewritten
    assert '"/api/yawamf/ingress/pwa-192x192.png?v=1"' in rewritten
    assert "'/api/yawamf/ingress/api/stats/daily-summary'" in rewritten
    assert '"start_url": "/api/yawamf/ingress/"' in rewritten
    assert '"scope": "/api/yawamf/ingress/"' in rewritten
    assert '"/api/yawamf/ingress/pwa-512x512.png?v=1"' in rewritten


def test_ingress_rewrite_does_not_duplicate_app_base_marker():
    ingress_module = _load_ingress_module()
    body = (
        '<html><head><script>window.__YAWAMF_APP_BASE_PATH="/api/yawamf/ingress";</script></head><body></body></html>'
    )

    rewritten = ingress_module._rewrite_root_paths(body)

    assert rewritten.count("__YAWAMF_APP_BASE_PATH") == 1


# ---------------------------------------------------------------------------
# Sidebar proxy survives a reload
# ---------------------------------------------------------------------------


def _frontend_stub():
    """A frontend module whose panel calls record what they were given.

    ``async_remove_panel`` is a plain function here, as it is in core, so a
    caller that awaits it gets a TypeError just as it would in Home Assistant.
    """
    frontend_mod = types.ModuleType("homeassistant.components.frontend")
    frontend_mod.registered = []
    frontend_mod.removed = []

    def async_register_built_in_panel(hass, **kwargs):
        if kwargs["frontend_url_path"] in {p["frontend_url_path"] for p in frontend_mod.registered} and not kwargs.get(
            "update"
        ):
            raise ValueError(f"Overwriting panel {kwargs['frontend_url_path']}")
        frontend_mod.registered.append(kwargs)

    def async_remove_panel(hass, frontend_url_path, *, warn_if_unknown=True):
        frontend_mod.removed.append(frontend_url_path)

    frontend_mod.async_register_built_in_panel = async_register_built_in_panel
    frontend_mod.async_remove_panel = async_remove_panel
    sys.modules["homeassistant.components.frontend"] = frontend_mod
    sys.modules["homeassistant.components"].frontend = frontend_mod
    return frontend_mod


def _hass_stub():
    views = []
    return types.SimpleNamespace(http=types.SimpleNamespace(register_view=views.append), data={}), views


@pytest.mark.asyncio
async def test_ingress_registers_the_view_once_and_follows_the_live_coordinator_across_a_reload():
    ingress_module = _load_ingress_module()
    ingress_module.secrets.token_urlsafe = lambda _length: "test-token"
    frontend = _frontend_stub()
    hass, views = _hass_stub()

    first = types.SimpleNamespace(url="http://old.local", headers={}, session=None)
    second = types.SimpleNamespace(url="http://new.local", headers={}, session=None)

    await ingress_module.async_register_ingress(hass, first)
    await ingress_module.async_register_ingress(hass, second)

    assert [view.url for view in views] == ["/api/yawamf/ingress/{path:.*}"], "the view must be registered once per run"
    assert views[0].runtime.coordinator is second, "the proxy must read the coordinator from the latest setup"
    assert [panel["config"] for panel in frontend.registered] == [
        {"url": "/api/yawamf/ingress/?auth=test-token"},
        {"url": "/api/yawamf/ingress/?auth=test-token"},
    ]
    assert all(panel["update"] is True for panel in frontend.registered)
    assert all(panel["require_admin"] is False for panel in frontend.registered)


@pytest.mark.asyncio
async def test_ingress_unregister_removes_the_panel_with_a_plain_call_and_the_proxy_refuses_afterwards():
    ingress_module = _load_ingress_module()
    frontend = _frontend_stub()
    hass, views = _hass_stub()
    coordinator = types.SimpleNamespace(url="http://yawamf.local", headers={}, session=None)

    await ingress_module.async_register_ingress(hass, coordinator)
    ingress_module.async_unregister_ingress(hass)

    assert frontend.removed == ["yawamf"]
    assert views[0].runtime.coordinator is None
    request = types.SimpleNamespace(query={"auth": views[0].runtime.token}, cookies={}, headers={}, method="GET")
    with pytest.raises(ingress_module.web.HTTPNotFound):
        await views[0]._proxy(request, "")


@pytest.mark.asyncio
async def test_ingress_keeps_its_token_across_a_reload_so_an_open_browser_keeps_working():
    ingress_module = _load_ingress_module()
    _frontend_stub()
    hass, views = _hass_stub()

    await ingress_module.async_register_ingress(hass, types.SimpleNamespace(url="http://a", headers={}, session=None))
    token_before = views[0].runtime.token
    ingress_module.async_unregister_ingress(hass)
    await ingress_module.async_register_ingress(hass, types.SimpleNamespace(url="http://b", headers={}, session=None))

    assert views[0].runtime.token == token_before


@pytest.mark.asyncio
async def test_ingress_unregister_is_harmless_when_nothing_was_registered():
    ingress_module = _load_ingress_module()
    frontend = _frontend_stub()
    hass, _views = _hass_stub()

    ingress_module.async_unregister_ingress(hass)

    assert frontend.removed == []


@pytest.mark.asyncio
async def test_ingress_proxy_refreshes_the_login_before_forwarding():
    ingress_module = _load_ingress_module()
    _frontend_stub()
    hass, views = _hass_stub()
    order = []

    class _Coordinator:
        url = "http://yawamf.local"
        headers = {"Authorization": "Bearer fresh"}

        async def async_ensure_logged_in(self):
            order.append("login")

        class session:
            @staticmethod
            def request(method, url, **kwargs):
                order.append(("forward", url, kwargs["headers"].get("Authorization")))
                raise RuntimeError("stop here; the response path needs a real aiohttp")

    await ingress_module.async_register_ingress(hass, _Coordinator())
    request = types.SimpleNamespace(
        query={"auth": views[0].runtime.token}, cookies={}, headers={"Host": "ha.local"}, method="GET"
    )

    with pytest.raises(ingress_module.web.HTTPBadGateway):
        await views[0]._proxy(request, "api/version")

    assert order == ["login", ("forward", "http://yawamf.local/api/version", "Bearer fresh")]


@pytest.mark.asyncio
async def test_ingress_proxy_answers_502_without_a_stack_trace_when_the_login_is_rejected():
    ingress_module = _load_ingress_module()
    _frontend_stub()
    hass, views = _hass_stub()
    auth_failed = sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed

    class _Coordinator:
        url = "http://yawamf.local"
        headers = {}
        session = None

        async def async_ensure_logged_in(self):
            raise auth_failed("nope")

    await ingress_module.async_register_ingress(hass, _Coordinator())
    request = types.SimpleNamespace(query={"auth": views[0].runtime.token}, cookies={}, headers={}, method="GET")

    with pytest.raises(ingress_module.web.HTTPBadGateway) as raised:
        await views[0]._proxy(request, "")

    assert "reconfigure the integration" in raised.value.text


@pytest.mark.asyncio
async def test_ingress_proxy_rejects_a_request_without_the_token():
    ingress_module = _load_ingress_module()
    _frontend_stub()
    hass, views = _hass_stub()
    await ingress_module.async_register_ingress(
        hass, types.SimpleNamespace(url="http://yawamf.local", headers={}, session=None)
    )
    request = types.SimpleNamespace(query={}, cookies={"yawamf_ingress_token": "stale"}, headers={}, method="GET")

    with pytest.raises(ingress_module.web.HTTPUnauthorized):
        await views[0]._proxy(request, "")


@pytest.mark.asyncio
async def test_unloading_one_of_two_sidebar_entries_points_the_proxy_at_the_survivor():
    _install_common_test_modules()
    ingress_module = _load_ingress_module()
    frontend = _frontend_stub()
    hass, views = _hass_stub()
    hass.config_entries = types.SimpleNamespace(async_unload_platforms=_async_true)

    init_spec = importlib.util.spec_from_file_location("custom_components.yawamf", PACKAGE_DIR / "__init__.py")
    sys.modules["homeassistant.const"] = types.SimpleNamespace(
        Platform=types.SimpleNamespace(SENSOR="sensor", CAMERA="camera")
    )
    sys.modules["homeassistant.helpers.aiohttp_client"] = types.SimpleNamespace(
        async_get_clientsession=lambda hass: None
    )
    init_module = importlib.util.module_from_spec(init_spec)
    assert init_spec.loader is not None
    init_spec.loader.exec_module(init_module)

    first = types.SimpleNamespace(url="http://first", headers={}, session=None)
    second = types.SimpleNamespace(url="http://second", headers={}, session=None)
    hass.data[ingress_module.DOMAIN] = {"a": first, "b": second, "_ingress_entries": {"a", "b"}}
    await ingress_module.async_register_ingress(hass, first)
    await ingress_module.async_register_ingress(hass, second)

    assert await init_module.async_unload_entry(hass, types.SimpleNamespace(entry_id="b")) is True

    assert views[0].runtime.coordinator is first, "the proxy must follow the entry that still wants the sidebar"
    assert frontend.removed == [], "the panel stays while another entry still wants it"

    assert await init_module.async_unload_entry(hass, types.SimpleNamespace(entry_id="a")) is True

    assert views[0].runtime.coordinator is None
    assert frontend.removed == ["yawamf"]


async def _async_true(*_args, **_kwargs):
    return True


def test_ingress_no_longer_squats_root_asset_paths():
    ingress_module = _load_ingress_module()

    assert not hasattr(ingress_module, "YAWAMFIngressAssetView")
    assert not hasattr(ingress_module, "_PUBLIC_ASSET_PATHS")


# ---------------------------------------------------------------------------
# Sensor availability
# ---------------------------------------------------------------------------


def test_last_bird_sensor_writes_state_when_the_coordinator_stops_reaching_yawamf():
    sensor_module = _load_sensor_module()
    coordinator = _Coordinator(
        {
            "display_name": "Northern Cardinal",
            "frigate_event": "evt-1",
            "detection_time": "2026-04-01T10:15:00Z",
            "camera_name": "front",
        }
    )
    coordinator.last_update_success = True
    sensor = sensor_module.YAWAMFLastBirdSensor(coordinator)

    sensor._handle_coordinator_update()
    sensor._handle_coordinator_update()
    coordinator.last_update_success = False
    sensor._handle_coordinator_update()
    sensor._handle_coordinator_update()
    coordinator.last_update_success = True
    sensor._handle_coordinator_update()

    assert sensor._write_count == 3, "one write per change: first seen, went unavailable, came back"


# ---------------------------------------------------------------------------
# Coordinator authentication failures start reauth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_raises_auth_failed_when_yawamf_answers_401():
    coordinator_module, _sensor_module = _load_coordinator_and_sensor_modules()
    auth_failed = sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed

    with _JsonServer({("GET", "/api/stats/daily-summary"): lambda: (401, {"detail": "no"})}) as base_url:
        session = sys.modules["aiohttp"].ClientSession()
        coordinator = coordinator_module.YAWAMFDataUpdateCoordinator(
            hass=object(),
            logger=logging.getLogger("yawamf-test"),
            config_entry=types.SimpleNamespace(entry_id="entry-1"),
            session=session,
            url=base_url,
            username=None,
            password=None,
            api_key="stale-key",
            update_interval=coordinator_module.timedelta(seconds=30),
        )

        with pytest.raises(auth_failed):
            await coordinator.async_config_entry_first_refresh()


@pytest.mark.asyncio
async def test_coordinator_raises_auth_failed_when_the_login_is_rejected():
    coordinator_module, _sensor_module = _load_coordinator_and_sensor_modules()
    auth_failed = sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed
    routes = {
        ("POST", "/api/auth/login"): lambda: (401, {"detail": "bad password"}),
        ("GET", "/api/stats/daily-summary"): lambda: (200, {"total_count": 0}),
    }

    with _JsonServer(routes) as base_url:
        session = sys.modules["aiohttp"].ClientSession()
        coordinator = coordinator_module.YAWAMFDataUpdateCoordinator(
            hass=object(),
            logger=logging.getLogger("yawamf-test"),
            config_entry=types.SimpleNamespace(entry_id="entry-1"),
            session=session,
            url=base_url,
            username="owner",
            password="wrong",
            api_key=None,
            update_interval=coordinator_module.timedelta(seconds=30),
        )

        with pytest.raises(auth_failed):
            await coordinator.async_config_entry_first_refresh()


@pytest.mark.asyncio
async def test_coordinator_reports_a_plain_outage_as_update_failed_not_auth():
    coordinator_module, _sensor_module = _load_coordinator_and_sensor_modules()
    update_failed = sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed

    with _JsonServer({("GET", "/api/stats/daily-summary"): lambda: (503, {"detail": "down"})}) as base_url:
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

        with pytest.raises(update_failed):
            await coordinator.async_config_entry_first_refresh()


# ---------------------------------------------------------------------------
# Camera caches per detection and times out
# ---------------------------------------------------------------------------


def _camera_coordinator(session, event_id="evt-1"):
    coordinator = types.SimpleNamespace(
        entry_id="entry-1",
        url="http://yawamf.local",
        headers={},
        session=session,
        data={"latest": {"frigate_event": event_id}},
    )

    async def _login():
        return None

    coordinator.async_ensure_logged_in = _login
    return coordinator


def _camera_hass():
    async def run_in_executor(func, *args):
        return func(*args)

    return types.SimpleNamespace(async_add_executor_job=run_in_executor)


@pytest.mark.asyncio
async def test_camera_serves_the_cached_snapshot_for_the_same_detection_and_refetches_for_a_new_one():
    camera_module = _load_camera_module()
    session = _RecordingSession({("GET", "snapshot.jpg"): (200, b"jpeg-bytes")})
    coordinator = _camera_coordinator(session)
    camera = camera_module.YAWAMFLatestBirdCamera(coordinator)
    camera.hass = _camera_hass()

    first = await camera.async_camera_image()
    again = await camera.async_camera_image()
    coordinator.data["latest"] = {"frigate_event": "evt-2"}
    fresh = await camera.async_camera_image()

    assert first == again == fresh == b"jpeg-bytes"
    assert [call["url"] for call in session.calls] == [
        "http://yawamf.local/api/frigate/evt-1/snapshot.jpg",
        "http://yawamf.local/api/frigate/evt-2/snapshot.jpg",
    ]


@pytest.mark.asyncio
async def test_camera_snapshot_fetch_carries_a_timeout():
    camera_module = _load_camera_module()
    session = _RecordingSession({("GET", "snapshot.jpg"): (200, b"jpeg-bytes")})
    camera = camera_module.YAWAMFLatestBirdCamera(_camera_coordinator(session))
    camera.hass = _camera_hass()

    await camera.async_camera_image()

    assert session.calls[0]["timeout"].total == 15


@pytest.mark.asyncio
async def test_camera_returns_nothing_for_a_detection_it_cannot_fetch_and_keeps_the_older_frame():
    camera_module = _load_camera_module()
    session = _RecordingSession({("GET", "snapshot.jpg"): (200, b"jpeg-bytes")})
    coordinator = _camera_coordinator(session)
    camera = camera_module.YAWAMFLatestBirdCamera(coordinator)
    camera.hass = _camera_hass()

    assert await camera.async_camera_image() == b"jpeg-bytes"

    coordinator.data["latest"] = {"frigate_event": "evt-2"}
    session._responses[("GET", "snapshot.jpg")] = (503, None)
    assert await camera.async_camera_image() is None, "a frame from another detection must not stand in"

    coordinator.data["latest"] = {"frigate_event": "evt-1"}
    assert await camera.async_camera_image() == b"jpeg-bytes", "the older detection is still cached"
    assert len(session.calls) == 2


# ---------------------------------------------------------------------------
# Config flow: timeouts and reauth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_flow_validation_requests_all_carry_a_timeout():
    session = _RecordingSession(
        {
            ("GET", "health"): (200, {}),
            ("GET", "status"): (200, {"auth_required": True, "public_access_enabled": False}),
            ("POST", "login"): (200, {"access_token": "jwt"}),
        }
    )
    config_flow = _load_config_flow_module(session)

    await config_flow.validate_input(
        object(), {"url": "http://yawamf.local", "username": "owner", "password": "pw", "api_key": ""}
    )

    assert len(session.calls) == 3
    assert all(call["timeout"].total == 10 for call in session.calls)


@pytest.mark.asyncio
async def test_reauth_replaces_credentials_in_data_and_clears_them_from_options():
    session = _RecordingSession(
        {
            ("GET", "health"): (200, {}),
            ("GET", "status"): (200, {"auth_required": True, "public_access_enabled": False}),
            ("POST", "login"): (200, {"access_token": "jwt"}),
        }
    )
    config_flow = _load_config_flow_module(session)
    entry = types.SimpleNamespace(
        entry_id="entry-1",
        data={"url": "http://yawamf.local", "username": "old", "password": "old-pw"},
        options={"url": "http://yawamf.local", "username": "stale", "password": "stale-pw", "polling_interval": 45},
    )
    updates = []
    reloads = []

    async def reload(entry_id):
        reloads.append(entry_id)

    flow = config_flow.ConfigFlow()
    flow.context = {"entry_id": "entry-1"}
    flow.hass = types.SimpleNamespace(
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: entry,
            async_update_entry=lambda entry, **changes: updates.append(changes),
            async_reload=reload,
        )
    )

    shown = await flow.async_step_reauth({"url": "http://yawamf.local"})
    result = await flow.async_step_reauth_confirm({"username": "owner", "password": "new-pw"})

    assert shown["step_id"] == "reauth_confirm"
    assert result == {"type": "abort", "reason": "reauth_successful"}
    assert updates == [
        {
            "data": {"url": "http://yawamf.local", "username": "owner", "password": "new-pw", "api_key": None},
            "options": {"url": "http://yawamf.local", "polling_interval": 45},
        }
    ]
    assert reloads == ["entry-1"]
    assert session.calls[-1]["json"] == {"username": "owner", "password": "new-pw"}


@pytest.mark.asyncio
async def test_reauth_shows_the_form_again_when_the_new_credentials_are_rejected():
    session = _RecordingSession(
        {
            ("GET", "health"): (200, {}),
            ("GET", "status"): (200, {"auth_required": True, "public_access_enabled": False}),
            ("POST", "login"): (401, {"detail": "no"}),
        }
    )
    config_flow = _load_config_flow_module(session)
    entry = types.SimpleNamespace(entry_id="entry-1", data={"url": "http://yawamf.local"}, options={})
    flow = config_flow.ConfigFlow()
    flow.context = {"entry_id": "entry-1"}
    flow.hass = types.SimpleNamespace(
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda entry_id: entry,
            async_update_entry=lambda *a, **k: pytest.fail("must not persist rejected credentials"),
            async_reload=None,
        )
    )

    result = await flow.async_step_reauth_confirm({"username": "owner", "password": "wrong"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
