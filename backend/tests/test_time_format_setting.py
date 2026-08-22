"""The display time format is owned by the app, not by the browser's locale.

`date_format` already lets an owner pin the date. Time was left to
`toLocaleTimeString()`, so choosing `dmy` on a US-locale browser produced a
European date beside a 12 hour clock in the same string. `time_format` closes
that gap and is validated the same way `date_format` is.
"""

import httpx
import pytest
import pytest_asyncio

from app.config import Settings, settings
from app.main import app
from app.routers.settings import SettingsUpdate


def test_time_format_defaults_to_following_the_locale():
    # `Settings()` needs a `frigate` section, so assert the declared default.
    assert Settings.model_fields["time_format"].default == "locale"


@pytest.mark.parametrize("value", ["locale", "12h", "24h"])
def test_time_format_accepts_the_supported_choices(value: str):
    assert SettingsUpdate(time_format=value).time_format == value


@pytest.mark.parametrize("value", ["LOCALE", " 24H ", "12H"])
def test_time_format_is_normalised(value: str):
    assert SettingsUpdate(time_format=value).time_format == value.strip().lower()


@pytest.mark.parametrize("value", ["24", "twelve", "hh:mm", ""])
def test_time_format_rejects_anything_else(value: str):
    with pytest.raises(ValueError, match="time_format must be one of"):
        SettingsUpdate(time_format=value)


def test_time_format_is_optional_so_existing_clients_are_unaffected():
    assert SettingsUpdate().time_format is None


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_time_format_survives_a_settings_round_trip(client):
    original = settings.time_format
    try:
        response = await client.post("/api/settings", json={"time_format": "24h"})
        assert response.status_code == 200

        reread = await client.get("/api/settings")
        assert reread.status_code == 200
        assert reread.json()["time_format"] == "24h"
    finally:
        settings.time_format = original


@pytest.mark.asyncio
async def test_settings_write_without_time_format_leaves_it_alone(client):
    original = settings.time_format
    try:
        settings.time_format = "24h"
        response = await client.post("/api/settings", json={"date_format": "dmy"})
        assert response.status_code == 200
        assert settings.time_format == "24h"
    finally:
        settings.time_format = original


@pytest.mark.asyncio
async def test_auth_status_reports_the_time_format(client):
    original = settings.time_format
    try:
        settings.time_format = "24h"
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json()["time_format"] == "24h"
    finally:
        settings.time_format = original


@pytest.mark.asyncio
async def test_settings_rejects_an_unsupported_time_format(client):
    response = await client.post("/api/settings", json={"time_format": "25h"})
    assert response.status_code == 422
