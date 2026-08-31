"""Weather from Home Assistant's own sensors (#277).

A sensor a few metres from the feeder is better evidence than a regional
forecast for what the bird was actually flying in. The contract under test:
the weather entity is the general source, a per-category sensor override
wins for its one reading, everything is stored in the same metric units the
forecast provider used, and an unavailable sensor reads as unknown - never
as a forecast value pretending to be measured.
"""

import pytest

from app.services.ha_weather import (
    HomeAssistantWeatherSource,
    convert_length_mm,
    convert_speed_kmh,
    convert_temperature_c,
    map_ha_condition,
    map_sensor_state,
    map_weather_entity,
)


def test_temperature_converts_to_celsius_for_storage():
    assert convert_temperature_c(68.0, "°F") == pytest.approx(20.0)
    assert convert_temperature_c(20.0, "°C") == pytest.approx(20.0)
    assert convert_temperature_c(293.15, "K") == pytest.approx(20.0)
    assert convert_temperature_c(20.0, None) == pytest.approx(20.0)


def test_speed_converts_to_kmh_for_storage():
    assert convert_speed_kmh(10.0, "mph") == pytest.approx(16.09344)
    assert convert_speed_kmh(5.0, "m/s") == pytest.approx(18.0)
    assert convert_speed_kmh(12.0, "km/h") == pytest.approx(12.0)
    assert convert_speed_kmh(2.0, "kn") == pytest.approx(3.704)


def test_length_converts_to_millimetres_for_storage():
    assert convert_length_mm(1.0, "in") == pytest.approx(25.4)
    assert convert_length_mm(3.0, "mm") == pytest.approx(3.0)
    assert convert_length_mm(1.2, "cm") == pytest.approx(12.0)


def test_ha_conditions_map_to_the_stored_vocabulary():
    assert map_ha_condition("sunny") == "Clear sky"
    assert map_ha_condition("partlycloudy") == "Partly cloudy"
    assert map_ha_condition("rainy") == "Rain"
    assert map_ha_condition("lightning-rainy") == "Thunderstorm"
    assert map_ha_condition("snowy") == "Snow"
    assert map_ha_condition("fog") == "Foggy"
    # An unknown state is unknown, not guessed.
    assert map_ha_condition("unavailable") is None
    assert map_ha_condition("unknown") is None
    assert map_ha_condition(None) is None


def test_weather_entity_maps_measured_fields_and_omits_the_rest():
    payload = {
        "state": "partlycloudy",
        "attributes": {
            "temperature": 64.4,
            "temperature_unit": "°F",
            "wind_speed": 10.0,
            "wind_speed_unit": "mph",
            "wind_bearing": 315,
            "cloud_coverage": 40,
        },
    }
    weather = map_weather_entity(payload)
    assert weather["condition_text"] == "Partly cloudy"
    assert weather["temperature"] == pytest.approx(18.0)
    assert weather["wind_speed"] == pytest.approx(16.09344)
    assert weather["wind_direction"] == 315
    assert weather["cloud_cover"] == 40
    # Nothing measured for precipitation, so nothing claimed.
    assert "rain" not in weather
    assert "snowfall" not in weather


def test_unavailable_weather_entity_yields_nothing():
    assert map_weather_entity({"state": "unavailable", "attributes": {"temperature": 20}}) == {}
    assert map_weather_entity(None) == {}


def test_sensor_override_parses_state_with_its_own_unit():
    payload = {"state": "59.0", "attributes": {"unit_of_measurement": "°F"}}
    assert map_sensor_state(payload, "temperature") == pytest.approx(15.0)
    assert map_sensor_state({"state": "unavailable", "attributes": {}}, "temperature") is None
    assert map_sensor_state({"state": "not-a-number", "attributes": {}}, "temperature") is None
    assert map_sensor_state(None, "temperature") is None
    assert map_sensor_state({"state": "42", "attributes": {}}, "cloud_cover") == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_source_merges_entity_with_overrides_and_degrades_honestly():
    states = {
        "weather.home": {
            "state": "rainy",
            "attributes": {
                "temperature": 12.0,
                "temperature_unit": "°C",
                "wind_speed": 20.0,
                "wind_speed_unit": "km/h",
            },
        },
        "sensor.feeder_temp": {"state": "11.2", "attributes": {"unit_of_measurement": "°C"}},
        "sensor.rain_gauge": {"state": "0.02", "attributes": {"unit_of_measurement": "in"}},
        "sensor.broken": {"state": "unavailable", "attributes": {}},
    }

    source = HomeAssistantWeatherSource(
        base_url="http://ha.local:8123",
        access_token="token",
        weather_entity="weather.home",
        override_entities={
            "temperature": "sensor.feeder_temp",
            "rain": "sensor.rain_gauge",
            "cloud_cover": "sensor.broken",
        },
    )

    async def fake_fetch(entity_id: str):
        return states.get(entity_id)

    source._fetch_state = fake_fetch  # type: ignore[method-assign]

    weather = await source.get_current_weather()
    # The local probe outranks the entity's own reading for its one category.
    assert weather["temperature"] == pytest.approx(11.2)
    assert weather["rain"] == pytest.approx(0.508)
    assert weather["condition_text"] == "Rain"
    assert weather["wind_speed"] == pytest.approx(20.0)
    # The broken override does not fall back to anything: cloud cover was
    # simply not measured.
    assert weather.get("cloud_cover") is None or "cloud_cover" not in weather


@pytest.mark.asyncio
async def test_source_with_everything_unreachable_reports_unknown_not_forecast():
    source = HomeAssistantWeatherSource(
        base_url="http://ha.local:8123",
        access_token="token",
        weather_entity="weather.home",
        override_entities={},
    )

    async def fake_fetch(entity_id: str):
        return None

    source._fetch_state = fake_fetch  # type: ignore[method-assign]
    assert await source.get_current_weather() == {}


def test_home_assistant_unit_spellings_are_honoured():
    """Researched against the HA weather entity contract: wind speed may be
    reported as mi/h or Beaufort, and wind_bearing may be a cardinal."""
    from app.services.ha_weather import wind_bearing_degrees

    assert convert_speed_kmh(10.0, "mi/h") == pytest.approx(16.09344)
    assert convert_speed_kmh(4.0, "Beaufort") == pytest.approx(3.01096 * 8.0)
    assert wind_bearing_degrees("NW") == pytest.approx(315.0)
    assert wind_bearing_degrees("nne") == pytest.approx(22.5)
    assert wind_bearing_degrees(190) == pytest.approx(190.0)
    assert wind_bearing_degrees("gibberish") is None

    payload = {
        "state": "windy",
        "attributes": {"wind_speed": 10.0, "wind_speed_unit": "mi/h", "wind_bearing": "NW"},
    }
    weather = map_weather_entity(payload)
    assert weather["wind_speed"] == pytest.approx(16.09344)
    assert weather["wind_direction"] == pytest.approx(315.0)


@pytest.mark.asyncio
async def test_weather_service_dispatches_to_home_assistant_when_configured(monkeypatch):
    from app.config import settings
    from app.services import ha_weather as ha_module
    from app.services.weather_service import weather_service

    sentinel = {"temperature": 11.2, "condition_text": "Rain"}

    async def fake_current(self):
        return sentinel

    monkeypatch.setattr(ha_module.HomeAssistantWeatherSource, "get_current_weather", fake_current)
    monkeypatch.setattr(settings.ha_weather, "enabled", True)
    monkeypatch.setattr(settings.ha_weather, "base_url", "http://ha.local:8123")
    monkeypatch.setattr(settings.ha_weather, "access_token", "token")
    monkeypatch.setattr(settings.ha_weather, "weather_entity", "weather.home")

    assert await weather_service.get_current_weather() == sentinel


@pytest.mark.asyncio
async def test_settings_api_redacts_and_preserves_the_ha_token(monkeypatch, tmp_path):
    import app.config as config_module
    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(settings.ha_weather, "enabled", False)
    monkeypatch.setattr(settings.ha_weather, "access_token", None)
    monkeypatch.setattr(settings.ha_weather, "base_url", None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/settings",
            json={
                "ha_weather_enabled": True,
                "ha_weather_base_url": "http://ha.local:8123",
                "ha_weather_access_token": "secret-token",
                "ha_weather_entity": "weather.home",
                "ha_weather_temperature_entity": "sensor.feeder_temp",
            },
        )
        assert res.status_code == 200
        assert settings.ha_weather.access_token == "secret-token"

        res = await client.get("/api/settings")
        payload = res.json()
        assert payload["ha_weather_access_token"] == "***REDACTED***"
        assert payload["ha_weather_base_url"] == "http://ha.local:8123"
        assert payload["ha_weather_temperature_entity"] == "sensor.feeder_temp"

        # Saving the settings page back must not overwrite the stored secret
        # with the redaction placeholder.
        res = await client.post("/api/settings", json={"ha_weather_access_token": "***REDACTED***"})
        assert res.status_code == 200
        assert settings.ha_weather.access_token == "secret-token"
