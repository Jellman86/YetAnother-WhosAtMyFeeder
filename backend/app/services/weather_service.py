import httpx
import structlog
from typing import Optional, Tuple
from datetime import datetime
from app.config import settings

log = structlog.get_logger()

class WeatherService:
    """Service to fetch weather data from OpenMeteo."""
    
    BASE_URL = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    GEO_URL = "http://ip-api.com/json" # Fallback for auto-location

    async def get_location(self) -> Tuple[Optional[float], Optional[float]]:
        """Get configured location or detect via IP."""
        lat = settings.location.latitude
        lon = settings.location.longitude
        
        if lat is not None and lon is not None:
            return lat, lon
            
        if settings.location.automatic:
            try:
                # Use short timeout for auto-location to avoid blocking
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(self.GEO_URL)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get('status') == 'success':
                        log.info("Detected location via IP", lat=data.get('lat'), lon=data.get('lon'), city=data.get('city'))
                        return data.get('lat'), data.get('lon')
            except Exception as e:
                log.warning("Failed to detect location via IP", error=str(e))
                
        return None, None

    async def get_current_weather(self) -> dict:
        """Fetch current weather for the configured location.

        Note: Always fetches temperature in Celsius for consistent database storage.
        Frontend converts to user's preferred unit for display.
        """
        try:
            lat, lon = await self.get_location()

            if lat is None or lon is None:
                return {}

            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,is_day,cloud_cover,wind_speed_10m,wind_direction_10m,precipitation,rain,snowfall",
                "temperature_unit": "celsius"  # Always store in Celsius
            }
            
            # Use short timeout for weather to avoid blocking event processing
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                current = data.get("current", {})
                return {
                    "temperature": current.get("temperature_2m"),
                    "condition_code": current.get("weather_code"),
                    "is_day": current.get("is_day") == 1,
                    "condition_text": self._get_condition_text(current.get("weather_code")),
                    "cloud_cover": current.get("cloud_cover"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "wind_direction": current.get("wind_direction_10m"),
                    "precipitation": current.get("precipitation"),
                    "rain": current.get("rain"),
                    "snowfall": current.get("snowfall")
                }
        except httpx.TimeoutException:
            log.warning("Weather API timeout - skipping weather context")
            return {}
        except Exception as e:
            log.error("Failed to fetch weather", error=str(e))
            return {}

    async def get_hourly_weather(self, start: datetime, end: datetime) -> dict:
        """Fetch hourly weather data for a time range (UTC)."""
        try:
            lat, lon = await self.get_location()

            if lat is None or lon is None:
                return {}

            start_date = start.date().isoformat()
            end_date = end.date().isoformat()

            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "hourly": "temperature_2m,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,precipitation,rain,snowfall",
                "temperature_unit": "celsius",
                "timezone": "UTC"
            }

            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(self.ARCHIVE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                return {}

            result = {}
            for idx, time_str in enumerate(times):
                result[time_str] = {
                    "temperature": hourly.get("temperature_2m", [None] * len(times))[idx],
                    "condition_code": hourly.get("weather_code", [None] * len(times))[idx],
                    "condition_text": self._get_condition_text(hourly.get("weather_code", [None] * len(times))[idx]),
                    "cloud_cover": hourly.get("cloud_cover", [None] * len(times))[idx],
                    "wind_speed": hourly.get("wind_speed_10m", [None] * len(times))[idx],
                    "wind_direction": hourly.get("wind_direction_10m", [None] * len(times))[idx],
                    "precipitation": hourly.get("precipitation", [None] * len(times))[idx],
                    "rain": hourly.get("rain", [None] * len(times))[idx],
                    "snowfall": hourly.get("snowfall", [None] * len(times))[idx]
                }

            return result
        except httpx.TimeoutException:
            log.warning("Weather archive API timeout - skipping weather backfill")
            return {}
        except Exception as e:
            log.error("Failed to fetch hourly weather", error=str(e))
            return {}

    def _get_condition_text(self, code: int) -> str:
        """Map WMO weather code to text."""
        # https://open-meteo.com/en/docs
        if code is None:
            return "Unknown"
        if code == 0:
            return "Clear sky"
        if code in [1, 2, 3]:
            return "Partly cloudy"
        if code in [45, 48]:
            return "Foggy"
        if code in [51, 53, 55]:
            return "Drizzle"
        if code in [61, 63, 65]:
            return "Rain"
        if code in [71, 73, 75]:
            return "Snow"
        if code in [80, 81, 82]:
            return "Rain showers"
        if code in [95, 96, 99]:
            return "Thunderstorm"
        return "Cloudy"

weather_service = WeatherService()
