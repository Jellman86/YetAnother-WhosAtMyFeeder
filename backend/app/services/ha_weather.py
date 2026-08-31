"""Weather from Home Assistant's own sensors (#277).

A sensor a few metres from the feeder is better evidence than a regional
forecast for what a bird was actually flying in. The weather entity is the
general source; a per-category sensor override wins for its one reading.
Everything converts to the same metric units the forecast provider stores
(Celsius, km/h, millimetres), and an unavailable sensor reads as unknown —
never as a forecast value presented as measured.
"""

import httpx
import structlog
from typing import Any, Optional

log = structlog.get_logger()

_UNKNOWN_STATES = {"unavailable", "unknown", "none", ""}

# Home Assistant's weather-entity condition vocabulary, mapped onto the
# condition texts the rest of the app already stores and displays.
_CONDITION_MAP = {
    "clear-night": "Clear sky",
    "sunny": "Clear sky",
    "partlycloudy": "Partly cloudy",
    "cloudy": "Cloudy",
    "fog": "Foggy",
    "hail": "Hail",
    "lightning": "Thunderstorm",
    "lightning-rainy": "Thunderstorm",
    "pouring": "Rain",
    "rainy": "Rain",
    "snowy": "Snow",
    "snowy-rainy": "Snow",
    "windy": "Windy",
    "windy-variant": "Windy",
    "exceptional": "Exceptional",
}

#: Which conversion each override category needs.
OVERRIDE_KINDS = {
    "temperature": "temperature",
    "wind_speed": "speed",
    "wind_direction": "plain",
    "cloud_cover": "plain",
    "precipitation": "length",
    "rain": "length",
    "snowfall": "length",
}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in _UNKNOWN_STATES:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def convert_temperature_c(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    normalized = str(unit or "").strip().lstrip("°").upper()
    if normalized == "F":
        return (value - 32.0) * 5.0 / 9.0
    if normalized == "K":
        return value - 273.15
    return value


def convert_speed_kmh(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    normalized = str(unit or "").strip().lower()
    # Home Assistant reports miles per hour as "mi/h"; accept "mph" too.
    if normalized in {"mph", "mi/h"}:
        return value * 1.609344
    if normalized == "m/s":
        return value * 3.6
    if normalized in {"kn", "kt", "knots"}:
        return value * 1.852
    if normalized == "ft/s":
        return value * 1.09728
    if normalized == "beaufort":
        # The accepted empirical conversion: v[km/h] = 3.01096 * B^1.5.
        return 3.01096 * (max(0.0, value) ** 1.5)
    return value


def convert_length_mm(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    normalized = str(unit or "").strip().lower()
    if normalized in {"in", "inch", "inches"}:
        return value * 25.4
    if normalized == "cm":
        return value * 10.0
    return value


# Home Assistant may report wind_bearing as a 1-3 letter cardinal
# instead of degrees; both are measurements and both are kept.
_CARDINAL_DEGREES = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}  # fmt: skip


def wind_bearing_degrees(value: Any) -> Optional[float]:
    numeric = _to_float(value)
    if numeric is not None:
        return numeric
    return _CARDINAL_DEGREES.get(str(value or "").strip().upper())


def map_ha_condition(state: Optional[str]) -> Optional[str]:
    text = str(state or "").strip().lower()
    if not text or text in _UNKNOWN_STATES:
        return None
    return _CONDITION_MAP.get(text, text.replace("-", " ").capitalize())


def map_weather_entity(payload: Optional[dict]) -> dict:
    """Map a weather entity's state payload to the stored weather fields.

    Only measured fields appear in the result; nothing is guessed for the
    rest, so a missing attribute stays an unknown downstream.
    """
    if not isinstance(payload, dict):
        return {}
    condition = map_ha_condition(payload.get("state"))
    if condition is None and str(payload.get("state") or "").strip().lower() in _UNKNOWN_STATES:
        return {}
    attributes = payload.get("attributes") or {}

    weather: dict[str, Any] = {}
    if condition is not None:
        weather["condition_text"] = condition
    temperature = convert_temperature_c(_to_float(attributes.get("temperature")), attributes.get("temperature_unit"))
    if temperature is not None:
        weather["temperature"] = temperature
    wind_speed = convert_speed_kmh(_to_float(attributes.get("wind_speed")), attributes.get("wind_speed_unit"))
    if wind_speed is not None:
        weather["wind_speed"] = wind_speed
    wind_direction = wind_bearing_degrees(attributes.get("wind_bearing"))
    if wind_direction is not None:
        weather["wind_direction"] = wind_direction
    cloud_cover = _to_float(attributes.get("cloud_coverage"))
    if cloud_cover is not None:
        weather["cloud_cover"] = cloud_cover
    precipitation_unit = attributes.get("precipitation_unit")
    precipitation = convert_length_mm(_to_float(attributes.get("precipitation")), precipitation_unit)
    if precipitation is not None:
        weather["precipitation"] = precipitation
    return weather


def map_sensor_state(payload: Optional[dict], category: str) -> Optional[float]:
    """Parse one override sensor's state in the unit it declares."""
    if not isinstance(payload, dict):
        return None
    value = _to_float(payload.get("state"))
    if value is None:
        return None
    unit = (payload.get("attributes") or {}).get("unit_of_measurement")
    kind = OVERRIDE_KINDS.get(category, "plain")
    if kind == "temperature":
        return convert_temperature_c(value, unit)
    if kind == "speed":
        return convert_speed_kmh(value, unit)
    if kind == "length":
        return convert_length_mm(value, unit)
    return value


class HomeAssistantWeatherSource:
    """Reads current conditions from a Home Assistant instance."""

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        weather_entity: Optional[str],
        override_entities: dict[str, str],
        timeout_seconds: float = 3.0,
    ) -> None:
        self._base_url = str(base_url or "").rstrip("/")
        self._access_token = str(access_token or "")
        self._weather_entity = str(weather_entity or "").strip() or None
        self._override_entities = {k: v.strip() for k, v in (override_entities or {}).items() if v and v.strip()}
        self._timeout_seconds = max(0.5, float(timeout_seconds))

    async def _fetch_state(self, entity_id: str) -> Optional[dict]:
        url = f"{self._base_url}/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else None
        except httpx.TimeoutException:
            log.info("home_assistant_state_timeout", entity_id=entity_id)
            return None
        except Exception as exc:
            log.info("home_assistant_state_unavailable", entity_id=entity_id, error=str(exc))
            return None

    async def get_current_weather(self) -> dict:
        """The entity's readings with each configured override on top.

        A failed or unavailable sensor contributes nothing: unknown stays
        unknown rather than borrowing a forecast and calling it measured.
        """
        weather: dict[str, Any] = {}
        if self._weather_entity:
            weather = map_weather_entity(await self._fetch_state(self._weather_entity))
        for category, entity_id in self._override_entities.items():
            value = map_sensor_state(await self._fetch_state(entity_id), category)
            if value is not None:
                weather[category] = value
            else:
                # The override is the declared source of truth for this
                # category; when it cannot answer, the category is unknown.
                weather.pop(category, None)
        return weather
