"""Base entity for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL, CONF_SERIAL_NUMBER, CONF_THING_NAME, DOMAIN, MANUFACTURER
from .coordinator import DelonghiComfortCoordinator

if TYPE_CHECKING:
    from delonghi_comfort import MachineStatus


class DelonghiComfortEntity(CoordinatorEntity[DelonghiComfortCoordinator]):
    """Common base wiring device info and the status snapshot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DelonghiComfortCoordinator, key: str) -> None:
        """Attach the entity to the heater device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        thing_name = entry.data[CONF_THING_NAME]
        serial = entry.data.get(CONF_SERIAL_NUMBER)
        self._attr_unique_id = f"{thing_name}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, thing_name)},
            manufacturer=MANUFACTURER,
            model=entry.data.get(CONF_MODEL),
            name=entry.title,
            serial_number=serial,
            connections={(CONNECTION_NETWORK_MAC, serial)} if serial else set(),
            sw_version=(
                coordinator.capabilities.wifi_firmware
                if coordinator.capabilities
                else None
            ),
        )

    @property
    def status(self) -> MachineStatus:
        """The latest reported status."""
        # HA types ``DataUpdateCoordinator.data`` loosely; pin it to our model here so
        # every entity that reads ``self.status`` gets precise attribute types.
        status: MachineStatus = self.coordinator.data
        return status
