"""Camera platform for Yet Another WhosAtMyFeeder."""
from __future__ import annotations

import httpx
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YAWAMFDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the camera platform."""
    coordinator: YAWAMFDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([YAWAMFLatestBirdCamera(coordinator)])

class YAWAMFLatestBirdCamera(CoordinatorEntity[YAWAMFDataUpdateCoordinator], Camera):
    """Camera that shows the latest bird detection snapshot."""

    _attr_name = "Latest Bird Snapshot"
    _attr_icon = "mdi:image"

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_latest_snapshot"

    @property
    def is_on(self) -> bool:
        """Return true if on."""
        return True

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image response from the camera."""
        latest = self.coordinator.data.get("latest")
        if not latest:
            return None

        event_id = latest.get("frigate_event")
        url = f"{self.coordinator.url}/api/frigate/{event_id}/snapshot.jpg"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.content
        except Exception:
            return None
        
        return None
