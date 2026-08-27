"""The media integrity scan's settings, and the legacy keys they replace.

`auto_purge_missing_clips` and `auto_purge_missing_snapshots` said "purge",
but with the default `frigate_missing_behavior = mark_missing` they purge
nothing — they mark. An owner who wants their history marked will not tick a
box labelled purge, so the setting that would keep `frigate_status` honest is
the one they have been correctly avoiding (#254).

The names change; the behaviour of an existing install must not.
"""

import pytest

from app.config_models import MaintenanceSettings


def test_the_scan_is_off_until_an_owner_turns_it_on():
    """It asks Frigate about every detection it checks and can be configured to
    delete history, so it is never something an upgrade switches on."""
    settings = MaintenanceSettings()
    assert settings.media_integrity_scan_enabled is False
    assert settings.media_integrity_scan_media == "any"


@pytest.mark.parametrize(
    ("legacy", "expected_enabled", "expected_media"),
    [
        ({"auto_purge_missing_clips": True, "auto_purge_missing_snapshots": True}, True, "any"),
        ({"auto_purge_missing_clips": True, "auto_purge_missing_snapshots": False}, True, "clip"),
        ({"auto_purge_missing_clips": False, "auto_purge_missing_snapshots": True}, True, "snapshot"),
        ({"auto_purge_missing_clips": False, "auto_purge_missing_snapshots": False}, False, "any"),
        ({}, False, "any"),
    ],
)
def test_legacy_purge_keys_carry_their_exact_behaviour_forward(legacy, expected_enabled, expected_media):
    """Someone who enabled only the clip scan must keep getting only the clip
    scan. Collapsing both flags into one switch would quietly widen what counts
    as missing for them."""
    settings = MaintenanceSettings(**legacy)
    assert settings.media_integrity_scan_enabled is expected_enabled
    assert settings.media_integrity_scan_media == expected_media


def test_the_new_keys_win_when_both_are_present():
    """A config written by a current install must not be reinterpreted through
    the legacy keys it also still carries."""
    settings = MaintenanceSettings(
        media_integrity_scan_enabled=False,
        media_integrity_scan_media="clip",
        auto_purge_missing_clips=True,
        auto_purge_missing_snapshots=True,
    )
    assert settings.media_integrity_scan_enabled is False
    assert settings.media_integrity_scan_media == "clip"


def test_the_scan_is_bounded_so_it_cannot_ask_frigate_about_everything_at_once():
    """The old scan read every row and asked Frigate about each one, every
    cycle. On a 96,000-detection install that is 96,000 requests per run, mostly
    about events retired months ago. The batch is what makes it safe to enable."""
    settings = MaintenanceSettings()
    assert settings.media_integrity_scan_batch_size == 1000
    assert settings.media_integrity_scan_interval_hours == 6

    with pytest.raises(ValueError):
        MaintenanceSettings(media_integrity_scan_batch_size=0)
    with pytest.raises(ValueError):
        MaintenanceSettings(media_integrity_scan_interval_hours=0)


def test_the_legacy_keys_are_still_readable_for_an_older_client():
    """The settings API still reports them, so a client that has not been
    updated keeps seeing a truthful value rather than a missing field."""
    settings = MaintenanceSettings(auto_purge_missing_clips=True, auto_purge_missing_snapshots=True)
    assert settings.auto_purge_missing_clips is True
    assert settings.auto_purge_missing_snapshots is True


@pytest.mark.asyncio
async def test_an_older_client_writing_only_the_legacy_toggle_still_enables_the_scan():
    """The Settings page writes `auto_purge_missing_*`. If that no longer
    reached the scan, an owner would turn the toggle on and nothing would run."""
    import httpx

    from app.config import settings
    from app.main import app

    m = settings.maintenance
    original = (
        m.media_integrity_scan_enabled,
        m.media_integrity_scan_media,
        m.auto_purge_missing_clips,
        m.auto_purge_missing_snapshots,
        settings.auth.enabled,
    )
    settings.auth.enabled = False
    m.media_integrity_scan_enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/settings",
                json={"auto_purge_missing_clips": True, "auto_purge_missing_snapshots": True},
            )
            assert response.status_code == 200, response.text
        assert m.media_integrity_scan_enabled is True
        assert m.media_integrity_scan_media == "any"
    finally:
        (
            m.media_integrity_scan_enabled,
            m.media_integrity_scan_media,
            m.auto_purge_missing_clips,
            m.auto_purge_missing_snapshots,
            settings.auth.enabled,
        ) = original


@pytest.mark.asyncio
async def test_writing_the_new_toggle_keeps_the_legacy_pair_truthful():
    """A client reading only the old fields must not be told the scan is off."""
    import httpx

    from app.config import settings
    from app.main import app

    m = settings.maintenance
    original = (
        m.media_integrity_scan_enabled,
        m.auto_purge_missing_clips,
        m.auto_purge_missing_snapshots,
        settings.auth.enabled,
    )
    settings.auth.enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/settings", json={"media_integrity_scan_enabled": True})
            assert response.status_code == 200, response.text
        assert m.auto_purge_missing_clips is True
        assert m.auto_purge_missing_snapshots is True
    finally:
        (
            m.media_integrity_scan_enabled,
            m.auto_purge_missing_clips,
            m.auto_purge_missing_snapshots,
            settings.auth.enabled,
        ) = original
