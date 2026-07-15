"""Number platform for De'Longhi Comfort (LED ring brightness)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness number entity."""
    async_add_entities([DelonghiBrightness(entry.runtime_data)])


class DelonghiBrightness(DelonghiComfortEntity, NumberEntity):
    """The LED ring brightness level (0-3)."""

    _attr_translation_key = "brightness"
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 3
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the brightness entity."""
        super().__init__(coordinator, "brightness")

    @property
    def native_value(self) -> float | None:
        """Return the current brightness level."""
        return self.status.brightness

    async def async_set_native_value(self, value: float) -> None:
        """Set the brightness level."""
        await self.coordinator.client.async_set_brightness(int(value))
        await self.coordinator.async_request_refresh()
