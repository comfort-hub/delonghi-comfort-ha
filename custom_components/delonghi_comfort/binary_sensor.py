"""Binary sensor platform for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor entities."""
    async_add_entities([DelonghiProblem(entry.runtime_data)])


class DelonghiProblem(DelonghiComfortEntity, BinarySensorEntity):
    """Reports whether any heater fault/alarm flag is set."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "alarm"

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the problem sensor."""
        super().__init__(coordinator, "alarm")

    @property
    def is_on(self) -> bool:
        """Return true if any alarm is active."""
        return self.status.any_alarm

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the individual active alarm flags."""
        return {name: active for name, active in self.status.alarms.items() if active}
