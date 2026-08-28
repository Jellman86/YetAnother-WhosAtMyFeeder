"""The owner's accessibility choices reach a public visitor.

High contrast and the dyslexia-friendly font are applied from
`settingsStore.settings`, and `/api/settings` is owner-only. On an install with
authentication on and public access enabled, a visitor's settings store is
therefore always empty, so a visitor who needs high contrast cannot have it and
the owner has no way to give it to them.

`accessibility_live_announcements` already travels on the public status payload
for exactly this reason, which left the block split: one field public, two not.
These close it. The same route carries the date and time formats and the
Explorer layout.
"""

import httpx
import pytest

from app.config import settings
from app.main import app


def _guest_install():
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = True


async def _status() -> dict:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/status")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def restore_settings():
    original = (
        settings.accessibility.high_contrast,
        settings.accessibility.dyslexia_font,
        settings.auth.enabled,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
    )
    yield
    (
        settings.accessibility.high_contrast,
        settings.accessibility.dyslexia_font,
        settings.auth.enabled,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
    ) = original


@pytest.mark.asyncio
async def test_a_guest_is_told_the_install_wants_high_contrast(restore_settings):
    _guest_install()
    settings.accessibility.high_contrast = True

    assert (await _status())["accessibility_high_contrast"] is True


@pytest.mark.asyncio
async def test_a_guest_is_told_the_install_wants_the_dyslexia_font(restore_settings):
    _guest_install()
    settings.accessibility.dyslexia_font = True

    assert (await _status())["accessibility_dyslexia_font"] is True


@pytest.mark.asyncio
async def test_an_install_that_chose_neither_says_so(restore_settings):
    """Neither may default on: both change the whole interface."""
    _guest_install()
    settings.accessibility.high_contrast = False
    settings.accessibility.dyslexia_font = False

    status = await _status()
    assert status["accessibility_high_contrast"] is False
    assert status["accessibility_dyslexia_font"] is False
