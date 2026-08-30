"""Base entity for the Accelev EV Charger integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHARGER_ID, DOMAIN, MANUFACTURER, MODEL
from .coordinator import AccelevConfigEntry, AccelevDataUpdateCoordinator


class AccelevEntity(CoordinatorEntity[AccelevDataUpdateCoordinator]):
    """Common base: binds entities to the coordinator and the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._charger_id: str = entry.data[CONF_CHARGER_ID]
        self._device_uid: str = entry.unique_id or self._charger_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info, including firmware once it has been polled."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"Accelev {self._charger_id}",
            serial_number=self._charger_id,
        )
        if (
            self.coordinator.data
            and self.coordinator.data.info
            and self.coordinator.data.info.firmware
        ):
            info["sw_version"] = self.coordinator.data.info.firmware
        return info
