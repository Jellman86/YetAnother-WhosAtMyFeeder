"""The Explorer's layout choice.

#270: "The explorer section tends to get crowded fast, the cards there are very
big, maybe a more condensed list version would help... What I am interested is
comparing the visiting times."

An appearance preference, alongside the date and time formats: the same kind of
choice, stored the same way.
"""

import httpx
import pytest

from app.config import settings
from app.config_models import AppearanceSettings
from app.main import app


def test_cards_stay_the_default():
    """Nobody's Explorer changes shape because they upgraded."""
    assert AppearanceSettings().explorer_view == "cards"


@pytest.mark.parametrize("value", ["cards", "list"])
def test_both_layouts_are_accepted(value):
    assert AppearanceSettings(explorer_view=value).explorer_view == value


def test_an_unknown_layout_is_refused():
    """A typo in an env var must not leave the Explorer with no way to render."""
    with pytest.raises(ValueError):
        AppearanceSettings(explorer_view="grid")


@pytest.mark.asyncio
async def test_the_setting_round_trips_through_the_api():
    original = (settings.appearance.explorer_view, settings.auth.enabled)
    settings.auth.enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            read = await client.get("/api/settings")
            assert read.status_code == 200, read.text
            assert read.json()["appearance_explorer_view"] == "cards"

            written = await client.post("/api/settings", json={"appearance_explorer_view": "list"})
            assert written.status_code == 200, written.text
            assert settings.appearance.explorer_view == "list"

            back = await client.get("/api/settings")
            assert back.json()["appearance_explorer_view"] == "list"
    finally:
        settings.appearance.explorer_view, settings.auth.enabled = original


@pytest.mark.asyncio
async def test_a_rejected_layout_leaves_the_setting_alone():
    original = (settings.appearance.explorer_view, settings.auth.enabled)
    settings.auth.enabled = False
    settings.appearance.explorer_view = "cards"
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/settings", json={"appearance_explorer_view": "mosaic"})
        assert response.status_code == 422
        assert settings.appearance.explorer_view == "cards"
    finally:
        settings.appearance.explorer_view, settings.auth.enabled = original


@pytest.mark.asyncio
async def test_auth_status_carries_the_layout_to_a_guest():
    """A guest never reads `/api/settings`, so the layout has to reach them here.

    The control calls itself "the layout new devices start with", and a public
    visitor's device is the newest device there is. Without this the setting is
    silently inert on exactly the installs that have visitors, because the
    Explorer falls back to cards when it cannot read a default.
    """
    original = (
        settings.appearance.explorer_view,
        settings.auth.enabled,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
    )
    settings.appearance.explorer_view = "list"
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = True
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/auth/status")
        assert response.status_code == 200, response.text
        assert response.json()["appearance_explorer_view"] == "list"
    finally:
        (
            settings.appearance.explorer_view,
            settings.auth.enabled,
            settings.auth.initial_setup_complete,
            settings.public_access.enabled,
        ) = original


@pytest.mark.asyncio
async def test_auth_status_defaults_the_layout_to_cards():
    """An install that never chose a layout must not push visitors into a list."""
    original = (settings.appearance.explorer_view, settings.auth.enabled)
    settings.appearance.explorer_view = "cards"
    settings.auth.enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/auth/status")
        assert response.status_code == 200, response.text
        assert response.json()["appearance_explorer_view"] == "cards"
    finally:
        settings.appearance.explorer_view, settings.auth.enabled = original
