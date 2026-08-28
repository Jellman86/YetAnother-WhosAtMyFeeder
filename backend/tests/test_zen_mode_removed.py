"""Zen mode is gone, and an install that carries it still starts.

The setting shipped as a toggle in Settings > Accessibility that saved,
reported success, and changed nothing: it added a `zen-mode` class to the
document root, and no stylesheet in the app has ever had a rule for that
class. The effect that added it also lived on the Settings page, so the class
was dropped again on navigating away. An accessibility control that claims an
effect it does not have is worse than no control (CLAUDE.md section 5).

Removing a released setting touches user data, so the load path is pinned
here: a `config.json` written by an older version still names `zen_mode`, and
that file must keep loading with the rest of its accessibility block intact.
"""

from pathlib import Path

import httpx
import pytest

from app.config import Settings, settings
from app.config_loader import load_settings_instance
from app.config_models import AccessibilitySettings
from app.main import app
from app.routers.settings import SettingsUpdate


def test_the_setting_is_gone():
    assert "zen_mode" not in AccessibilitySettings.model_fields


def test_the_api_no_longer_offers_it():
    assert "accessibility_zen_mode" not in SettingsUpdate.model_fields


def test_an_existing_config_that_still_names_zen_mode_loads(tmp_path: Path):
    """The upgrade must not strand anyone on an unreadable config."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"accessibility": {"zen_mode": true, "high_contrast": true, "dyslexia_font": true}}',
        encoding="utf-8",
    )

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.accessibility.high_contrast is True
    assert loaded.accessibility.dyslexia_font is True
    assert not hasattr(loaded.accessibility, "zen_mode")


@pytest.mark.asyncio
async def test_a_client_still_sending_zen_mode_is_not_refused():
    """An older browser tab holding the previous form must not fail to save."""
    original = (settings.auth.enabled, settings.accessibility.high_contrast)
    settings.auth.enabled = False
    settings.accessibility.high_contrast = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/settings",
                json={"accessibility_zen_mode": True, "accessibility_high_contrast": True},
            )
        assert response.status_code == 200, response.text
        assert settings.accessibility.high_contrast is True
        assert "accessibility_zen_mode" not in response.json()
    finally:
        settings.auth.enabled, settings.accessibility.high_contrast = original


def test_a_backup_taken_before_the_removal_still_imports():
    """Restore is a user-data path: an older backup must not be refused.

    `/api/settings/import` validates the whole payload through `Settings`, so a
    backup file written by a version that still had zen mode has to validate
    with the field simply ignored.
    """
    from app.config import Settings as AppSettings

    # A real backup is the whole config, so start from one and put the retired
    # key back exactly where an older version would have written it.
    backup = settings.model_dump()
    backup["accessibility"] = {**backup["accessibility"], "zen_mode": True}
    backup["accessibility"]["reduced_motion"] = True
    backup["accessibility"]["high_contrast"] = True

    imported = AppSettings.model_validate(backup)

    assert imported.accessibility.reduced_motion is True
    assert imported.accessibility.high_contrast is True
    assert not hasattr(imported.accessibility, "zen_mode")
