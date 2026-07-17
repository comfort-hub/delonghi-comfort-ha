"""Sensor platform for De'Longhi Comfort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from delonghi_comfort import MachineStatus
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry


def _scaled_temp(status: MachineStatus, key: str) -> float | None:
    """Return a tenths-of-a-degree field as degrees."""
    value = status.raw.get(key)
    return value / 10 if isinstance(value, (int, float)) else None


@dataclass(frozen=True, kw_only=True)
class DelonghiSensorDescription(SensorEntityDescription):
    """Describes a De'Longhi Comfort sensor."""

    value_fn: Callable[[MachineStatus], float | None]


SENSORS: tuple[DelonghiSensorDescription, ...] = (
    DelonghiSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda status: status.current_temperature,
    ),
    DelonghiSensorDescription(
        key="power_board_temperature",
        translation_key="power_board_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _scaled_temp(status, "PowerBoard_PcbTemp"),
    ),
    DelonghiSensorDescription(
        key="ui_board_temperature",
        translation_key="ui_board_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _scaled_temp(status, "UiBoard_PcbTemp"),
    ),
)


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(DelonghiSensor(coordinator, desc) for desc in SENSORS)


class DelonghiSensor(DelonghiComfortEntity, SensorEntity):
    """A De'Longhi Comfort sensor."""

    entity_description: DelonghiSensorDescription

    def __init__(
        self,
        coordinator: DelonghiComfortCoordinator,
        description: DelonghiSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.status)
