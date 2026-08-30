"""Sensors for the Accelev EV Charger integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import AccelevConfigEntry, AccelevData, AccelevDataUpdateCoordinator
from .entity import AccelevEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AccelevSensorEntityDescription(SensorEntityDescription):
    """Describes an Accelev sensor."""

    value_fn: Callable[[AccelevData], StateType]


SENSORS: tuple[AccelevSensorEntityDescription, ...] = (
    AccelevSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.values.voltage if data.values else None,
    ),
    AccelevSensorEntityDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.values.current if data.values else None,
    ),
    AccelevSensorEntityDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.values.power if data.values else None,
    ),
    AccelevSensorEntityDescription(
        key="energy",
        translation_key="energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: data.values.energy if data.values else None,
    ),
    AccelevSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=lambda data: data.info.total_energy_kwh if data.info else None,
    ),
    AccelevSensorEntityDescription(
        key="last_update",
        translation_key="last_update",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.values.last_time if data.values else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AccelevConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Accelev sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        AccelevSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.append(AccelevInfoSensor(coordinator, entry))
    async_add_entities(entities)


class AccelevSensor(AccelevEntity, SensorEntity):
    """A plain polled Accelev sensor."""

    entity_description: AccelevSensorEntityDescription

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
        description: AccelevSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_uid}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the sensor value from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class AccelevInfoSensor(AccelevEntity, SensorEntity):
    """Raw `info` response with parsed values as attributes."""

    _attr_translation_key = "info"

    def __init__(
        self,
        coordinator: AccelevDataUpdateCoordinator,
        entry: AccelevConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_uid}_info"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> StateType:
        """Return the raw info string."""
        if self.coordinator.data is None or self.coordinator.data.info is None:
            return None
        return self.coordinator.data.info.raw[:255]

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return parsed info fields as attributes."""
        data = self.coordinator.data
        if data is None or data.info is None:
            return {}
        return {
            "total_energy_kwh": data.info.total_energy_kwh,
            "sop": data.info.sop,
            "firmware": data.info.firmware,
        }
