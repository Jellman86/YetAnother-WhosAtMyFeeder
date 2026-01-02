"""DataUpdateCoordinator for Yet Another WhosAtMyFeeder."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import httpx
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

class YAWAMFDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching YA-WAMF data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        url: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        super().__init__(hass, logger, name="YA-WAMF", update_interval=update_interval)
        self.url = url.rstrip("/")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Fetch daily summary (counts and latest detection)
                summary_resp = await client.get(f"{self.url}/api/stats/daily-summary")
                summary_resp.raise_for_status()
                summary_data = summary_resp.json()

                # 2. Return aggregated data
                return {
                    "summary": summary_data,
                    "latest": summary_data.get("latest_detection"),
                    "total_today": summary_data.get("total_count", 0),
                    "top_species": summary_data.get("top_species", []),
                }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
