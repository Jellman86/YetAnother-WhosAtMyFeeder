import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.weather_service import WeatherService


@pytest.fixture
def weather_service():
    return WeatherService()


@pytest.mark.asyncio
async def test_get_location_from_config(weather_service):
    """Should use configured location if available."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        lat, lon = await weather_service.get_location()

        assert lat == 40.7128
        assert lon == -74.0060


@pytest.mark.asyncio
async def test_get_location_auto_detect(weather_service):
    """Should auto-detect location via IP if not configured."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = None
        mock_settings.location.longitude = None
        mock_settings.location.automatic = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "lat": 51.5074,
            "lon": -0.1278,
            "city": "London"
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            lat, lon = await weather_service.get_location()

            assert lat == 51.5074
            assert lon == -0.1278


@pytest.mark.asyncio
async def test_get_location_auto_detect_failure(weather_service):
    """Should return None if auto-detection fails."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = None
        mock_settings.location.longitude = None
        mock_settings.location.automatic = True

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client.return_value = mock_instance

            lat, lon = await weather_service.get_location()

            assert lat is None
            assert lon is None


@pytest.mark.asyncio
async def test_get_location_no_config_no_auto(weather_service):
    """Should return None if no config and auto disabled."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = None
        mock_settings.location.longitude = None
        mock_settings.location.automatic = False

        lat, lon = await weather_service.get_location()

        assert lat is None
        assert lon is None


@pytest.mark.asyncio
async def test_get_current_weather_success(weather_service):
    """Should fetch current weather successfully."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "current": {
                "temperature_2m": 18.5,
                "weather_code": 0,
                "is_day": 1
            }
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            weather = await weather_service.get_current_weather()

            assert weather["temperature"] == 18.5
            assert weather["condition_code"] == 0
            assert weather["is_day"] is True
            assert weather["condition_text"] == "Clear sky"


@pytest.mark.asyncio
async def test_get_current_weather_no_location(weather_service):
    """Should return empty dict if location unavailable."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = None
        mock_settings.location.longitude = None
        mock_settings.location.automatic = False

        weather = await weather_service.get_current_weather()

        assert weather == {}


@pytest.mark.asyncio
async def test_get_current_weather_api_timeout(weather_service):
    """Should handle API timeout gracefully."""
    import httpx

    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            # __aexit__ must return None/False to propagate exceptions
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
            mock_client.return_value = mock_instance

            weather = await weather_service.get_current_weather()

            assert weather == {}


@pytest.mark.asyncio
async def test_get_current_weather_api_error(weather_service):
    """Should handle API errors gracefully."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            # __aexit__ must return None/False to propagate exceptions
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.get = AsyncMock(side_effect=Exception("API connection failed"))
            mock_client.return_value = mock_instance

            weather = await weather_service.get_current_weather()

            assert weather == {}


def test_get_condition_text_clear_sky(weather_service):
    """Should map code 0 to Clear sky."""
    assert weather_service._get_condition_text(0) == "Clear sky"


def test_get_condition_text_partly_cloudy(weather_service):
    """Should map codes 1-3 to Partly cloudy."""
    assert weather_service._get_condition_text(1) == "Partly cloudy"
    assert weather_service._get_condition_text(2) == "Partly cloudy"
    assert weather_service._get_condition_text(3) == "Partly cloudy"


def test_get_condition_text_foggy(weather_service):
    """Should map codes 45, 48 to Foggy."""
    assert weather_service._get_condition_text(45) == "Foggy"
    assert weather_service._get_condition_text(48) == "Foggy"


def test_get_condition_text_rain(weather_service):
    """Should map codes 61-65 to Rain."""
    assert weather_service._get_condition_text(61) == "Rain"
    assert weather_service._get_condition_text(63) == "Rain"
    assert weather_service._get_condition_text(65) == "Rain"


def test_get_condition_text_snow(weather_service):
    """Should map codes 71-75 to Snow."""
    assert weather_service._get_condition_text(71) == "Snow"
    assert weather_service._get_condition_text(73) == "Snow"
    assert weather_service._get_condition_text(75) == "Snow"


def test_get_condition_text_thunderstorm(weather_service):
    """Should map codes 95-99 to Thunderstorm."""
    assert weather_service._get_condition_text(95) == "Thunderstorm"
    assert weather_service._get_condition_text(96) == "Thunderstorm"
    assert weather_service._get_condition_text(99) == "Thunderstorm"


def test_get_condition_text_unknown(weather_service):
    """Should return Unknown for None."""
    assert weather_service._get_condition_text(None) == "Unknown"


def test_get_condition_text_default(weather_service):
    """Should return Cloudy for unmapped codes."""
    assert weather_service._get_condition_text(999) == "Cloudy"
    assert weather_service._get_condition_text(10) == "Cloudy"


@pytest.mark.asyncio
async def test_get_current_weather_includes_all_fields(weather_service):
    """Weather response should include all expected fields."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "current": {
                "temperature_2m": 22.0,
                "weather_code": 61,
                "is_day": 0
            }
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            weather = await weather_service.get_current_weather()

            assert "temperature" in weather
            assert "condition_code" in weather
            assert "is_day" in weather
            assert "condition_text" in weather
            assert weather["temperature"] == 22.0
            assert weather["condition_code"] == 61
            assert weather["is_day"] is False
            assert weather["condition_text"] == "Rain"


@pytest.mark.asyncio
async def test_get_daily_sun_times_uses_local_timezone(weather_service):
    """Sun times should request local timezone from Open-Meteo."""
    with patch('app.services.weather_service.settings') as mock_settings:
        mock_settings.location.latitude = 40.7128
        mock_settings.location.longitude = -74.0060

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "daily": {
                "time": ["2026-02-01"],
                "sunrise": ["2026-02-01T07:01"],
                "sunset": ["2026-02-01T17:13"]
            }
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await weather_service.get_daily_sun_times(
                datetime(2026, 2, 1, 0, 0),
                datetime(2026, 2, 3, 0, 0),
            )

            assert result["2026-02-01"]["sunrise"] == "2026-02-01T07:01"
            assert result["2026-02-01"]["sunset"] == "2026-02-01T17:13"
            _, kwargs = mock_instance.get.await_args
            assert kwargs["params"]["timezone"] == "auto"
