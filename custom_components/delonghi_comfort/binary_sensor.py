"""Binary sensor platform for De'Longhi Comfort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from delonghi_comfort import ConnectionState
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from delonghi_comfort import MachineStatus
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

PARALLEL_UPDATES = 0

# Alarm flags are prefix-coded: TOS* = tip-over safety cut-out, HTMAX* = over-
# temperature protection, and anything else is a generic protection fault.
_SAFETY_PREFIXES = ("TOS",)
_OVERHEAT_PREFIXES = ("HTMAX",)


def _matches(status: MachineStatus, prefixes: tuple[str, ...]) -> bool:
    """Return true if any active alarm flag starts with one of the prefixes."""
    return any(
        active and name.startswith(prefixes) for name, active in status.alarms.items()
    )


def _uncategorised(status: MachineStatus) -> bool:
    """Return true if an active alarm is neither a safety nor over-temperature flag."""
    known = _SAFETY_PREFIXES + _OVERHEAT_PREFIXES
    return any(
        active and not name.startswith(known) for name, active in status.alarms.items()
    )


@dataclass(frozen=True, kw_only=True)
class DelonghiBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a De'Longhi Comfort binary sensor."""

    value_fn: Callable[[MachineStatus], bool]
    attrs_fn: Callable[[MachineStatus], dict[str, bool]] | None = None


BINARY_SENSORS: tuple[DelonghiBinarySensorDescription, ...] = (
    DelonghiBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.any_alarm,
        attrs_fn=lambda status: {
            name: active for name, active in status.alarms.items() if active
        },
    ),
    DelonghiBinarySensorDescription(
        key="safety_alarm",
        translation_key="safety_alarm",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: _matches(status, _SAFETY_PREFIXES),
    ),
    DelonghiBinarySensorDescription(
        key="overheat_alarm",
        translation_key="overheat_alarm",
        device_class=BinarySensorDeviceClass.HEAT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: _matches(status, _OVERHEAT_PREFIXES),
    ),
    DelonghiBinarySensorDescription(
        key="problem_alarm",
        translation_key="problem_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_uncategorised,
    ),
    DelonghiBinarySensorDescription(
        key="timer_active",
        translation_key="timer_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda status: status.timer_active,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor entities."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        DelonghiBinarySensor(coordinator, desc) for desc in BINARY_SENSORS
    ]
    entities.append(DelonghiConnectivity(coordinator))
    async_add_entities(entities)


class DelonghiBinarySensor(DelonghiComfortEntity, BinarySensorEntity):
    """A De'Longhi Comfort binary sensor."""

    entity_description: DelonghiBinarySensorDescription

    def __init__(
        self,
        coordinator: DelonghiComfortCoordinator,
        description: DelonghiBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the current on/off state."""
        return self.entity_description.value_fn(self.status)

    @property
    def extra_state_attributes(self) -> dict[str, bool] | None:
        """Expose extra attributes (e.g. individual alarm flags) when provided."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.status)


class DelonghiConnectivity(DelonghiComfortEntity, BinarySensorEntity):
    """Whether the library's live cloud (MQTT) connection to the heater is up.

    This reflects the transport link, not device availability, so it stays
    available and reports "disconnected" even while the heater itself is
    offline — giving a clear signal of whether real-time pushes are flowing.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connection"

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the connectivity sensor."""
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        """Stay available so it can always report the connection state."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the live connection is currently up."""
        return self.coordinator.connection_state is ConnectionState.CONNECTED
