import json

import app.config as config_module
from app.config import Settings


def test_classification_timeout_seconds_env_override(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS", "777")

    loaded = Settings.load()

    assert loaded.classification.video_classification_timeout_seconds == 777


def test_classification_stale_minutes_env_override(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES", "61")

    loaded = Settings.load()

    assert loaded.classification.video_classification_stale_minutes == 61


def test_notification_cooldown_env_override(monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES", "13")

    loaded = Settings.load()

    assert loaded.notifications.notification_cooldown_minutes == 13


def test_classification_env_overrides_file_values(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "classification": {
                    "video_classification_timeout_seconds": 180,
                    "video_classification_stale_minutes": 15,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS", "777")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES", "61")

    loaded = Settings.load()

    assert loaded.classification.video_classification_timeout_seconds == 777
    assert loaded.classification.video_classification_stale_minutes == 61
