"""Sensor platform for Yet Another WhosAtMyFeeder."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_EVENT_ID,
    ATTR_SCORE,
    ATTR_CAMERA,
    ATTR_TIMESTAMP,
    ATTR_FRIGATE_SCORE,
    ATTR_SUB_LABEL,
    ATTR_TEMPERATURE,
    ATTR_WEATHER,
)
from .coordinator import YAWAMFDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: YAWAMFDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        YAWAMFLastBirdSensor(coordinator),
        YAWAMFDailyCountSensor(coordinator),
    ])

class YAWAMFLastBirdSensor(CoordinatorEntity[YAWAMFDataUpdateCoordinator], SensorEntity):
    """Sensor showing the last bird detected."""

    _attr_name = "Last Bird Detected"
    _attr_unique_id = "last_bird_detected"
    _attr_icon = "mdi:bird"
    _attr_has_entity_name = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_last_bird"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        latest = self.coordinator.data.get("latest")
        if latest:
            return latest.get("display_name")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        latest = self.coordinator.data.get("latest")
        if not latest:
            return {}

        return {
            ATTR_EVENT_ID: latest.get("frigate_event"),
            ATTR_SCORE: latest.get("score"),
            ATTR_CAMERA: latest.get("camera_name"),
            ATTR_TIMESTAMP: latest.get("detection_time"),
            ATTR_FRIGATE_SCORE: latest.get("frigate_score"),
            ATTR_SUB_LABEL: latest.get("sub_label"),
            ATTR_TEMPERATURE: latest.get("temperature"),
            ATTR_WEATHER: latest.get("weather_condition"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name="YA-WAMF",
            manufacturer="YA-WAMF",
            configuration_url=self.coordinator.url,
        )

class YAWAMFDailyCountSensor(CoordinatorEntity[YAWAMFDataUpdateCoordinator], SensorEntity):
    """Sensor showing total detections today."""

    _attr_name = "Daily Bird Count"
    _attr_unique_id = "daily_bird_count"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "birds"
    _attr_has_entity_name = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_daily_count"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_today", 0)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name="YA-WAMF",
            manufacturer="YA-WAMF",
            configuration_url=self.coordinator.url,
        )
