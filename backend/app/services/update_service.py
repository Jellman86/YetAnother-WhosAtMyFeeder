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
        self._channels: dict | None = None
        self._fetched_at: float | None = None
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    async def get_status(self, current_version: str, branch: str, git_hash: str) -> dict:
        """Return the channel-aware update status for the running build (cached).

        Dev images compare against the latest dev-branch commit; stable images compare
        against the latest release tag — so a dev install is never nagged about releases.
        """
        enabled = bool(settings.system.update_check_enabled)
        channel = "dev" if branch == "dev" else "stable"
        status: dict = {
            "current_version": current_version,
            "channel": channel,
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
        status["error"] = self._last_error
        if self._fetched_at is not None:
            status["checked_at"] = datetime.fromtimestamp(self._fetched_at, tz=timezone.utc).isoformat()

        channels = self._channels or {}
        if channel == "dev":
            dev = channels.get("dev") or {}
            commit = str(dev.get("commit") or "").strip() or None
            base = str(dev.get("version") or "").strip() or None
            short = commit[:7] if commit else None
            status["latest_version"] = f"{base}-dev+{short}" if base and short else short
            status["release_url"] = str(dev.get("url") or "") or RELEASES_PAGE_URL
            # A pulled dev image is never ahead of remote dev, so any differing head is newer.
            status["update_available"] = bool(commit and git_hash and not commit.startswith(git_hash))
        else:
            stable = channels.get("stable") or {}
            latest = str(stable.get("version") or "").strip() or None
            status["latest_version"] = latest
            status["release_url"] = str(stable.get("url") or "") or RELEASES_PAGE_URL
            status["update_available"] = is_update_available(current_version, latest)
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
                self._channels = await self._fetch_channels()
                self._last_error = None
            except Exception as exc:  # keep the last known good result; only bound the retry
                self._last_error = "fetch_failed"
                log.debug("Update check failed", error=str(exc))
            finally:
                self._fetched_at = time.time()

    async def _fetch_channels(self) -> dict:
        """Fetch the {stable, dev} version channels from the worker (the patchable I/O boundary)."""
        version_url = settings.telemetry.version_url
        if not version_url:
            raise RuntimeError("version_url_not_configured")
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(version_url, headers={"User-Agent": "YA-WAMF"})
        if response.status_code != 200:
            raise RuntimeError(f"version_http_{response.status_code}")
        data = response.json()
        return data if isinstance(data, dict) else {}


update_service = UpdateService()
