"""Sensor platform for Yet Another WhosAtMyFeeder."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
        YAWAMFLastDetectionEventSensor(coordinator),
        YAWAMFLastDetectionTimestampSensor(coordinator),
        YAWAMFDailyCountSensor(coordinator),
    ])


def _latest_detection(coordinator: YAWAMFDataUpdateCoordinator) -> dict[str, Any] | None:
    latest = coordinator.data.get("latest")
    return latest if isinstance(latest, dict) else None


def _latest_event_id(coordinator: YAWAMFDataUpdateCoordinator) -> str | None:
    latest = _latest_detection(coordinator)
    if not latest:
        return None
    event_id = latest.get("frigate_event")
    if isinstance(event_id, str) and event_id.strip():
        return event_id.strip()
    return None


def _latest_detection_timestamp(coordinator: YAWAMFDataUpdateCoordinator) -> datetime | None:
    latest = _latest_detection(coordinator)
    if not latest:
        return None
    raw_value = latest.get("detection_time")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None

class YAWAMFLastBirdSensor(CoordinatorEntity[YAWAMFDataUpdateCoordinator], SensorEntity):
    """Sensor showing the last bird detected."""

    _attr_name = "Last Bird Detected"
    _attr_unique_id = "last_bird_detected"
    _attr_icon = "mdi:bird"
    _attr_has_entity_name = True
    _attr_force_update = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_last_bird"
        self._last_event_id: str | None = None

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        latest = _latest_detection(self.coordinator)
        if latest:
            return latest.get("display_name")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        latest = _latest_detection(self.coordinator)
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Only emit HA state updates when a new detection arrives."""
        event_id = _latest_event_id(self.coordinator)
        if event_id == self._last_event_id:
            return
        self._last_event_id = event_id
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name="YA-WAMF",
            manufacturer="YA-WAMF",
            configuration_url=self.coordinator.url,
        )


class YAWAMFLastDetectionEventSensor(CoordinatorEntity[YAWAMFDataUpdateCoordinator], SensorEntity):
    """Sensor exposing the latest detection event ID for automations."""

    _attr_name = "Last Detection Event"
    _attr_icon = "mdi:identifier"
    _attr_has_entity_name = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_last_detection_event"

    @property
    def native_value(self) -> str | None:
        return _latest_event_id(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = _latest_detection(self.coordinator)
        if not latest:
            return {}
        return {
            "species": latest.get("display_name"),
            ATTR_CAMERA: latest.get("camera_name"),
            ATTR_TIMESTAMP: latest.get("detection_time"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name="YA-WAMF",
            manufacturer="YA-WAMF",
            configuration_url=self.coordinator.url,
        )


class YAWAMFLastDetectionTimestampSensor(CoordinatorEntity[YAWAMFDataUpdateCoordinator], SensorEntity):
    """Sensor exposing the latest detection timestamp as a HA timestamp."""

    _attr_name = "Last Detection Time"
    _attr_icon = "mdi:clock-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True

    def __init__(self, coordinator: YAWAMFDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_last_detection_time"

    @property
    def native_value(self) -> datetime | None:
        return _latest_detection_timestamp(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = _latest_detection(self.coordinator)
        if not latest:
            return {}
        return {
            "species": latest.get("display_name"),
            ATTR_EVENT_ID: latest.get("frigate_event"),
            ATTR_CAMERA: latest.get("camera_name"),
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
