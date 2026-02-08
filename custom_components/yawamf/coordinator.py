"""DataUpdateCoordinator for Yet Another WhosAtMyFeeder."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


class YAWAMFDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching YA-WAMF data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        config_entry: ConfigEntry,
        session: aiohttp.ClientSession,
        url: str,
        username: str | None,
        password: str | None,
        api_key: str | None,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        super().__init__(hass, logger, name="YA-WAMF", update_interval=update_interval)
        self.config_entry = config_entry
        self.entry_id = config_entry.entry_id

        self.session = session
        self.url = url.rstrip("/")

        self.username = username
        self.password = password
        self.api_key = api_key

        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None
        self._login_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        if self.api_key:
            return {"X-API-Key": self.api_key}
        return {}

    @property
    def headers(self) -> dict[str, str]:
        """Public accessor for auth headers."""
        return self._headers()

    def _token_valid(self) -> bool:
        if not self._access_token:
            return False
        if not self._access_token_expires_at:
            return True
        return datetime.now(timezone.utc) < (self._access_token_expires_at - timedelta(minutes=5))

    async def _ensure_logged_in(self) -> None:
        """Best-effort login if username/password provided."""
        if not self.username or not self.password:
            return
        if self._token_valid():
            return

        async with self._login_lock:
            if self._token_valid():
                return

            try:
                async with self.session.post(
                    f"{self.url}/api/auth/login",
                    json={"username": self.username, "password": self.password},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (401, 403):
                        raise UpdateFailed("Invalid YA-WAMF credentials")
                    resp.raise_for_status()
                    data = await resp.json()

                token = data.get("access_token")
                expires_in_hours = data.get("expires_in_hours")
                if not token:
                    raise UpdateFailed("YA-WAMF login did not return an access token")

                self._access_token = token
                if isinstance(expires_in_hours, int):
                    self._access_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
                else:
                    self._access_token_expires_at = None
            except UpdateFailed:
                raise
            except Exception as err:
                raise UpdateFailed(f"Error logging in to YA-WAMF: {err}") from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            await self._ensure_logged_in()
            headers = self._headers()

            async with self.session.get(
                f"{self.url}/api/stats/daily-summary",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403):
                    # Clear cached token so we can re-login next cycle.
                    self._access_token = None
                    self._access_token_expires_at = None
                    raise UpdateFailed(
                        "Authentication required for YA-WAMF API (check HA integration credentials/public access)"
                    )
                resp.raise_for_status()
                summary_data = await resp.json()

            return {
                "summary": summary_data,
                "latest": summary_data.get("latest_detection"),
                "total_today": summary_data.get("total_count", 0),
                "top_species": summary_data.get("top_species", []),
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
