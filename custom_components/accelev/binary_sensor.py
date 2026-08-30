"""Binary sensors for the Accelev EV Charger integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AccelevConfigEntry, AccelevDataUpdateCoordinator
from .entity import AccelevEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AccelevConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Accelev binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AccelevChargingBinarySensor(coordinator, entry),
            AccelevServerOnlineBinarySensor(coordinator, entry),
        ]
    )


class AccelevChargingBinarySensor(AccelevEntity, BinarySensorEntity):
    """Whether the charger is currently delivering power to the car."""

    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_uid}_charging"

    @property
    def is_on(self) -> bool | None:
        """Return the charging state computed by the coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.charging

    @property
    def extra_state_attributes(self) -> dict[str, bool] | None:
        """Expose the stale-data flag (frozen charger-side snapshot)."""
        if self.coordinator.data is None:
            return None
        return {"data_stale": self.coordinator.data.stale}


class AccelevServerOnlineBinarySensor(AccelevEntity, BinarySensorEntity):
    """Whether the cloud API answered the last poll.

    Unlike the other entities this stays *available* during outages so users
    can distinguish "server down" from a broken entity.
    """

    _attr_translation_key = "server_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_uid}_server_online"

    @property
    def is_on(self) -> bool:
        """Return whether the last coordinator update succeeded."""
        return self.coordinator.last_update_success

    @property
    def available(self) -> bool:
        """Always available, especially when the server is not."""
        return True
