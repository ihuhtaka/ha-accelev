"""Button entities for the Accelev EV Charger integration."""

from __future__ import annotations

import homeassistant.util.dt as dt_util
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import AccelevError
from .const import DOMAIN
from .coordinator import AccelevConfigEntry, AccelevDataUpdateCoordinator
from .entity import AccelevEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AccelevConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Accelev button entities."""
    coordinator = entry.runtime_data
    async_add_entities([AccelevSyncTimeButton(coordinator, entry)])


class AccelevSyncTimeButton(AccelevEntity, ButtonEntity):
    """Sync the charger clock to Home Assistant's local time."""

    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-sync-outline"

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_uid}_sync_time"

    async def async_press(self) -> None:
        """Send the current local time (HHMM) to the charger."""
        hhmm = dt_util.now().strftime("%H%M")
        try:
            await self.coordinator.client.async_set_time(hhmm)
        except AccelevError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
