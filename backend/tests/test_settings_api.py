import json

import httpx
import pytest
import pytest_asyncio

import app.config as config_module
from app.config import Settings, settings
from app.main import app
from app.routers import settings as settings_router
from app.routers import backfill as backfill_router
from app.services.maintenance_coordinator import maintenance_coordinator


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_video_classification_max_concurrent = settings.classification.video_classification_max_concurrent
    original_maintenance_max_concurrent = settings.maintenance.max_concurrent
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.classification.video_classification_max_concurrent = original_video_classification_max_concurrent
    settings.maintenance.max_concurrent = original_maintenance_max_concurrent


@pytest_asyncio.fixture(autouse=True)
async def reset_maintenance_coordinator():
    await maintenance_coordinator.reset()
    yield
    await maintenance_coordinator.reset()


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
async def test_settings_roundtrip_frigate_missing_behavior(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "frigate_missing_behavior" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "frigate_missing_behavior": "keep",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["frigate_missing_behavior"] == "keep"


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
async def test_analysis_status_is_not_cacheable(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    response = await client.get("/api/maintenance/analysis/status")
    assert response.status_code == 200, response.text
    assert response.headers.get("Cache-Control") == "no-store, max-age=0"
    assert response.headers.get("Pragma") == "no-cache"


@pytest.mark.asyncio
async def test_analyze_unknowns_coalesces_when_maintenance_video_is_already_in_progress(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    def _busy_status():
        return {
            "pending": 6,
            "active": 1,
            "circuit_open": False,
            "maintenance_circuit_open": False,
            "maintenance_state": "deprioritized",
            "maintenance_status_message": "Maintenance video analysis is already in progress.",
            "pending_maintenance": 6,
            "active_maintenance": 1,
            "oldest_maintenance_pending_age_seconds": 22.0,
            "maintenance_starvation_relief_active": False,
            "throttled_for_live_pressure": True,
            "throttled_for_mqtt_pressure": False,
            "live_pressure_active": True,
            "live_in_flight": 2,
            "live_queued": 5,
            "mqtt_in_flight": 0,
            "mqtt_in_flight_capacity": 200,
            "max_concurrent_configured": 4,
            "max_concurrent_effective": 0,
            "mqtt_pressure_level": "normal",
        }

    async def _unexpected_run():
        raise AssertionError("analyze unknowns should have been coalesced")

    monkeypatch.setattr(
        settings_router.auto_video_classifier,
        "get_maintenance_guardrail_status",
        _busy_status,
    )
    monkeypatch.setattr(settings_router, "_run_analyze_unknowns", _unexpected_run)

    response = await client.post("/api/maintenance/analyze-unknowns")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "in_progress"
    assert "already in progress" in payload["message"].lower()


@pytest.mark.asyncio
async def test_taxonomy_sync_rejects_when_maintenance_pressure_is_high(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    monkeypatch.setattr(
        settings_router.canonical_identity_repair_service,
        "get_status",
        lambda: {"is_running": False, "processed": 0, "total": 0, "current_item": None, "error": None},
    )
    monkeypatch.setattr(
        settings_router.auto_video_classifier,
        "get_maintenance_guardrail_status",
        lambda: {
            "pending": 28,
            "active": 1,
            "circuit_open": False,
            "maintenance_circuit_open": False,
            "maintenance_state": "stalled",
            "maintenance_status_message": "Maintenance work is already heavily backlogged.",
            "pending_maintenance": 28,
            "active_maintenance": 1,
            "oldest_maintenance_pending_age_seconds": 91.0,
            "maintenance_starvation_relief_active": True,
            "throttled_for_live_pressure": True,
            "throttled_for_mqtt_pressure": False,
            "live_pressure_active": True,
            "live_in_flight": 2,
            "live_queued": 4,
            "mqtt_in_flight": 0,
            "mqtt_in_flight_capacity": 200,
            "max_concurrent_configured": 4,
            "max_concurrent_effective": 1,
            "mqtt_pressure_level": "normal",
        },
    )

    response = await client.post("/api/maintenance/taxonomy/sync")
    assert response.status_code == 409, response.text
    assert "backlogged" in response.text.lower()


@pytest.mark.asyncio
async def test_backfill_async_rejects_when_taxonomy_sync_is_running(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()
    backfill_router._JOB_TASKS.clear()

    monkeypatch.setattr(
        backfill_router.canonical_identity_repair_service,
        "get_status",
        lambda: {
            "is_running": True,
            "processed": 12,
            "total": 50,
            "current_item": "Blue Tit",
            "error": None,
        },
    )
    monkeypatch.setattr(
        backfill_router.auto_video_classifier,
        "get_maintenance_guardrail_status",
        lambda: {
            "pending": 0,
            "active": 0,
            "circuit_open": False,
            "maintenance_circuit_open": False,
            "maintenance_state": "idle",
            "maintenance_status_message": "",
            "pending_maintenance": 0,
            "active_maintenance": 0,
            "oldest_maintenance_pending_age_seconds": None,
            "maintenance_starvation_relief_active": False,
            "throttled_for_live_pressure": False,
            "throttled_for_mqtt_pressure": False,
            "live_pressure_active": False,
            "live_in_flight": 0,
            "live_queued": 0,
            "mqtt_in_flight": 0,
            "mqtt_in_flight_capacity": 200,
            "max_concurrent_configured": 4,
            "max_concurrent_effective": 4,
            "mqtt_pressure_level": "normal",
        },
    )

    response = await client.post("/api/backfill/async", json={"date_range": "week"})
    assert response.status_code == 409, response.text
    assert "taxonomy" in response.text.lower()


@pytest.mark.asyncio
async def test_taxonomy_sync_derives_reject_new_work_from_partial_guardrail_payload(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    monkeypatch.setattr(
        settings_router.canonical_identity_repair_service,
        "get_status",
        lambda: {"is_running": False, "processed": 0, "total": 0, "current_item": None, "error": None},
    )
    monkeypatch.setattr(
        settings_router.auto_video_classifier,
        "get_maintenance_guardrail_status",
        lambda: {
            "maintenance_state": "stalled",
            "maintenance_status_message": "Maintenance work is already heavily backlogged.",
            "pending_maintenance": 5,
            "active_maintenance": 1,
            "oldest_maintenance_pending_age_seconds": 91.0,
            "maintenance_circuit_open": False,
        },
    )

    response = await client.post("/api/maintenance/taxonomy/sync")
    assert response.status_code == 409, response.text
    assert "backlogged" in response.text.lower()


@pytest.mark.asyncio
async def test_backfill_async_rejects_when_maintenance_pressure_is_high(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()
    backfill_router._JOB_TASKS.clear()

    monkeypatch.setattr(
        backfill_router.canonical_identity_repair_service,
        "get_status",
        lambda: {
            "is_running": False,
            "processed": 0,
            "total": 0,
            "current_item": None,
            "error": None,
        },
    )
    monkeypatch.setattr(
        backfill_router.auto_video_classifier,
        "get_maintenance_guardrail_status",
        lambda: {
            "maintenance_state": "stalled",
            "maintenance_status_message": "Maintenance work is already heavily backlogged.",
            "pending_maintenance": 12,
            "active_maintenance": 1,
            "oldest_maintenance_pending_age_seconds": 91.0,
            "maintenance_circuit_open": False,
        },
    )

    response = await client.post("/api/backfill/async", json={"date_range": "week"})
    assert response.status_code == 409, response.text
    assert "backlogged" in response.text.lower()


@pytest.mark.asyncio
async def test_backfill_async_rejects_when_same_kind_maintenance_slot_is_occupied(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    # Issue #33: capacity is now per-kind, so only a concurrent *backfill*
    # holder should block a new /api/backfill/async request. A holder on a
    # different kind (e.g. taxonomy_sync) must no longer block it.
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.video_classification_max_concurrent = 2
    settings.maintenance.max_concurrent = 1
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()
    backfill_router._JOB_TASKS.clear()

    monkeypatch.setattr(
        backfill_router.canonical_identity_repair_service,
        "get_status",
        lambda: {
            "is_running": False,
            "processed": 0,
            "total": 0,
            "current_item": None,
            "error": None,
        },
    )

    acquired = await maintenance_coordinator.try_acquire("test-maintenance-slot", kind="backfill")
    assert acquired is True
    try:
        response = await client.post("/api/backfill/async", json={"date_range": "week"})
        assert response.status_code == 409, response.text
        assert "maintenance work is running" in response.text.lower()
    finally:
        await maintenance_coordinator.release("test-maintenance-slot")


@pytest.mark.asyncio
async def test_backfill_async_proceeds_when_a_different_kind_is_running(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    # Regression for issue #33: a long-running video_classification holder
    # used to pin the single global maintenance slot and block user-initiated
    # backfill indefinitely. Per-kind capacity means different kinds are
    # independent.
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.video_classification_max_concurrent = 2
    settings.maintenance.max_concurrent = 1
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()
    backfill_router._JOB_TASKS.clear()

    monkeypatch.setattr(
        backfill_router.canonical_identity_repair_service,
        "get_status",
        lambda: {
            "is_running": False,
            "processed": 0,
            "total": 0,
            "current_item": None,
            "error": None,
        },
    )

    acquired = await maintenance_coordinator.try_acquire(
        "test-video-slot", kind="video_classification"
    )
    assert acquired is True
    try:
        response = await client.post("/api/backfill/async", json={"date_range": "week"})
        # The request should be accepted — a concurrent video_classification
        # holder must not block a backfill kick-off.
        assert response.status_code != 409, response.text
    finally:
        await maintenance_coordinator.release("test-video-slot")


@pytest.mark.asyncio
async def test_analyze_unknowns_coalesces_when_same_kind_slot_is_occupied(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.video_classification_max_concurrent = 2
    settings.maintenance.max_concurrent = 1

    async def _unexpected_run():
        raise AssertionError("analyze unknowns should have been coalesced")

    monkeypatch.setattr(settings_router, "_run_analyze_unknowns", _unexpected_run)

    acquired = await maintenance_coordinator.try_acquire(
        "test-maintenance-slot", kind="analyze_unknowns"
    )
    assert acquired is True
    try:
        response = await client.post("/api/maintenance/analyze-unknowns")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "in_progress"
        assert "already in progress" in payload["message"].lower()
    finally:
        await maintenance_coordinator.release("test-maintenance-slot")


@pytest.mark.asyncio
async def test_timezone_repair_preview_rejects_when_same_kind_slot_is_occupied(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.video_classification_max_concurrent = 2
    settings.maintenance.max_concurrent = 1

    acquired = await maintenance_coordinator.try_acquire(
        "test-maintenance-slot", kind="timezone_repair"
    )
    assert acquired is True
    try:
        response = await client.get("/api/maintenance/timezone-repair/preview")
        assert response.status_code == 409, response.text
        assert "maintenance work is running" in response.text.lower()
    finally:
        await maintenance_coordinator.release("test-maintenance-slot")


@pytest.mark.asyncio
async def test_timezone_repair_apply_rejects_when_same_kind_slot_is_occupied(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.video_classification_max_concurrent = 2
    settings.maintenance.max_concurrent = 1

    acquired = await maintenance_coordinator.try_acquire(
        "test-maintenance-slot", kind="timezone_repair"
    )
    assert acquired is True
    try:
        response = await client.post("/api/maintenance/timezone-repair/apply", json={"confirm": True})
        assert response.status_code == 409, response.text
        assert "maintenance work is running" in response.text.lower()
    finally:
        await maintenance_coordinator.release("test-maintenance-slot")


@pytest.mark.asyncio
async def test_maintenance_coordinator_rejects_duplicate_holder_acquire():
    acquired = await maintenance_coordinator.try_acquire("dup-holder", kind="backfill")
    assert acquired is True
    try:
        acquired_again = await maintenance_coordinator.try_acquire("dup-holder", kind="backfill")
        assert acquired_again is False
    finally:
        await maintenance_coordinator.release("dup-holder")


@pytest.mark.asyncio
async def test_settings_roundtrip_maintenance_max_concurrent(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "maintenance_max_concurrent" in before_payload
    original_limit = before_payload["maintenance_max_concurrent"]

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "maintenance_max_concurrent": 2,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["maintenance_max_concurrent"] == 2

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "maintenance_max_concurrent": original_limit,
    }
    restore_resp = await client.post("/api/settings", json=restore_payload)
    assert restore_resp.status_code == 200, restore_resp.text


@pytest.mark.asyncio
async def test_settings_include_maintenance_video_circuit_fields_and_reset_reports_both(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_resp = await client.get("/api/settings")
    assert get_resp.status_code == 200, get_resp.text
    payload = get_resp.json()

    assert "video_classification_maintenance_circuit_open" in payload
    assert "video_classification_maintenance_circuit_until" in payload
    assert "video_classification_maintenance_circuit_failures" in payload

    reset_resp = await client.post("/api/maintenance/video-classification/reset-circuit")
    assert reset_resp.status_code == 200, reset_resp.text
    reset_payload = reset_resp.json()
    assert "live_circuit" in reset_payload
    assert "maintenance_circuit" in reset_payload


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
async def test_settings_roundtrip_notification_species_filters(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "notifications_filter_species_whitelist": ["Legacy Robin"],
        "notifications_filter_species_whitelist_structured": [
            {
                "scientific_name": "Erithacus rubecula",
                "common_name": "European Robin",
                "taxa_id": 1234,
            }
        ],
        "notifications_filter_species_blacklist_structured": [
            {
                "scientific_name": "Passer domesticus",
                "common_name": "House Sparrow",
                "taxa_id": 5678,
            }
        ],
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["notifications_filter_species_whitelist"] == ["Legacy Robin"]
    assert after_payload["notifications_filter_species_whitelist_structured"] == [
        {
            "scientific_name": "Erithacus rubecula",
            "common_name": "European Robin",
            "taxa_id": 1234,
        }
    ]
    assert after_payload["notifications_filter_species_blacklist_structured"] == [
        {
            "scientific_name": "Passer domesticus",
            "common_name": "House Sparrow",
            "taxa_id": 5678,
        }
    ]

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "notifications_filter_species_whitelist": before_payload.get("notifications_filter_species_whitelist", []),
        "notifications_filter_species_whitelist_structured": before_payload.get("notifications_filter_species_whitelist_structured", []),
        "notifications_filter_species_blacklist_structured": before_payload.get("notifications_filter_species_blacklist_structured", []),
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
async def test_settings_roundtrip_appearance_color_theme(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "appearance_color_theme" in before_payload

    original_theme = before_payload["appearance_color_theme"]
    updated_theme = "bluetit" if original_theme != "bluetit" else "default"

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "appearance_color_theme": updated_theme,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["appearance_color_theme"] == updated_theme

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.appearance.color_theme == updated_theme

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["appearance"]["color_theme"] == updated_theme

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "appearance_color_theme": original_theme,
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
async def test_settings_roundtrip_media_cache_high_quality_event_snapshot_bird_crop(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "media_cache_high_quality_event_snapshot_bird_crop" in before_payload

    original_value = before_payload["media_cache_high_quality_event_snapshot_bird_crop"]
    updated_value = not original_value

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshot_bird_crop": updated_value,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["media_cache_high_quality_event_snapshot_bird_crop"] is updated_value

    reloaded_from_file = Settings.load()
    assert reloaded_from_file.media_cache.high_quality_event_snapshot_bird_crop is updated_value

    persisted_json = json.loads(config_module.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted_json["media_cache"]["high_quality_event_snapshot_bird_crop"] is updated_value

    restore_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "media_cache_high_quality_event_snapshot_bird_crop": original_value,
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
