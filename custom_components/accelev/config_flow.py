"""Config flow for the Accelev EV Charger integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PIN, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AccelevApiClient,
    AccelevAuthError,
    AccelevConnectionError,
    AccelevParseError,
)
from .const import (
    CONF_CHARGER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import AccelevConfigEntry

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_ID): str,
        vol.Required(CONF_PIN): str,
    }
)


async def _validate_input(hass: HomeAssistant, charger_id: str, pin: str) -> str:
    """Validate credentials against the API; return the unique ID to use."""
    client = AccelevApiClient(charger_id, pin, async_get_clientsession(hass))
    info = await client.async_validate_credentials()
    return info.serial or charger_id.upper()


class AccelevConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Accelev config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: collect and validate credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            charger_id = user_input[CONF_CHARGER_ID].strip()
            pin = user_input[CONF_PIN].strip()
            try:
                unique_id = await _validate_input(self.hass, charger_id, pin)
            except AccelevAuthError:
                errors["base"] = "invalid_auth"
            except AccelevConnectionError:
                errors["base"] = "cannot_connect"
            except AccelevParseError:
                errors["base"] = "cannot_parse"
            except Exception:
                _LOGGER.exception("Unexpected error validating Accelev credentials")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Accelev {charger_id}",
                    data={CONF_CHARGER_ID: charger_id, CONF_PIN: pin},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: AccelevConfigEntry) -> AccelevOptionsFlow:
        """Return the options flow handler."""
        return AccelevOptionsFlow()


class AccelevOptionsFlow(OptionsFlow):
    """Handle Accelev options (poll interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
