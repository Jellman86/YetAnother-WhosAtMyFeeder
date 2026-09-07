"""DataUpdateCoordinator for Yet Another WhosAtMyFeeder."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


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

    async def async_ensure_logged_in(self) -> None:
        """Log in with the stored username and password when the token is missing or near expiry.

        The sidebar proxy calls this before each upstream request, so a token
        that expires between polls is refreshed on demand rather than waiting
        for the next poll.
        """
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
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403):
                        raise ConfigEntryAuthFailed("YA-WAMF rejected the stored username and password")
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
            except (UpdateFailed, ConfigEntryAuthFailed):
                raise
            except Exception as err:
                raise UpdateFailed(f"Error logging in to YA-WAMF: {err}") from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            await self.async_ensure_logged_in()
            headers = self._headers()

            async with self.session.get(
                f"{self.url}/api/stats/daily-summary",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    # Forget the token so a reauth with new credentials starts clean.
                    self._access_token = None
                    self._access_token_expires_at = None
                    raise ConfigEntryAuthFailed(
                        "YA-WAMF requires authentication: provide credentials or enable public access"
                    )
                resp.raise_for_status()
                summary_data = await resp.json()

            if not isinstance(summary_data, dict):
                raise UpdateFailed("YA-WAMF daily summary returned an invalid payload")

            latest_detection = summary_data.get("latest_detection")
            top_species = summary_data.get("top_species")
            count_24h = summary_data.get("total_count", 0)

            return {
                "summary": summary_data,
                "latest": latest_detection if isinstance(latest_detection, dict) else None,
                "count_24h": count_24h if isinstance(count_24h, int) else 0,
                "top_species": top_species if isinstance(top_species, list) else [],
            }
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
