"""Measured light level from a Home Assistant lux sensor, kept with each detection (#945).

The contract under test: the reading is taken from the configured entity
only, it is stored once with the detection it was measured for, later saves
and configuration changes never rewrite it, and a sensor that cannot answer
leaves the light level unknown.
"""

import csv
import io
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import ha_weather as ha_module
from app.services.ha_weather import HomeAssistantWeatherSource
from app.services.weather_service import WeatherService

LUX_SENSOR = {"state": "1240.5", "attributes": {"device_class": "illuminance", "unit_of_measurement": "lx"}}
HA_FIELDS = (
    "enabled",
    "base_url",
    "access_token",
    "weather_entity",
    "temperature_entity",
    "wind_speed_entity",
    "wind_direction_entity",
    "cloud_cover_entity",
    "precipitation_entity",
    "rain_entity",
    "snowfall_entity",
    "illuminance_entity",
)


@pytest.fixture
def ha_settings(monkeypatch):
    """A connected Home Assistant with nothing named yet; restored afterwards."""
    for field in HA_FIELDS:
        monkeypatch.setattr(settings.ha_weather, field, None)
    monkeypatch.setattr(settings.ha_weather, "enabled", True)
    monkeypatch.setattr(settings.ha_weather, "base_url", "http://ha.local:8123")
    monkeypatch.setattr(settings.ha_weather, "access_token", "token")
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    return settings.ha_weather


def _source(states: dict, **kwargs) -> tuple[HomeAssistantWeatherSource, list[str]]:
    source = HomeAssistantWeatherSource(
        base_url="http://ha.local:8123",
        access_token="token",
        weather_entity=kwargs.pop("weather_entity", None),
        override_entities=kwargs.pop("override_entities", {}),
        **kwargs,
    )
    requested: list[str] = []

    async def fake_fetch(entity_id: str, *, client):
        requested.append(entity_id)
        return states.get(entity_id)

    source._fetch_state = fake_fetch  # type: ignore[method-assign]
    return source, requested


def _serve_states(monkeypatch, states: dict) -> list[str]:
    requested: list[str] = []

    async def fake_fetch(self, entity_id: str, *, client):
        requested.append(entity_id)
        return states.get(entity_id)

    monkeypatch.setattr(ha_module.HomeAssistantWeatherSource, "_fetch_state", fake_fetch)
    return requested


@pytest.mark.asyncio
async def test_source_reads_lux_beside_the_weather_entity():
    source, requested = _source(
        {
            "weather.home": {"state": "sunny", "attributes": {"temperature": 12.0, "temperature_unit": "°C"}},
            "sensor.feeder_lux": LUX_SENSOR,
        },
        weather_entity="weather.home",
        illuminance_entity="sensor.feeder_lux",
    )

    weather = await source.get_current_weather()

    assert weather["illuminance_lux"] == pytest.approx(1240.5)
    assert weather["temperature"] == pytest.approx(12.0)
    assert sorted(requested) == ["sensor.feeder_lux", "weather.home"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state, reason",
    [
        ({"state": "unavailable", "attributes": {"device_class": "illuminance"}}, "unavailable"),
        ({"state": "unknown", "attributes": {"unit_of_measurement": "lx"}}, "unavailable"),
        ({"state": "bright", "attributes": {"unit_of_measurement": "lx"}}, "not_numeric"),
        (
            {"state": "21", "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}},
            "not_illuminance",
        ),
        ({"state": "-4", "attributes": {"unit_of_measurement": "lx"}}, "out_of_range"),
        (None, "unreachable"),
    ],
)
async def test_source_leaves_lux_unknown_and_never_derives_it(state, reason):
    source, _ = _source(
        {
            # Daylight and cloud cover are on offer; neither may stand in for a measurement.
            "weather.home": {"state": "sunny", "attributes": {"cloud_coverage": 10, "uv_index": 6}},
            "sensor.feeder_lux": state,
        },
        weather_entity="weather.home",
        illuminance_entity="sensor.feeder_lux",
    )

    weather, reading = await source.read_current()

    assert "illuminance_lux" not in weather
    assert weather["cloud_cover"] == pytest.approx(10.0)
    assert reading is not None
    assert reading.lux is None
    assert reading.reason == reason


@pytest.mark.asyncio
async def test_source_never_requests_something_that_is_not_an_entity_id():
    source, requested = _source({}, illuminance_entity="sensor/../../config")

    weather, reading = await source.read_current()

    assert requested == []
    assert weather == {}
    assert reading is not None and reading.reason == "invalid_entity_id"


@pytest.mark.asyncio
async def test_source_without_a_lux_entity_reports_no_light_reading():
    source, _ = _source({"weather.home": {"state": "sunny", "attributes": {}}}, weather_entity="weather.home")

    weather, reading = await source.read_current()

    assert reading is None
    assert "illuminance_lux" not in weather


@pytest.mark.asyncio
async def test_lux_alone_keeps_the_forecast_as_the_weather_source(ha_settings, monkeypatch):
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    _serve_states(monkeypatch, {"sensor.feeder_lux": LUX_SENSOR})
    service = WeatherService()

    async def forecast():
        return {"temperature": 9.0, "condition_text": "Cloudy", "cloud_cover": 80}

    monkeypatch.setattr(service, "_fetch_forecast_weather", forecast)

    weather = await service.get_current_weather()

    assert weather == {
        "temperature": 9.0,
        "condition_text": "Cloudy",
        "cloud_cover": 80,
        "illuminance_lux": pytest.approx(1240.5),
    }


@pytest.mark.asyncio
async def test_forecast_never_supplies_a_light_level(ha_settings, monkeypatch):
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    _serve_states(monkeypatch, {"sensor.feeder_lux": {"state": "unavailable", "attributes": {}}})
    service = WeatherService()

    async def forecast():
        return {"temperature": 9.0, "cloud_cover": 0, "is_day": True, "illuminance_lux": 99999}

    monkeypatch.setattr(service, "_fetch_forecast_weather", forecast)

    weather = await service.get_current_weather()

    assert "illuminance_lux" not in weather
    assert weather["temperature"] == 9.0


@pytest.mark.asyncio
async def test_changing_the_lux_entity_is_not_answered_from_the_old_reading(ha_settings, monkeypatch):
    ha_settings.weather_entity = "weather.home"
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    _serve_states(
        monkeypatch,
        {
            "weather.home": {"state": "sunny", "attributes": {}},
            "sensor.feeder_lux": LUX_SENSOR,
            "sensor.porch_lux": {"state": "15", "attributes": {"unit_of_measurement": "lx"}},
        },
    )
    service = WeatherService()

    assert (await service.get_current_weather())["illuminance_lux"] == pytest.approx(1240.5)
    ha_settings.illuminance_entity = "sensor.porch_lux"
    assert (await service.get_current_weather())["illuminance_lux"] == pytest.approx(15.0)
    ha_settings.illuminance_entity = None
    assert "illuminance_lux" not in await service.get_current_weather()


@pytest.mark.asyncio
async def test_settings_api_saves_trims_and_clears_the_lux_entity(ha_settings, monkeypatch, tmp_path):
    import app.config as config_module
    from app.main import app

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/settings", json={"ha_weather_illuminance_entity": "  sensor.feeder_lux "})
        assert res.status_code == 200, res.text
        assert settings.ha_weather.illuminance_entity == "sensor.feeder_lux"
        assert (await client.get("/api/settings")).json()["ha_weather_illuminance_entity"] == "sensor.feeder_lux"

        res = await client.post("/api/settings", json={"ha_weather_illuminance_entity": None})
        assert res.status_code == 200, res.text
        assert settings.ha_weather.illuminance_entity is None
        assert (await client.get("/api/settings")).json()["ha_weather_illuminance_entity"] is None


@pytest.mark.asyncio
async def test_live_test_shows_the_measured_light_level(ha_settings, monkeypatch):
    from app.main import app

    _serve_states(monkeypatch, {"sensor.feeder_lux": LUX_SENSOR})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # The field's unsaved value is tested, as the weather entity's is.
        res = await client.post("/api/settings/ha-weather/test", json={"illuminance_entity": "sensor.feeder_lux"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["weather"] == "not_configured"
    assert body["illuminance"] == {
        "entity_id": "sensor.feeder_lux",
        "status": "ok",
        "lux": pytest.approx(1240.5),
        "reason": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state, reason",
    [
        ({"state": "unavailable", "attributes": {"unit_of_measurement": "lx"}}, "unavailable"),
        (
            {"state": "21", "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}},
            "not_illuminance",
        ),
        ({"state": "bright", "attributes": {"unit_of_measurement": "lx"}}, "not_numeric"),
        ({"state": "9e9", "attributes": {"unit_of_measurement": "lx"}}, "out_of_range"),
        (None, "unreachable"),
    ],
)
async def test_live_test_says_why_the_light_level_is_missing(ha_settings, monkeypatch, state, reason):
    from app.main import app

    ha_settings.weather_entity = "weather.home"
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    _serve_states(
        monkeypatch,
        {
            "weather.home": {"state": "sunny", "attributes": {"temperature": 12, "temperature_unit": "°C"}},
            "sensor.feeder_lux": state,
        },
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/settings/ha-weather/test", json={})

    assert res.status_code == 200, res.text
    body = res.json()
    # The weather answered; the light sensor did not, and the whole test says so.
    assert body["weather"] == "ok"
    assert body["readings"]["temperature"] == pytest.approx(12.0)
    assert "illuminance_lux" not in body["readings"]
    assert body["status"] == "error"
    assert body["illuminance"] == {"entity_id": "sensor.feeder_lux", "status": "error", "lux": None, "reason": reason}


@pytest.mark.asyncio
async def test_live_test_reports_a_failed_weather_read_beside_a_good_light_reading(ha_settings, monkeypatch):
    from app.main import app

    ha_settings.weather_entity = "weather.home"
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    _serve_states(monkeypatch, {"sensor.feeder_lux": LUX_SENSOR})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/settings/ha-weather/test", json={})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert body["weather"] == "error"
    assert body["readings"] == {}
    assert body["illuminance"]["status"] == "ok"
    assert body["illuminance"]["lux"] == pytest.approx(1240.5)


@pytest.mark.asyncio
async def test_live_test_without_a_lux_entity_answers_as_before(ha_settings, monkeypatch):
    from app.main import app

    ha_settings.weather_entity = "weather.home"
    _serve_states(monkeypatch, {"weather.home": {"state": "sunny", "attributes": {"temperature": 12}}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/settings/ha-weather/test", json={})
        assert res.status_code == 200
        assert res.json()["illuminance"] is None
        assert res.json()["weather"] == "ok"

        ha_settings.weather_entity = "weather.gone"
        res = await client.post("/api/settings/ha-weather/test", json={})
        assert res.status_code == 502
        assert res.json()["status"] == "error"


def _detection(event_id: str, *, score: float = 0.8, lux: float | None = None) -> Detection:
    return Detection(
        detection_time=datetime(2026, 11, 13, 9, 0, 0),
        detection_index=1,
        score=score,
        display_name="Robin",
        category_name="Robin",
        frigate_event=event_id,
        camera_name="feeder",
        illuminance_lux=lux,
    )


async def _stored_lux(event_id: str) -> float | None:
    async with get_db() as db:
        cursor = await db.execute("SELECT illuminance_lux FROM detections WHERE frigate_event = ?", (event_id,))
        row = await cursor.fetchone()
    assert row is not None
    return row[0]


async def _delete(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_repository_stores_and_reads_back_the_light_level():
    event_id = f"lux-{uuid.uuid4().hex[:10]}"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            assert await repo.upsert_if_higher_score(_detection(event_id, lux=1240.5)) == (True, False)
            stored = await repo.get_by_frigate_event(event_id)
        assert stored is not None
        assert stored.illuminance_lux == pytest.approx(1240.5)
    finally:
        await _delete(event_id)


@pytest.mark.asyncio
async def test_a_later_save_never_rewrites_or_erases_the_first_measurement():
    event_id = f"lux-{uuid.uuid4().hex[:10]}"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.upsert_if_higher_score(_detection(event_id, score=0.6, lux=1240.5))
            # A better frame arrives after the light changed, then one with the sensor gone.
            assert await repo.upsert_if_higher_score(_detection(event_id, score=0.7, lux=15.0)) == (False, True)
            assert await repo.upsert_if_higher_score(_detection(event_id, score=0.9, lux=None)) == (False, True)
        assert await _stored_lux(event_id) == pytest.approx(1240.5)
    finally:
        await _delete(event_id)


@pytest.mark.asyncio
async def test_a_detection_first_saved_without_a_reading_takes_the_first_one_measured():
    event_id = f"lux-{uuid.uuid4().hex[:10]}"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.upsert_if_higher_score(_detection(event_id, score=0.6, lux=None))
            await repo.upsert_if_higher_score(_detection(event_id, score=0.7, lux=300.0))
        assert await _stored_lux(event_id) == pytest.approx(300.0)
    finally:
        await _delete(event_id)


@pytest.mark.asyncio
async def test_the_schema_refuses_a_light_level_no_sensor_can_report():
    import aiosqlite

    event_id = f"lux-{uuid.uuid4().hex[:10]}"
    try:
        async with get_db() as db:
            for impossible in (-1.0, 200000.5):
                with pytest.raises(aiosqlite.IntegrityError):
                    await db.execute(
                        """INSERT INTO detections (detection_time, detection_index, score, display_name,
                           category_name, frigate_event, camera_name, illuminance_lux)
                           VALUES ('2026-11-13 09:00:00', 1, 0.8, 'Robin', 'Robin', ?, 'feeder', ?)""",
                        (event_id, impossible),
                    )
            await db.rollback()
    finally:
        await _delete(event_id)


@pytest.mark.asyncio
async def test_save_detection_drops_an_invalid_light_level_but_keeps_the_detection(monkeypatch):
    from app.services.detection_service import DetectionService

    event_id = f"lux-{uuid.uuid4().hex[:10]}"
    service = DetectionService(classifier=None)

    async def no_taxonomy(*_args, **_kwargs):
        return {}

    monkeypatch.setattr("app.services.detection_service.taxonomy_service.get_names", no_taxonomy)
    try:
        changed, inserted = await service.save_detection(
            frigate_event=event_id,
            camera="feeder",
            start_time=datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc).timestamp(),
            classification={"label": "Robin", "score": 0.8, "index": 1},
            illuminance_lux=float("inf"),
            report_to_birdweather=False,
        )
        assert (changed, inserted) == (True, True)
        assert await _stored_lux(event_id) is None
    finally:
        await _delete(event_id)


@pytest.mark.asyncio
async def test_events_api_exposes_the_stored_light_level_and_null_when_unmeasured():
    from app.main import app

    settings.auth.enabled = False
    settings.public_access.enabled = False
    camera = f"cam-{uuid.uuid4().hex[:6]}"
    measured, unmeasured = f"lux-{uuid.uuid4().hex[:10]}", f"lux-{uuid.uuid4().hex[:10]}"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            for event_id, lux in ((measured, 1240.5), (unmeasured, None)):
                detection = _detection(event_id, lux=lux)
                detection.camera_name = camera
                await repo.upsert_if_higher_score(detection)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/events", params={"camera": camera, "limit": 20})
        assert res.status_code == 200, res.text
        by_event = {row["frigate_event"]: row for row in res.json()}
        assert by_event[measured]["illuminance_lux"] == pytest.approx(1240.5)
        assert by_event[unmeasured]["illuminance_lux"] is None
    finally:
        await _delete(measured)
        await _delete(unmeasured)


@pytest.mark.asyncio
async def test_ebird_export_notes_the_measured_light_of_the_best_detection():
    from app.main import app

    settings.auth.enabled = False
    settings.public_access.enabled = False
    lat, lon = settings.location.latitude, settings.location.longitude
    settings.location.latitude, settings.location.longitude = 51.501, -0.142
    camera = f"cam-{uuid.uuid4().hex[:6]}"
    events = [f"lux-{uuid.uuid4().hex[:10]}" for _ in range(3)]
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            rows = (
                (events[0], "Robin", 0.70, 15.0, 10),
                (events[1], "Robin", 0.95, 1240.5, 12),
                (events[2], "Dunnock", 0.80, None, 14),
            )
            for event_id, name, score, lux, minute in rows:
                detection = _detection(event_id, score=score, lux=lux)
                detection.display_name = detection.category_name = detection.common_name = name
                detection.scientific_name = {"Robin": "Erithacus rubecula", "Dunnock": "Prunella modularis"}[name]
                detection.camera_name = camera
                detection.detection_time = datetime(2031, 5, 4, 9, minute, 0)
                await repo.upsert_if_higher_score(detection)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/ebird/export", params={"from": "2031-05-04", "to": "2031-05-04"})
        assert res.status_code == 200, res.text
        exported = [row for row in csv.reader(io.StringIO(res.text)) if camera in row[5]]
        # Keyed by genus: the exported common name depends on what taxonomy the database holds.
        comments = {row[1]: row[4] for row in exported}
        assert all(len(row) == 19 for row in exported)
        assert comments["Erithacus"] == "AI confidence 0.95; measured light 1240 lx"
        # No reading is no claim: the comment says nothing about light.
        assert comments["Prunella"] == "AI confidence 0.80"
    finally:
        settings.location.latitude, settings.location.longitude = lat, lon
        for event_id in events:
            await _delete(event_id)


@pytest.mark.asyncio
async def test_live_test_can_read_each_part_on_its_own(ha_settings, monkeypatch):
    from app.main import app

    ha_settings.weather_entity = "weather.home"
    ha_settings.illuminance_entity = "sensor.feeder_lux"
    requested = _serve_states(
        monkeypatch,
        {"weather.home": {"state": "sunny", "attributes": {"temperature": 12}}, "sensor.feeder_lux": LUX_SENSOR},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/settings/ha-weather/test", json={"scope": "weather"})
        assert res.status_code == 200, res.text
        assert res.json()["weather"] == "ok"
        assert res.json()["illuminance"] is None
        assert requested == ["weather.home"]

        requested.clear()
        res = await client.post("/api/settings/ha-weather/test", json={"scope": "illuminance"})
        assert res.status_code == 200, res.text
        assert res.json()["weather"] == "not_configured"
        assert res.json()["readings"] == {}
        assert res.json()["illuminance"]["lux"] == pytest.approx(1240.5)
        assert requested == ["sensor.feeder_lux"]

        ha_settings.illuminance_entity = None
        res = await client.post("/api/settings/ha-weather/test", json={"scope": "illuminance"})
        assert res.status_code == 400
        assert "illuminance entity" in res.json()["message"]
