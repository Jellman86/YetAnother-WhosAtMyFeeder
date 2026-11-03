import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services.update_service import FAILURE_RETRY_SECONDS, SUCCESS_TTL_SECONDS, UpdateService

CHANNELS = {
    "stable": {"version": "v2.12.0", "url": "https://example/releases/tag/v2.12.0"},
    "dev": {"version": "2.13.0", "commit": "abc1234def5678", "url": "https://example/tree/dev"},
    "branches": {
        "dev": {"version": "2.13.0", "commit": "abc1234def5678", "url": "https://example/tree/dev"},
        "main": {"version": "2.13.0", "commit": "def5678abc1234", "url": "https://example/tree/main"},
    },
}


@pytest.mark.asyncio
async def test_disabled_returns_no_check_without_fetching():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock()
    with patch.object(settings.system, "update_check_enabled", False):
        status = await svc.get_status("2.10.0", branch="main", git_hash="deadbee")
    assert status["enabled"] is False
    assert status["update_available"] is False
    svc._fetch_channels.assert_not_awaited()


@pytest.mark.asyncio
async def test_stable_install_sees_newer_release():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.10.0", branch="stable", git_hash="deadbee")
    assert status["channel"] == "stable"
    assert status["latest_version"] == "v2.12.0"
    assert status["update_available"] is True
    assert status["release_url"] == "https://example/releases/tag/v2.12.0"


@pytest.mark.asyncio
async def test_stable_install_on_latest_release_sees_no_update():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.12.0", branch="stable", git_hash="deadbee")
    assert status["update_available"] is False


@pytest.mark.asyncio
async def test_dev_install_sees_newer_dev_commit():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.13.0-dev+0000000", branch="dev", git_hash="0000000")
    assert status["channel"] == "dev"
    assert status["update_available"] is True  # running 0000000 != dev head abc1234
    assert status["latest_version"] == "2.13.0-dev+abc1234"
    assert status["release_url"] == "https://example/tree/dev"


@pytest.mark.asyncio
async def test_dev_install_on_current_head_sees_no_update():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.13.0-dev+abc1234", branch="dev", git_hash="abc1234")
    assert status["update_available"] is False  # dev head abc1234def... starts with abc1234


@pytest.mark.asyncio
async def test_main_branch_install_compares_against_main_branch_row():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.13.0+0000000", branch="main", git_hash="0000000")
    assert status["channel"] == "main"
    assert status["latest_version"] == "2.13.0-main+def5678"
    assert status["update_available"] is True
    assert status["release_url"] == "https://example/tree/main"


@pytest.mark.asyncio
async def test_dev_install_is_not_nagged_about_stable_releases():
    # A dev install must never surface the stable channel's release as an update.
    channels = {"stable": {"version": "v9.9.9", "url": "x"}, "dev": {"version": "2.13.0", "commit": "abc1234"}}
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=channels)
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.13.0-dev+abc1234", branch="dev", git_hash="abc1234")
    assert status["update_available"] is False


@pytest.mark.asyncio
async def test_result_is_cached_within_ttl():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        await svc.get_status("2.10.0", branch="main", git_hash="x")
        await svc.get_status("2.10.0", branch="main", git_hash="x")
    svc._fetch_channels.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_result_refreshes_after_bounded_ttl():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(return_value=CHANNELS)
    with patch.object(settings.system, "update_check_enabled", True):
        await svc.get_status("2.10.0", branch="main", git_hash="x")
        svc._fetched_at -= SUCCESS_TTL_SECONDS + 1
        await svc.get_status("2.10.0", branch="main", git_hash="x")

    assert svc._fetch_channels.await_count == 2


@pytest.mark.asyncio
async def test_failed_result_retries_after_short_bounded_ttl():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(
        side_effect=[RuntimeError("temporary"), CHANNELS],
    )
    with patch.object(settings.system, "update_check_enabled", True):
        first = await svc.get_status("2.10.0", branch="main", git_hash="x")
        svc._fetched_at -= FAILURE_RETRY_SECONDS + 1
        recovered = await svc.get_status("2.10.0", branch="main", git_hash="x")

    assert first["error"] == "fetch_failed"
    assert recovered["error"] is None
    assert recovered["update_available"] is True
    assert svc._fetch_channels.await_count == 2


@pytest.mark.asyncio
async def test_fetch_failure_degrades_gracefully():
    svc = UpdateService()
    svc._fetch_channels = AsyncMock(side_effect=RuntimeError("version_http_502"))
    with patch.object(settings.system, "update_check_enabled", True):
        status = await svc.get_status("2.10.0", branch="main", git_hash="x")
    assert status["update_available"] is False
    assert status["error"] == "fetch_failed"
    assert status["latest_version"] is None
