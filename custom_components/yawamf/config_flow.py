"""Config flow for Yet Another WhosAtMyFeeder integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_URL,
    CONF_POLLING_INTERVAL,
    DEFAULT_POLLING_INTERVAL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_API_KEY,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="http://localhost:9852"): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional(CONF_API_KEY): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    url = data[CONF_URL].rstrip("/")
    username = (data.get(CONF_USERNAME) or "").strip() or None
    password = data.get(CONF_PASSWORD) or None
    api_key = (data.get(CONF_API_KEY) or "").strip() or None
    
    try:
        session = async_get_clientsession(hass)
        async with session.get(f"{url}/health") as response:
            if response.status != 200:
                raise CannotConnect

        # If auth is enabled and public access is disabled, we need credentials.
        async with session.get(f"{url}/api/auth/status") as status_resp:
            status_resp.raise_for_status()
            status = await status_resp.json()

        auth_required = bool(status.get("auth_required"))
        public_access_enabled = bool(status.get("public_access_enabled"))

        if auth_required and not public_access_enabled:
            # Either a JWT login (username/password) or the legacy API key must be provided.
            if username and password:
                async with session.post(
                    f"{url}/api/auth/login",
                    json={"username": username, "password": password},
                ) as login_resp:
                    if login_resp.status in (401, 403):
                        raise InvalidAuth
                    login_resp.raise_for_status()
                    login_data = await login_resp.json()
                    if not login_data.get("access_token"):
                        raise InvalidAuth
            elif api_key:
                async with session.get(
                    f"{url}/api/stats/daily-summary",
                    headers={"X-API-Key": api_key},
                ) as protected_resp:
                    if protected_resp.status in (401, 403):
                        raise InvalidAuth
                    protected_resp.raise_for_status()
            else:
                raise InvalidAuth
            
    except InvalidAuth:
        raise
    except Exception:
        _LOGGER.exception("Unexpected exception during validation")
        raise CannotConnect

    # Return info that you want to store in the config entry.
    return {"title": "YA-WAMF"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yet Another WhosAtMyFeeder."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for YA-WAMF."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_URL,
                        default=self.config_entry.options.get(
                            CONF_URL, self.config_entry.data.get(CONF_URL, "http://localhost:9852")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_USERNAME,
                        default=self.config_entry.options.get(
                            CONF_USERNAME, self.config_entry.data.get(CONF_USERNAME, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_PASSWORD,
                        default=self.config_entry.options.get(
                            CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_API_KEY,
                        default=self.config_entry.options.get(
                            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_POLLING_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
