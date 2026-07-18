"""The De'Longhi Comfort integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: DelonghiConfigEntry) -> bool:
    """Set up De'Longhi Comfort from a config entry."""
    coordinator = DelonghiComfortCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DelonghiConfigEntry) -> bool:
    """Unload a config entry (the coordinator shuts its connection down on unload)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
