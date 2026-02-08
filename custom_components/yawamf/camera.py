"""Camera platform for Yet Another WhosAtMyFeeder."""
from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
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
    _attr_has_entity_name = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{coordinator.entry_id}_latest_snapshot"

    @property
    def is_on(self) -> bool:
        """Return true if on."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name="YA-WAMF",
            manufacturer="YA-WAMF",
            configuration_url=self.coordinator.url,
        )

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
            async with self.coordinator.session.get(url, headers=self.coordinator.headers) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception:
            return None
        
        return None
