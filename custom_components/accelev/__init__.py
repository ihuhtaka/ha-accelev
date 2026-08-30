"""The Accelev EV Charger integration."""

from __future__ import annotations

from homeassistant.const import CONF_PIN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AccelevApiClient
from .const import CONF_CHARGER_ID
from .coordinator import AccelevConfigEntry, AccelevDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: AccelevConfigEntry) -> bool:
    """Set up Accelev from a config entry."""
    client = AccelevApiClient(
        entry.data[CONF_CHARGER_ID],
        entry.data[CONF_PIN],
        async_get_clientsession(hass),
    )
    coordinator = AccelevDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: AccelevConfigEntry
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AccelevConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
