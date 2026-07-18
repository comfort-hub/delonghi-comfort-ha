"""Select platform for De'Longhi Comfort (front-panel LED brightness)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

PARALLEL_UPDATES = 1

# BrightnessLevel is a discrete 0-3 register; level 0 turns the panel display off.
# The option list is index-aligned to the device value it maps to.
_BRIGHTNESS_OPTIONS = ["off", "low", "medium", "high"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness select entity."""
    async_add_entities([DelonghiBrightness(entry.runtime_data)])


class DelonghiBrightness(DelonghiComfortEntity, SelectEntity):
    """The front-panel LED display brightness (off / low / medium / high)."""

    _attr_translation_key = "brightness"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = _BRIGHTNESS_OPTIONS

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the brightness select."""
        super().__init__(coordinator, "brightness")

    @property
    def current_option(self) -> str | None:
        """Return the current brightness level as a named option."""
        level = self.status.brightness
        if level is None or not 0 <= level < len(_BRIGHTNESS_OPTIONS):
            return None
        return _BRIGHTNESS_OPTIONS[level]

    async def async_select_option(self, option: str) -> None:
        """Set the brightness level from the named option."""
        await self._async_guard(
            self.coordinator.client.async_set_brightness(
                _BRIGHTNESS_OPTIONS.index(option)
            )
        )
        await self.coordinator.async_request_refresh()
