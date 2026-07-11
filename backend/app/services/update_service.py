"""Checks for a newer YA-WAMF release to power the in-app update prompt.

The latest version comes from the telemetry worker's ``/version`` endpoint (a plain GET
with no telemetry payload), which fetches and edge-caches it from GitHub — so GitHub is
hit once per cache window globally rather than once per install, and the check works even
when telemetry is disabled. The local lookup is itself cached and lazy (refreshed on
request when stale), never blocks, and degrades to the last known result — or to "no
update" — on any failure. Honours the ``system.update_check_enabled`` privacy opt-out.
"""

import asyncio
import time
from datetime import datetime, timezone

import httpx
import structlog

from app.config import settings
from app.utils.version import is_update_available

log = structlog.get_logger()

RELEASES_PAGE_URL = "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/latest"
SUCCESS_TTL_SECONDS = 12 * 3600
FAILURE_RETRY_SECONDS = 3600
FETCH_TIMEOUT_SECONDS = 8.0


class UpdateService:
    def __init__(self) -> None:
        self._latest_version: str | None = None
        self._latest_url: str | None = None
        self._fetched_at: float | None = None
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    async def get_status(self, current_version: str) -> dict:
        """Return the update status for the given running version (cached)."""
        enabled = bool(settings.system.update_check_enabled)
        status: dict = {
            "current_version": current_version,
            "latest_version": None,
            "update_available": False,
            "release_url": RELEASES_PAGE_URL,
            "checked_at": None,
            "enabled": enabled,
            "error": None,
        }
        if not enabled:
            return status

        await self._refresh_if_stale()
        status["latest_version"] = self._latest_version
        status["release_url"] = self._latest_url or RELEASES_PAGE_URL
        status["error"] = self._last_error
        if self._fetched_at is not None:
            status["checked_at"] = datetime.fromtimestamp(self._fetched_at, tz=timezone.utc).isoformat()
        status["update_available"] = is_update_available(current_version, self._latest_version)
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
            # Another caller may have refreshed while we waited for the lock.
            if self._is_fresh():
                return
            try:
                latest_version, latest_url = await self._fetch_latest_release()
                self._latest_version = latest_version
                self._latest_url = latest_url
                self._last_error = None
            except Exception as exc:  # keep the last known good result; only bound the retry
                self._last_error = "fetch_failed"
                log.debug("Update check failed", error=str(exc))
            finally:
                self._fetched_at = time.time()

    async def _fetch_latest_release(self) -> tuple[str | None, str | None]:
        """Fetch the latest version and release URL from the worker (the patchable I/O boundary)."""
        version_url = settings.telemetry.version_url
        if not version_url:
            raise RuntimeError("version_url_not_configured")
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(version_url, headers={"User-Agent": "YA-WAMF"})
        if response.status_code != 200:
            raise RuntimeError(f"version_http_{response.status_code}")
        data = response.json()
        latest = str(data.get("latest_version") or data.get("version") or "").strip() or None
        url = str(data.get("release_url") or "").strip() or None
        return latest, url


update_service = UpdateService()
