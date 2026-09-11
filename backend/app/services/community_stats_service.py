"""Anonymous install counts for the About page.

The telemetry worker publishes aggregate counts at ``/stats/summary`` (a plain GET with no
payload, the same host the update check reads). The About page quotes how many installs
reported in the last week. The lookup is cached for an hour and refreshed on the first request
after the hour, which waits for the fetch (bounded by its timeout); every other request is
served from the cache, and a failed fetch keeps the last known counts. It honours the
``system.update_check_enabled`` opt-out: an owner who has asked the install not to contact
the worker is not contacted on their behalf here either.
"""

import asyncio
import time
from datetime import datetime, timezone

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

SUCCESS_TTL_SECONDS = 60 * 60
FAILURE_RETRY_SECONDS = 10 * 60
FETCH_TIMEOUT_SECONDS = 8.0


def _count(value: object) -> int | None:
    """The worker publishes null below its public cohort minimum; anything else is a count."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


class CommunityStatsService:
    def __init__(self) -> None:
        self._summary: dict | None = None
        self._fetched_at: float | None = None
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    async def get_stats(self) -> dict:
        enabled = bool(settings.system.update_check_enabled)
        status: dict = {
            "enabled": enabled,
            "active_installs": None,
            "total_installs": None,
            "checked_at": None,
            "error": None,
        }
        if not enabled:
            return status

        await self._refresh_if_stale()
        status["error"] = self._last_error
        if self._fetched_at is not None:
            status["checked_at"] = datetime.fromtimestamp(self._fetched_at, tz=timezone.utc).isoformat()
        summary = self._summary or {}
        status["active_installs"] = _count(summary.get("active_last_7_days"))
        status["total_installs"] = _count(summary.get("total_installs"))
        return status

    def _is_fresh(self) -> bool:
        if self._fetched_at is None:
            return False
        ttl = SUCCESS_TTL_SECONDS if self._last_error is None else FAILURE_RETRY_SECONDS
        return (time.time() - self._fetched_at) < ttl

    async def _refresh_if_stale(self) -> None:
        if self._is_fresh():
            return
        async with self._lock:
            if self._is_fresh():
                return
            try:
                self._summary = await self._fetch_summary()
                self._last_error = None
            except Exception as exc:  # keep the last known counts; only bound the retry
                self._last_error = "fetch_failed"
                log.debug("Community stats fetch failed", error=str(exc))
            finally:
                self._fetched_at = time.time()

    async def _fetch_summary(self) -> dict:
        """Fetch the worker's public summary (the patchable I/O boundary)."""
        stats_url = settings.telemetry.stats_url
        if not stats_url:
            raise RuntimeError("stats_url_not_configured")
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(stats_url, headers={"User-Agent": "YA-WAMF"})
        if response.status_code != 200:
            raise RuntimeError(f"stats_http_{response.status_code}")
        data = response.json()
        return data if isinstance(data, dict) else {}


community_stats_service = CommunityStatsService()
