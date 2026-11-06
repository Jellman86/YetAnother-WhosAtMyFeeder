from pathlib import Path

import pytest

from app.config import Settings
from app.config_loader import load_settings_instance


@pytest.fixture(autouse=True)
def _clear_color_theme_env(monkeypatch):
    # The colour theme migration only runs when the value is not pinned by env.
    monkeypatch.delenv("APPEARANCE__COLOR_THEME", raising=False)


def test_fresh_install_defaults_to_bluetit(tmp_path: Path):
    config_path = tmp_path / "config.json"  # does not exist

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.appearance.color_theme == "bluetit"


def test_legacy_default_is_migrated_to_bluetit(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"appearance": {"color_theme": "default"}}', encoding="utf-8")

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.appearance.color_theme == "bluetit"
    # Marker is set so the migration is one-time and gets persisted on next save.
    assert loaded.appearance.color_theme_default_migrated is True


def test_deliberate_teal_after_migration_is_preserved(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"appearance": {"color_theme": "default", "color_theme_default_migrated": true}}',
        encoding="utf-8",
    )

    loaded = load_settings_instance(Settings, config_path)

    # Once migrated, "default" (teal) is a valid deliberate choice and must stick.
    assert loaded.appearance.color_theme == "default"


def test_existing_bluetit_is_unchanged(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"appearance": {"color_theme": "bluetit"}}', encoding="utf-8")

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.appearance.color_theme == "bluetit"


def test_env_var_is_authoritative_and_not_migrated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPEARANCE__COLOR_THEME", "default")
    config_path = tmp_path / "config.json"
    config_path.write_text('{"appearance": {"color_theme": "bluetit"}}', encoding="utf-8")

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.appearance.color_theme == "default"
