"""Number entities for the Accelev EV Charger integration."""

from __future__ import annotations

import contextlib

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import AccelevCommandRejectedError, AccelevError
from .const import CURRENT_STEP, DOMAIN, MAX_CURRENT, MIN_CURRENT
from .coordinator import AccelevConfigEntry, AccelevDataUpdateCoordinator
from .entity import AccelevEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AccelevConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Accelev number entities."""
    coordinator = entry.runtime_data
    async_add_entities([AccelevSetCurrentNumber(coordinator, entry)])


class AccelevSetCurrentNumber(AccelevEntity, NumberEntity, RestoreEntity):
    """Set the charge current.

    The API cannot read the setpoint back (``whatiscurrent`` reports the
    *actual* current to the car), so the value is optimistic and restored
    across restarts.
    """

    _attr_translation_key = "set_current"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = MIN_CURRENT
    _attr_native_max_value = MAX_CURRENT
    _attr_native_step = CURRENT_STEP

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_uid}_set_current"

    async def async_added_to_hass(self) -> None:
        """Restore the last set current."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None and (
            last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        ):
            with contextlib.suppress(ValueError):
                self._attr_native_value = float(last_state.state)

    async def async_set_native_value(self, value: float) -> None:
        """Send the new current setpoint to the charger."""
        try:
            await self.coordinator.client.async_set_current(value)
        except AccelevCommandRejectedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"response": str(err)},
            ) from err
        except AccelevError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._attr_native_value = value
        self.async_write_ha_state()
