"""Switches for the Accelev EV Charger integration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import AccelevApiClient, AccelevCommandRejectedError, AccelevError
from .const import (
    CHARGE_SWITCH_OVERRIDE_OFF,
    CHARGE_SWITCH_OVERRIDE_ON,
    DOMAIN,
)
from .coordinator import AccelevConfigEntry, AccelevData, AccelevDataUpdateCoordinator
from .entity import AccelevEntity


@dataclass(frozen=True, kw_only=True)
class AccelevSwitchEntityDescription(SwitchEntityDescription):
    """Describes an Accelev switch.

    ``state_fn`` None means the API cannot report this mode's state, so the
    switch is optimistic and restores its last state across restarts.
    """

    state_fn: Callable[[AccelevData], bool] | None
    turn_on_fn: Callable[[AccelevApiClient], Awaitable[None]]
    turn_off_fn: Callable[[AccelevApiClient], Awaitable[None]]


SWITCHES: tuple[AccelevSwitchEntityDescription, ...] = (
    AccelevSwitchEntityDescription(
        key="charge",
        translation_key="charge",
        state_fn=lambda data: data.charging,
        turn_on_fn=lambda client: client.async_start_charging(),
        turn_off_fn=lambda client: client.async_stop_charging(),
    ),
    AccelevSwitchEntityDescription(
        key="grid_monitoring",
        translation_key="grid_monitoring",
        state_fn=None,
        turn_on_fn=lambda client: client.async_set_grid_monitoring(True),
        turn_off_fn=lambda client: client.async_set_grid_monitoring(False),
    ),
    AccelevSwitchEntityDescription(
        key="battery_care",
        translation_key="battery_care",
        state_fn=None,
        turn_on_fn=lambda client: client.async_set_battery_care(True),
        turn_off_fn=lambda client: client.async_set_battery_care(False),
    ),
    AccelevSwitchEntityDescription(
        key="no_full_charging",
        translation_key="no_full_charging",
        state_fn=None,
        turn_on_fn=lambda client: client.async_set_no_full_charging(True),
        turn_off_fn=lambda client: client.async_set_no_full_charging(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AccelevConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Accelev switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        AccelevSwitch(coordinator, entry, description) for description in SWITCHES
    )


class AccelevSwitch(AccelevEntity, SwitchEntity, RestoreEntity):
    """An Accelev command switch."""

    entity_description: AccelevSwitchEntityDescription

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
        description: AccelevSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_uid}_{description.key}"
        self._optimistic_state: bool | None = None
        # For the polled charge switch: (state, valid-until monotonic) after a
        # successful command, so phantom readings don't bounce the switch.
        self._state_override: tuple[bool, float] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known state for optimistic (mode) switches."""
        await super().async_added_to_hass()
        if self.entity_description.state_fn is not None:
            return
        if (last_state := await self.async_get_last_state()) is not None:
            self._optimistic_state = last_state.state == STATE_ON

    @property
    def is_on(self) -> bool | None:
        """Return the switch state (polled for charge, optimistic for modes)."""
        if self.entity_description.state_fn is not None:
            if self._state_override is not None:
                state, until = self._state_override
                if time.monotonic() < until:
                    return state
                self._state_override = None
            if self.coordinator.data is None:
                return None
            return self.entity_description.state_fn(self.coordinator.data)
        return self._optimistic_state

    async def _async_command(self, turn_on: bool) -> None:
        description = self.entity_description
        command_fn = description.turn_on_fn if turn_on else description.turn_off_fn
        try:
            await command_fn(self.coordinator.client)
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
        if description.state_fn is None:
            self._optimistic_state = turn_on
        else:
            window = (
                CHARGE_SWITCH_OVERRIDE_ON if turn_on else CHARGE_SWITCH_OVERRIDE_OFF
            )
            self._state_override = (turn_on, time.monotonic() + window)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_command(False)
