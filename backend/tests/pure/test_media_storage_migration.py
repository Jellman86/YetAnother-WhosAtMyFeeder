"""Photos and visit media stopped being optional (#622).

The "Media Cache" and "Snapshots" switches are gone. An install that had either off must not
wake up after the upgrade storing far more than before: the high-quality full frames cost about
4 MB a visit and full-visit clips about 25 MB, against about 0.3 MB for the basic photographs.
So the upgrade turns off what those switches had been silently suppressing, once, and leaves
every later choice alone.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.config_loader import load_settings_instance

LEGACY_ENV = (
    "MEDIA_CACHE__ENABLED",
    "MEDIA_CACHE__CACHE_SNAPSHOTS",
    "MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS",
    "FRIGATE__RECORDING_CLIP_ENABLED",
)


@pytest.fixture(autouse=True)
def _clear_media_env(monkeypatch):
    for name in LEGACY_ENV:
        monkeypatch.delenv(name, raising=False)


def _load(tmp_path: Path, config: dict) -> Settings:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return load_settings_instance(Settings, path)


def test_the_switches_are_no_longer_settings():
    assert "enabled" not in Settings.model_fields["media_cache"].annotation.model_fields
    assert "cache_snapshots" not in Settings.model_fields["media_cache"].annotation.model_fields


def test_a_fresh_install_is_marked_migrated_and_keeps_its_defaults(tmp_path: Path):
    loaded = load_settings_instance(Settings, tmp_path / "config.json")

    assert loaded.media_cache.storage_controls_migrated is True
    assert loaded.media_cache.high_quality_event_snapshot_jpeg_quality == 90


def test_an_install_with_everything_on_is_unchanged(tmp_path: Path):
    loaded = _load(
        tmp_path,
        {
            "media_cache": {"enabled": True, "cache_snapshots": True, "high_quality_event_snapshots": True},
            "frigate": {"recording_clip_enabled": True},
        },
    )

    assert loaded.media_cache.high_quality_event_snapshots is True
    assert loaded.frigate.recording_clip_enabled is True
    assert loaded.media_cache.storage_controls_migrated is True


def test_photos_off_turns_off_the_high_quality_frames_it_was_suppressing(tmp_path: Path):
    loaded = _load(
        tmp_path,
        {
            "media_cache": {"enabled": True, "cache_snapshots": False, "high_quality_event_snapshots": True},
            "frigate": {"recording_clip_enabled": True},
        },
    )

    assert loaded.media_cache.high_quality_event_snapshots is False
    # Video was never suppressed by the photo switch, so it is left alone.
    assert loaded.frigate.recording_clip_enabled is True


def test_the_cache_off_turns_off_high_quality_frames_and_full_visit_clips(tmp_path: Path):
    loaded = _load(
        tmp_path,
        {
            "media_cache": {"enabled": False, "high_quality_event_snapshots": True},
            "frigate": {"recording_clip_enabled": True},
        },
    )

    assert loaded.media_cache.high_quality_event_snapshots is False
    assert loaded.frigate.recording_clip_enabled is False


def test_legacy_switches_set_by_environment_variable_migrate_too(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_CACHE__ENABLED", "false")

    loaded = _load(
        tmp_path,
        {"media_cache": {"high_quality_event_snapshots": True}, "frigate": {"recording_clip_enabled": True}},
    )

    assert loaded.media_cache.high_quality_event_snapshots is False
    assert loaded.frigate.recording_clip_enabled is False


def test_an_explicit_environment_variable_is_never_migrated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS", "true")
    monkeypatch.setenv("FRIGATE__RECORDING_CLIP_ENABLED", "true")

    loaded = _load(tmp_path, {"media_cache": {"enabled": False}})

    assert loaded.media_cache.high_quality_event_snapshots is True
    assert loaded.frigate.recording_clip_enabled is True


def test_a_choice_made_after_the_migration_is_kept(tmp_path: Path):
    # Saved after the upgrade: the legacy keys are gone and the marker is set.
    loaded = _load(
        tmp_path,
        {
            "media_cache": {"storage_controls_migrated": True, "high_quality_event_snapshots": True},
            "frigate": {"recording_clip_enabled": True},
        },
    )

    assert loaded.media_cache.high_quality_event_snapshots is True
    assert loaded.frigate.recording_clip_enabled is True


def test_a_saved_config_carries_the_marker_and_not_the_legacy_switches(tmp_path: Path):
    loaded = _load(tmp_path, {"media_cache": {"enabled": False, "cache_snapshots": False}})

    saved = json.loads(loaded.model_dump_json())["media_cache"]

    assert saved["storage_controls_migrated"] is True
    assert "enabled" not in saved
    assert "cache_snapshots" not in saved


def test_restoring_a_backup_from_before_the_upgrade_migrates_it_too():
    from app.config_loader import migrate_imported_media_controls

    backup = {
        "media_cache": {"enabled": False, "high_quality_event_snapshots": True},
        "frigate": {"frigate_url": "http://frigate:5000", "recording_clip_enabled": True},
    }
    migrate_imported_media_controls(backup)
    restored = Settings.model_validate(backup)

    assert restored.media_cache.high_quality_event_snapshots is False
    assert restored.frigate.recording_clip_enabled is False
    assert restored.media_cache.storage_controls_migrated is True
    assert "enabled" not in backup["media_cache"]


def test_restoring_a_backup_from_after_the_upgrade_is_left_as_it_was():
    from app.config_loader import migrate_imported_media_controls

    backup = {
        "media_cache": {"storage_controls_migrated": True, "high_quality_event_snapshots": True},
        "frigate": {"frigate_url": "http://frigate:5000", "recording_clip_enabled": True},
    }
    migrate_imported_media_controls(backup)
    restored = Settings.model_validate(backup)

    assert restored.media_cache.high_quality_event_snapshots is True
    assert restored.frigate.recording_clip_enabled is True


def test_the_warning_says_where_each_retired_switch_was_set_and_how_to_clear_it(tmp_path: Path, monkeypatch):
    from structlog.testing import capture_logs

    monkeypatch.setenv("MEDIA_CACHE__ENABLED", "true")
    with capture_logs() as logs:
        _load(tmp_path, {"media_cache": {"cache_snapshots": True}})

    warning = next(entry for entry in logs if entry["event"].startswith("Retired media switches"))
    assert warning["found"] == ["media_cache.cache_snapshots in config.json", "MEDIA_CACHE__ENABLED"]
    assert warning["turned_off"] == []
    assert "Saving settings once removes them from config.json" in warning["hint"]
