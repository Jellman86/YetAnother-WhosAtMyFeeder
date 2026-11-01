from pathlib import Path

from app.config import Settings
from app.config_loader import load_settings_instance


def test_generated_auth_secret_only_config_still_needs_first_run(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"auth": {"session_secret": "generated", "oauth_token_secret": "generated-oauth"}}',
        encoding="utf-8",
    )

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.auth.initial_setup_complete is False
    assert loaded.auth.password_hash is None


def test_legacy_real_config_counts_as_setup_complete(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"auth": {"session_secret": "generated"}, "frigate": {"url": "http://frigate:5000"}}',
        encoding="utf-8",
    )

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.auth.initial_setup_complete is True


def test_legacy_config_without_auth_section_counts_as_setup_complete(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"frigate": {"frigate_url": "http://frigate:5000"}}',
        encoding="utf-8",
    )

    loaded = load_settings_instance(Settings, config_path)

    assert loaded.auth.initial_setup_complete is True
