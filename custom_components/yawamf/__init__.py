"""The Yet Another WhosAtMyFeeder integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_URL,
    DEFAULT_POLLING_INTERVAL,
    CONF_POLLING_INTERVAL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_API_KEY,
    CONF_ENABLE_INGRESS,
    DEFAULT_ENABLE_INGRESS,
)
from .coordinator import YAWAMFDataUpdateCoordinator
from .ingress import async_register_ingress, async_unregister_ingress_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CAMERA]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Yet Another WhosAtMyFeeder from a config entry."""
    url = entry.options.get(CONF_URL, entry.data[CONF_URL])
    polling_interval = entry.options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)
    username = entry.options.get(CONF_USERNAME, entry.data.get(CONF_USERNAME))
    password = entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD))
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY))
    enable_ingress = entry.options.get(
        CONF_ENABLE_INGRESS,
        entry.data.get(CONF_ENABLE_INGRESS, DEFAULT_ENABLE_INGRESS),
    )

    session = async_get_clientsession(hass)

    coordinator = YAWAMFDataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        session=session,
        url=url,
        username=username,
        password=password,
        api_key=api_key,
        update_interval=timedelta(seconds=polling_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    hass.data[DOMAIN].setdefault("_ingress_entries", set())

    if enable_ingress:
        await async_register_ingress(hass, coordinator)
        hass.data[DOMAIN]["_ingress_entries"].add(entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        ingress_entries = hass.data.get(DOMAIN, {}).get("_ingress_entries", set())
        if entry.entry_id in ingress_entries:
            ingress_entries.discard(entry.entry_id)
            if not ingress_entries:
                await async_unregister_ingress_panel(hass)
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
