"""Photographs and visit media are always kept (#622).

The switches are gone, so what an owner needs to see is the one condition that still stops it: a
media folder that cannot be written. And nothing that read the old switches may misread their
absence.
"""

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, require_owner
from app.config import settings
from app.main import app
from app.services import media_cache as media_cache_module
from app.services.telemetry_service import build_runtime_telemetry_payload


@pytest_asyncio.fixture
async def owner_client():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_owner, None)


def test_health_reports_media_storage_and_degrades_when_it_cannot_be_written(monkeypatch):
    from app import main as main_module

    healthy = main_module.build_health_payload()
    assert healthy["media_storage"] == {"available": True, "error": None}

    monkeypatch.setattr(media_cache_module.media_cache, "_available", False)
    monkeypatch.setattr(media_cache_module.media_cache, "_init_error", "Permission denied: '/config/media_cache'")
    broken = main_module.build_health_payload()

    assert broken["media_storage"] == {"available": False, "error": "Permission denied: '/config/media_cache'"}
    assert broken["status"] == "degraded"
    # Never a startup warning: that would fail readiness and restart a container that otherwise works.
    assert broken["startup_warnings"] == healthy["startup_warnings"]


@pytest.mark.asyncio
async def test_cache_stats_say_whether_media_can_be_stored(owner_client, monkeypatch):
    from app.routers import settings as settings_router

    def walk():
        return {
            "snapshot_count": 0,
            "snapshot_size_bytes": 0,
            "snapshot_size_mb": 0.0,
            "clip_count": 0,
            "clip_size_bytes": 0,
            "clip_size_mb": 0.0,
            "preview_count": 0,
            "preview_size_bytes": 0,
            "preview_size_mb": 0.0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
            "oldest_file": None,
            "newest_file": None,
        }

    monkeypatch.setattr(settings_router.media_cache, "_get_cache_stats_sync", walk)
    monkeypatch.setattr(media_cache_module.media_cache, "_available", False)

    response = await owner_client.get("/api/cache/stats")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["storage_available"] is False
    assert "cache_enabled" not in body and "cache_snapshots" not in body


@pytest.mark.asyncio
async def test_a_browser_tab_from_before_the_upgrade_can_still_save(owner_client, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    original_clips = settings.media_cache.cache_clips

    try:
        response = await owner_client.post(
            "/api/settings",
            json={"media_cache_enabled": False, "media_cache_snapshots": False, "media_cache_clips": True},
        )
        assert response.status_code == 200, response.text
        assert settings.media_cache.cache_clips is True
        current = (await owner_client.get("/api/settings")).json()
        assert "media_cache_enabled" not in current and "media_cache_snapshots" not in current
    finally:
        settings.media_cache.cache_clips = original_clips


def test_telemetry_keeps_reporting_the_media_cache_as_on():
    # The telemetry dashboard counts this field; dropping it would read as every install turning it off.
    payload = build_runtime_telemetry_payload(
        model_type=None, model_runtime=None, classifier_status={}, app_version="test", deployment_env={}
    )

    assert payload["configuration"]["media_cache_enabled"] is True
