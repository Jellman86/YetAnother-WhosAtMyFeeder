import json

import httpx
import pytest
import pytest_asyncio

import app.config as config_module
from app.config import Settings, settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


@pytest.mark.asyncio
async def test_settings_roundtrip_personalized_rerank_enabled(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "personalized_rerank_enabled" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "personalized_rerank_enabled": True,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["personalized_rerank_enabled"] is True


@pytest.mark.asyncio
async def test_settings_rejects_enabling_auth_without_password(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.password_hash = None
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "auth_enabled": True,
        "auth_username": "root",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 422, post_resp.text
    assert "Password is required when enabling authentication" in post_resp.text


@pytest.mark.asyncio
async def test_settings_allows_enabling_auth_with_password(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.password_hash = None
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "auth_enabled": True,
        "auth_username": "root",
        "auth_password": "root1234",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text
    assert settings.auth.enabled is True
    assert settings.auth.username == "root"
    assert settings.auth.password_hash is not None


@pytest.mark.asyncio
async def test_settings_roundtrip_strict_non_finite_output(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "strict_non_finite_output" in before_payload

    original_value = bool(before_payload["strict_non_finite_output"])
    updated_value = not original_value

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "strict_non_finite_output": updated_value,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["strict_non_finite_output"] is updated_value

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "strict_non_finite_output": original_value,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_bird_model_region_override(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "bird_model_region_override" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "bird_model_region_override": "eu",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["bird_model_region_override"] == "eu"

    invalid_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "bird_model_region_override": "not-real",
    }
    invalid_resp = await client.post("/api/settings", json=invalid_payload)
    assert invalid_resp.status_code == 200, invalid_resp.text

    get_invalid = await client.get("/api/settings")
    assert get_invalid.status_code == 200, get_invalid.text
    invalid_after_payload = get_invalid.json()
    assert invalid_after_payload["bird_model_region_override"] == "auto"

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "bird_model_region_override": "auto",
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_crop_overrides(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "crop_model_overrides" in before_payload
    assert "crop_source_overrides" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "crop_model_overrides": {
            "small_birds": "off",
            "small_birds.na": "on",
            "bad-entry": "not-real",
        },
        "crop_source_overrides": {
            "small_birds": "high_quality",
            "small_birds.na": "standard",
            "also-bad": "whatever",
        },
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["crop_model_overrides"] == {
        "small_birds": "off",
        "small_birds.na": "on",
        "bad-entry": "default",
    }
    assert after_payload["crop_source_overrides"] == {
        "small_birds": "high_quality",
        "small_birds.na": "standard",
        "also-bad": "default",
    }

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.classification.crop_model_overrides == {
        "small_birds": "off",
        "small_birds.na": "on",
        "bad-entry": "default",
    }
    assert reloaded_from_file.classification.crop_source_overrides == {
        "small_birds": "high_quality",
        "small_birds.na": "standard",
        "also-bad": "default",
    }

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["classification"]["crop_model_overrides"] == {
        "small_birds": "off",
        "small_birds.na": "on",
        "bad-entry": "default",
    }
    assert persisted_json["classification"]["crop_source_overrides"] == {
        "small_birds": "high_quality",
        "small_birds.na": "standard",
        "also-bad": "default",
    }

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "crop_model_overrides": before_payload["crop_model_overrides"],
        "crop_source_overrides": before_payload["crop_source_overrides"],
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_blocked_species(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "blocked_species" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "blocked_species": [
            {
                "scientific_name": "Columba livia",
                "common_name": "Rock Pigeon",
                "taxa_id": 3017,
            }
        ],
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["blocked_species"] == [
        {
            "scientific_name": "Columba livia",
            "common_name": "Rock Pigeon",
            "taxa_id": 3017,
        }
    ]

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "blocked_species": before_payload["blocked_species"],
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_recording_clip_fields(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "recording_clip_enabled" in before_payload
    assert "recording_clip_before_seconds" in before_payload
    assert "recording_clip_after_seconds" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "recording_clip_enabled": True,
        "recording_clip_before_seconds": 45,
        "recording_clip_after_seconds": 150,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["recording_clip_enabled"] is True
    assert after_payload["recording_clip_before_seconds"] == 45
    assert after_payload["recording_clip_after_seconds"] == 150

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "recording_clip_enabled": before_payload["recording_clip_enabled"],
        "recording_clip_before_seconds": before_payload["recording_clip_before_seconds"],
        "recording_clip_after_seconds": before_payload["recording_clip_after_seconds"],
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_update_persists_classification_delay_and_env_precedence(
    client: httpx.AsyncClient, monkeypatch
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    monkeypatch.delenv("CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY", raising=False)

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()
    original_delay = before_payload["video_classification_delay"]
    updated_delay = 91 if original_delay != 91 else 92

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "video_classification_delay": updated_delay,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.classification.video_classification_delay == updated_delay

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["classification"]["video_classification_delay"] == updated_delay

    monkeypatch.setenv("CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY", "17")
    reloaded_with_env = Settings.load()
    assert reloaded_with_env.classification.video_classification_delay == 17

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "video_classification_delay": original_delay,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_video_classification_max_concurrent(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "video_classification_max_concurrent" in before_payload

    original_limit = before_payload["video_classification_max_concurrent"]
    updated_limit = 7 if original_limit != 7 else 8

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "video_classification_max_concurrent": updated_limit,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["video_classification_max_concurrent"] == updated_limit

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "video_classification_max_concurrent": original_limit,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_media_cache_high_quality_event_snapshots(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "media_cache_high_quality_event_snapshots" in before_payload

    original_value = before_payload["media_cache_high_quality_event_snapshots"]
    updated_value = not original_value

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshots": updated_value,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["media_cache_high_quality_event_snapshots"] is updated_value

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.media_cache.high_quality_event_snapshots is updated_value

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["media_cache"]["high_quality_event_snapshots"] is updated_value

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshots": original_value,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_media_cache_high_quality_event_snapshot_jpeg_quality(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "media_cache_high_quality_event_snapshot_jpeg_quality" in before_payload

    original_value = before_payload["media_cache_high_quality_event_snapshot_jpeg_quality"]
    updated_value = 82 if original_value != 82 else 90

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshot_jpeg_quality": updated_value,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["media_cache_high_quality_event_snapshot_jpeg_quality"] == updated_value

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.media_cache.high_quality_event_snapshot_jpeg_quality == updated_value

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["media_cache"]["high_quality_event_snapshot_jpeg_quality"] == updated_value

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshot_jpeg_quality": original_value,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_location_weather_unit_system(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "location_weather_unit_system" in before_payload

    original_value = before_payload["location_weather_unit_system"]
    updated_value = "imperial" if original_value != "imperial" else "metric"

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "location_weather_unit_system": updated_value,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["location_weather_unit_system"] == updated_value

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.location.weather_unit_system == updated_value

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["location"]["weather_unit_system"] == updated_value

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "location_weather_unit_system": original_value,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_roundtrip_location_state_and_country(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "location_state" in before_payload
    assert "location_country" in before_payload

    original_state = before_payload["location_state"]
    original_country = before_payload["location_country"]

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "location_state": "California",
        "location_country": "United States",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["location_state"] == "California"
    assert after_payload["location_country"] == "United States"

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.location.state == "California"
    assert reloaded_from_file.location.country == "United States"

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["location"]["state"] == "California"
    assert persisted_json["location"]["country"] == "United States"

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "location_state": original_state,
        "location_country": original_country,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_patch, expected_field",
    [
        ({"inference_provider": "gpu_magic"}, "inference_provider"),
        ({"classification_threshold": 1.5}, "classification_threshold"),
        ({"video_classification_frames": 3}, "video_classification_frames"),
        ({"video_classification_max_concurrent": 0}, "video_classification_max_concurrent"),
    ],
)
async def test_settings_update_rejects_invalid_classification_payload(
    client: httpx.AsyncClient, invalid_patch: dict, expected_field: str
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
    }
    payload.update(invalid_patch)

    post_resp = await client.post("/api/settings", json=payload)
    assert post_resp.status_code == 422, post_resp.text
    detail = post_resp.json().get("detail", [])
    assert any(item.get("loc", [])[-1] == expected_field for item in detail)
