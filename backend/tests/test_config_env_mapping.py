import json

import pytest

import app.config as config_module
from app.config import Settings
from app.config_loader import CLASSIFICATION_ENV_OVERRIDES


def test_llm_model_default_matches_current_ui_default(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.delenv("LLM__MODEL", raising=False)

    loaded = Settings.load()

    assert loaded.llm.model == "gemini-2.5-flash"


def test_classification_timeout_seconds_env_override(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS", "777")

    loaded = Settings.load()

    assert loaded.classification.video_classification_timeout_seconds == 777


def test_classification_stale_minutes_env_override(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES", "61")

    loaded = Settings.load()

    assert loaded.classification.video_classification_stale_minutes == 61


def test_classification_image_execution_mode_defaults_to_in_process(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.delenv("CLASSIFICATION__IMAGE_EXECUTION_MODE", raising=False)

    loaded = Settings.load()

    assert loaded.classification.image_execution_mode == "in_process"


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


CLASSIFICATION_ENV_PRECEDENCE_CASES = [
    ("write_frigate_sublabel", "CLASSIFICATION__WRITE_FRIGATE_SUBLABEL", "false", True, False),
    ("personalized_rerank_enabled", "CLASSIFICATION__PERSONALIZED_RERANK_ENABLED", "true", False, True),
    ("auto_video_classification", "CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION", "true", False, True),
    ("video_classification_delay", "CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY", "42", 30, 42),
    ("video_classification_max_retries", "CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES", "9", 3, 9),
    ("video_classification_retry_interval", "CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL", "21", 15, 21),
    ("video_classification_max_concurrent", "CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT", "7", 5, 7),
    ("video_classification_failure_threshold", "CLASSIFICATION__VIDEO_FAILURE_THRESHOLD", "11", 5, 11),
    (
        "video_classification_failure_window_minutes",
        "CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES",
        "22",
        10,
        22,
    ),
    (
        "video_classification_failure_cooldown_minutes",
        "CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES",
        "33",
        15,
        33,
    ),
    (
        "video_classification_timeout_seconds",
        "CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS",
        "777",
        180,
        777,
    ),
    ("video_classification_stale_minutes", "CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES", "61", 15, 61),
    ("video_classification_frames", "CLASSIFICATION__VIDEO_CLASSIFICATION_FRAMES", "25", 15, 25),
    ("strict_non_finite_output", "CLASSIFICATION__STRICT_NON_FINITE_OUTPUT", "false", True, False),
    ("strict_non_finite_output", "CLASSIFIER_STRICT_NON_FINITE_OUTPUT", "false", True, False),
    ("inference_provider", "CLASSIFICATION__INFERENCE_PROVIDER", "intel_cpu", "cpu", "intel_cpu"),
    ("inference_provider", "CLASSIFICATION__USE_CUDA", "true", "cpu", "cuda"),
    ("image_execution_mode", "CLASSIFICATION__IMAGE_EXECUTION_MODE", "subprocess", "in_process", "subprocess"),
    ("live_worker_count", "CLASSIFICATION__LIVE_WORKER_COUNT", "4", 2, 4),
    ("background_worker_count", "CLASSIFICATION__BACKGROUND_WORKER_COUNT", "3", 1, 3),
    (
        "worker_heartbeat_timeout_seconds",
        "CLASSIFICATION__WORKER_HEARTBEAT_TIMEOUT_SECONDS",
        "7.5",
        5.0,
        7.5,
    ),
    (
        "worker_hard_deadline_seconds",
        "CLASSIFICATION__WORKER_HARD_DEADLINE_SECONDS",
        "42.5",
        35.0,
        42.5,
    ),
    (
        "background_worker_hard_deadline_seconds",
        "CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS",
        "140.0",
        120.0,
        140.0,
    ),
    (
        "worker_ready_timeout_seconds",
        "CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS",
        "22.5",
        20.0,
        22.5,
    ),
    (
        "worker_restart_window_seconds",
        "CLASSIFICATION__WORKER_RESTART_WINDOW_SECONDS",
        "120.0",
        60.0,
        120.0,
    ),
    ("worker_restart_threshold", "CLASSIFICATION__WORKER_RESTART_THRESHOLD", "6", 3, 6),
    (
        "worker_breaker_cooldown_seconds",
        "CLASSIFICATION__WORKER_BREAKER_COOLDOWN_SECONDS",
        "90.0",
        60.0,
        90.0,
    ),
    ("live_event_stale_drop_seconds", "CLASSIFICATION__LIVE_EVENT_STALE_DROP_SECONDS", "45.0", 30.0, 45.0),
    (
        "live_event_coalescing_enabled",
        "CLASSIFICATION__LIVE_EVENT_COALESCING_ENABLED",
        "false",
        True,
        False,
    ),
    (
        "ai_pricing_json",
        "CLASSIFICATION__AI_PRICING_JSON",
        '[{"provider":"openai","model":"gpt-test","input_per_1k":0.001}]',
        "[]",
        '[{"provider":"openai","model":"gpt-test","input_per_1k":0.001}]',
    ),
    ("max_classification_results", "CLASSIFICATION__MAX_CLASSIFICATION_RESULTS", "9", 5, 9),
]


@pytest.mark.parametrize(
    "classification_key, env_key, env_value, file_value, expected_value",
    CLASSIFICATION_ENV_PRECEDENCE_CASES,
    ids=[case[1] for case in CLASSIFICATION_ENV_PRECEDENCE_CASES],
)
def test_classification_env_override_matrix(
    monkeypatch, tmp_path, classification_key, env_key, env_value, file_value, expected_value
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"classification": {classification_key: file_value}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setenv(env_key, env_value)

    loaded = Settings.load()

    assert getattr(loaded.classification, classification_key) == expected_value


def test_classification_override_matrix_covers_all_mapped_env_keys():
    covered_env_keys = {case[1] for case in CLASSIFICATION_ENV_PRECEDENCE_CASES}
    mapped_env_keys = {
        env_key
        for env_keys in CLASSIFICATION_ENV_OVERRIDES.values()
        for env_key in env_keys
    }
    assert covered_env_keys == mapped_env_keys


def test_classification_startup_load_env_precedence_with_full_file_payload(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "classification": {
                    "write_frigate_sublabel": True,
                    "personalized_rerank_enabled": False,
                    "auto_video_classification": False,
                    "video_classification_delay": 30,
                    "video_classification_max_retries": 3,
                    "video_classification_retry_interval": 15,
                    "video_classification_max_concurrent": 5,
                    "video_classification_failure_threshold": 5,
                    "video_classification_failure_window_minutes": 10,
                    "video_classification_failure_cooldown_minutes": 15,
                    "video_classification_timeout_seconds": 180,
                    "video_classification_stale_minutes": 15,
                    "video_classification_frames": 15,
                    "strict_non_finite_output": True,
                    "inference_provider": "cpu",
                    "image_execution_mode": "in_process",
                    "live_worker_count": 2,
                    "background_worker_count": 1,
                    "worker_heartbeat_timeout_seconds": 5.0,
                    "worker_hard_deadline_seconds": 35.0,
                    "background_worker_hard_deadline_seconds": 120.0,
                    "worker_ready_timeout_seconds": 20.0,
                    "worker_restart_window_seconds": 60.0,
                    "worker_restart_threshold": 3,
                    "worker_breaker_cooldown_seconds": 60.0,
                    "live_event_stale_drop_seconds": 30.0,
                    "live_event_coalescing_enabled": True,
                    "ai_pricing_json": "[]",
                    "max_classification_results": 5,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    monkeypatch.setenv("CLASSIFICATION__WRITE_FRIGATE_SUBLABEL", "false")
    monkeypatch.setenv("CLASSIFICATION__PERSONALIZED_RERANK_ENABLED", "true")
    monkeypatch.setenv("CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION", "true")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY", "44")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES", "8")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL", "22")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT", "9")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_FAILURE_THRESHOLD", "12")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES", "27")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES", "33")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS", "321")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES", "66")
    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_FRAMES", "31")
    monkeypatch.setenv("CLASSIFICATION__STRICT_NON_FINITE_OUTPUT", "false")
    monkeypatch.setenv("CLASSIFICATION__INFERENCE_PROVIDER", "intel_gpu")
    monkeypatch.setenv("CLASSIFICATION__USE_CUDA", "false")
    monkeypatch.setenv("CLASSIFICATION__IMAGE_EXECUTION_MODE", "subprocess")
    monkeypatch.setenv("CLASSIFICATION__LIVE_WORKER_COUNT", "4")
    monkeypatch.setenv("CLASSIFICATION__BACKGROUND_WORKER_COUNT", "2")
    monkeypatch.setenv("CLASSIFICATION__WORKER_HEARTBEAT_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("CLASSIFICATION__WORKER_HARD_DEADLINE_SECONDS", "42.5")
    monkeypatch.setenv("CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS", "140.0")
    monkeypatch.setenv("CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS", "22.5")
    monkeypatch.setenv("CLASSIFICATION__WORKER_RESTART_WINDOW_SECONDS", "120.0")
    monkeypatch.setenv("CLASSIFICATION__WORKER_RESTART_THRESHOLD", "6")
    monkeypatch.setenv("CLASSIFICATION__WORKER_BREAKER_COOLDOWN_SECONDS", "90.0")
    monkeypatch.setenv("CLASSIFICATION__LIVE_EVENT_STALE_DROP_SECONDS", "45.0")
    monkeypatch.setenv("CLASSIFICATION__LIVE_EVENT_COALESCING_ENABLED", "false")
    monkeypatch.setenv(
        "CLASSIFICATION__AI_PRICING_JSON",
        '[{"provider":"openai","model":"gpt-test","input_per_1k":0.001}]',
    )
    monkeypatch.setenv("CLASSIFICATION__MAX_CLASSIFICATION_RESULTS", "11")

    loaded = Settings.load()

    assert loaded.classification.write_frigate_sublabel is False
    assert loaded.classification.personalized_rerank_enabled is True
    assert loaded.classification.auto_video_classification is True
    assert loaded.classification.video_classification_delay == 44
    assert loaded.classification.video_classification_max_retries == 8
    assert loaded.classification.video_classification_retry_interval == 22
    assert loaded.classification.video_classification_max_concurrent == 9
    assert loaded.classification.video_classification_failure_threshold == 12
    assert loaded.classification.video_classification_failure_window_minutes == 27
    assert loaded.classification.video_classification_failure_cooldown_minutes == 33
    assert loaded.classification.video_classification_timeout_seconds == 321
    assert loaded.classification.video_classification_stale_minutes == 66
    assert loaded.classification.video_classification_frames == 31
    assert loaded.classification.strict_non_finite_output is False
    assert loaded.classification.inference_provider == "intel_gpu"
    assert loaded.classification.image_execution_mode == "subprocess"
    assert loaded.classification.live_worker_count == 4
    assert loaded.classification.background_worker_count == 2
    assert loaded.classification.worker_heartbeat_timeout_seconds == 7.5
    assert loaded.classification.worker_hard_deadline_seconds == 42.5
    assert loaded.classification.background_worker_hard_deadline_seconds == 140.0
    assert loaded.classification.worker_ready_timeout_seconds == 22.5
    assert loaded.classification.worker_restart_window_seconds == 120.0
    assert loaded.classification.worker_restart_threshold == 6
    assert loaded.classification.worker_breaker_cooldown_seconds == 90.0
    assert loaded.classification.live_event_stale_drop_seconds == 45.0
    assert loaded.classification.live_event_coalescing_enabled is False
    assert loaded.classification.ai_pricing_json == '[{"provider":"openai","model":"gpt-test","input_per_1k":0.001}]'
    assert loaded.classification.max_classification_results == 11


def test_legacy_location_temperature_unit_migrates_to_weather_unit_system(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "frigate": {"frigate_url": "http://frigate:5000"},
                "location": {"temperature_unit": "fahrenheit"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    loaded = Settings.load()

    assert loaded.location.weather_unit_system == "imperial"
    assert loaded.location.temperature_unit == "fahrenheit"


def test_media_cache_high_quality_event_snapshots_env_override(monkeypatch):
    monkeypatch.setenv("MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS", "true")

    loaded = Settings.load()

    assert loaded.media_cache.high_quality_event_snapshots is True


def test_media_cache_high_quality_event_snapshots_env_overrides_file_value(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "media_cache": {
                    "high_quality_event_snapshots": False,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setenv("MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS", "true")

    loaded = Settings.load()

    assert loaded.media_cache.high_quality_event_snapshots is True


def test_media_cache_high_quality_event_snapshot_jpeg_quality_env_override(monkeypatch):
    monkeypatch.setenv("MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOT_JPEG_QUALITY", "82")

    loaded = Settings.load()

    assert loaded.media_cache.high_quality_event_snapshot_jpeg_quality == 82


def test_media_cache_high_quality_event_snapshot_jpeg_quality_env_overrides_file_value(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "media_cache": {
                    "high_quality_event_snapshot_jpeg_quality": 95,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setenv("MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOT_JPEG_QUALITY", "81")

    loaded = Settings.load()

    assert loaded.media_cache.high_quality_event_snapshot_jpeg_quality == 81
