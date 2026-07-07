"""Camera platform for Yet Another WhosAtMyFeeder."""

from __future__ import annotations

import io
import logging

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YAWAMFDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Feeder snapshots are full-resolution (often several MB). That's fine for the
# scaled dashboard thumbnail, but the more-info / live camera view loops the
# full image and fails to render when it's this large, so downscale it.
_MAX_EDGE = 1280


def _downscale_jpeg(data: bytes) -> bytes:
    """Downscale a JPEG to a reasonable size. Runs in an executor thread.

    Returns the original bytes unchanged if Pillow is unavailable or the image
    can't be processed, so the camera degrades gracefully.
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if max(img.size) <= _MAX_EDGE:
            return data
        img.thumbnail((_MAX_EDGE, _MAX_EDGE))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - never fail the camera on a resize error
        return data


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

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return a still image response from the camera."""
        latest = self.coordinator.data.get("latest")
        if not latest:
            return None

        event_id = latest.get("frigate_event")
        url = f"{self.coordinator.url}/api/frigate/{event_id}/snapshot.jpg"

        try:
            async with self.coordinator.session.get(url, headers=self.coordinator.headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        except Exception:
            return None

        return await self.hass.async_add_executor_job(_downscale_jpeg, data)
