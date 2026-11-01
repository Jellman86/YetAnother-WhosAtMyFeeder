"""The About page's install count is a cached, optional read of the telemetry worker."""

import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services.community_stats_service import (
    FAILURE_RETRY_SECONDS,
    SUCCESS_TTL_SECONDS,
    CommunityStatsService,
)

SUMMARY = {"total_installs": 27, "active_last_7_days": 26, "versions": [], "cohort_minimum": 3}


@pytest.mark.asyncio
async def test_opted_out_install_never_contacts_the_worker():
    svc = CommunityStatsService()
    svc._fetch_summary = AsyncMock()
    with patch.object(settings.system, "update_check_enabled", False):
        stats = await svc.get_stats()
    assert stats["enabled"] is False
    assert stats["active_installs"] is None
    svc._fetch_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_counts_come_from_the_summary_and_are_cached():
    svc = CommunityStatsService()
    svc._fetch_summary = AsyncMock(return_value=SUMMARY)
    with patch.object(settings.system, "update_check_enabled", True):
        first = await svc.get_stats()
        second = await svc.get_stats()
    assert first["active_installs"] == 26
    assert first["total_installs"] == 27
    assert first["error"] is None
    assert first["checked_at"] is not None
    assert second == first
    assert svc._fetch_summary.await_count == 1


@pytest.mark.asyncio
async def test_below_cohort_minimum_the_worker_publishes_null_and_so_do_we():
    svc = CommunityStatsService()
    svc._fetch_summary = AsyncMock(return_value={"total_installs": None, "active_last_7_days": None})
    with patch.object(settings.system, "update_check_enabled", True):
        stats = await svc.get_stats()
    assert stats["active_installs"] is None
    assert stats["total_installs"] is None


@pytest.mark.asyncio
async def test_a_failed_fetch_keeps_the_last_counts_and_retries_sooner():
    svc = CommunityStatsService()
    svc._fetch_summary = AsyncMock(return_value=SUMMARY)
    with patch.object(settings.system, "update_check_enabled", True):
        await svc.get_stats()
        svc._fetched_at -= SUCCESS_TTL_SECONDS + 1
        svc._fetch_summary = AsyncMock(side_effect=RuntimeError("stats_http_502"))
        stale = await svc.get_stats()
        assert stale["active_installs"] == 26
        assert stale["error"] == "fetch_failed"
        # Within the failure window nothing is re-fetched; after it, the worker is asked again.
        await svc.get_stats()
        assert svc._fetch_summary.await_count == 1
        svc._fetched_at -= FAILURE_RETRY_SECONDS + 1
        await svc.get_stats()
        assert svc._fetch_summary.await_count == 2
