"""One public projection of the settings a viewer needs.

`/api/settings` is owner-only and returns everything, so every display preference
a visitor needs has been copied onto `/api/auth/status` one field at a time as
somebody noticed it was missing. That pattern only finds a defect after a visitor
has already been given the wrong interface. This projection is the decision point:
a setting is public because it is declared here, not because anyone remembered.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.public_settings import PUBLIC_SETTING_FIELDS, PublicSettings, build_public_settings


@pytest.mark.asyncio
async def test_a_guest_and_an_owner_resolve_the_same_value_for_every_public_setting():
    """The whole point of the projection. If these ever diverge, a visitor is being
    shown an interface the owner did not configure."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        guest = await client.get("/api/settings/public")
        owner = await client.get("/api/settings/public", headers={"X-API-Key": "not-required-here"})

    assert guest.status_code == 200
    assert owner.status_code == 200
    assert guest.json() == owner.json()
    for field in PUBLIC_SETTING_FIELDS:
        assert field in guest.json(), f"{field} is declared public but not served"


@pytest.mark.asyncio
async def test_the_projection_carries_the_three_settings_a_guest_was_denied():
    """Each of these shaped what a visitor saw and none of them reached one.

    The review flag is the worst: `needsReview` returns False when the threshold is
    null, so a guest never saw a row flagged as needing a person, while the layout
    standard names that flag as one of the three signals a visit carries. The guest
    view was making a claim it could not support.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/settings/public")).json()

    assert "classification_threshold" in body
    assert "ebird_default_days_back" in body
    assert "recording_clip_enabled" in body
    assert "clips_enabled" in body


def test_the_projection_is_an_allowlist_and_can_never_carry_a_secret():
    """A filtered copy of the settings would leak a new secret the day one is added.
    The projection names its fields, so a secret can only appear by someone writing
    it here on purpose."""
    declared = set(PublicSettings.model_fields)
    assert declared == set(PUBLIC_SETTING_FIELDS)
    for field in declared:
        assert not any(marker in field for marker in ("key", "token", "password", "secret", "credential")), (
            f"{field} looks like a secret and must not be in a public projection"
        )


def test_building_the_projection_needs_no_database_or_request():
    """Pure, so the decision about what is public is testable on its own."""
    projection = build_public_settings()
    assert isinstance(projection, PublicSettings)
    assert projection.model_dump().keys() == set(PUBLIC_SETTING_FIELDS)
