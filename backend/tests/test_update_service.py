import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services.update_service import UpdateService


@pytest.mark.asyncio
async def test_disabled_returns_no_check_without_fetching():
    svc = UpdateService()
    svc._fetch_latest_release = AsyncMock()
    with patch.object(settings.system, "update_check_enabled", False):
        status = await svc.get_status("2.10.0")
    assert status["enabled"] is False
    assert status["update_available"] is False
    assert status["latest_version"] is None
    svc._fetch_latest_release.assert_not_awaited()


@pytest.mark.asyncio
async def test_reports_update_when_github_has_a_newer_release():
    svc = UpdateService()
    svc._fetch_latest_release = AsyncMock(return_value=("v2.12.0", "https://example/releases/v2.12.0"))
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.10.0")
    assert status["latest_version"] == "v2.12.0"
    assert status["update_available"] is True
    assert status["release_url"] == "https://example/releases/v2.12.0"
    assert status["checked_at"] is not None
    assert status["error"] is None


@pytest.mark.asyncio
async def test_no_update_when_running_the_latest():
    svc = UpdateService()
    svc._fetch_latest_release = AsyncMock(return_value=("v2.12.0", None))
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.12.0")
    assert status["update_available"] is False


@pytest.mark.asyncio
async def test_result_is_cached_within_ttl():
    svc = UpdateService()
    svc._fetch_latest_release = AsyncMock(return_value=("v2.12.0", None))
    with patch.object(settings.system, "update_check_enabled", True):
        await svc.get_status("2.10.0")
        await svc.get_status("2.10.0")
    svc._fetch_latest_release.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_failure_degrades_gracefully():
    svc = UpdateService()
    svc._fetch_latest_release = AsyncMock(side_effect=RuntimeError("github_http_403"))
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.10.0")
    assert status["update_available"] is False
    assert status["error"] == "fetch_failed"
    assert status["latest_version"] is None
