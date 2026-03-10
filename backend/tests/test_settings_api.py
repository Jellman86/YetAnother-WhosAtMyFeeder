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
