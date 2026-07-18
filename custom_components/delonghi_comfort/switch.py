"""Switch platform for De'Longhi Comfort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from delonghi_comfort import DelonghiComfort, MachineStatus
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry


@dataclass(frozen=True, kw_only=True)
class DelonghiSwitchDescription(SwitchEntityDescription):
    """Describes a De'Longhi Comfort switch."""

    value_fn: Callable[[MachineStatus], bool]
    set_fn: Callable[[DelonghiComfort, bool], Awaitable[None]]


PARALLEL_UPDATES = 1

SWITCHES: tuple[DelonghiSwitchDescription, ...] = (
    DelonghiSwitchDescription(
        key="night_mode",
        translation_key="night_mode",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda status: status.night_mode,
        set_fn=lambda client, on: client.async_set_night_mode(on),
    ),
    DelonghiSwitchDescription(
        key="silent",
        translation_key="silent",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda status: status.silent,
        set_fn=lambda client, on: client.async_set_silent(on),
    ),
    DelonghiSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda status: status.child_lock,
        set_fn=lambda client, on: client.async_set_child_lock(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DelonghiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(DelonghiSwitch(coordinator, desc) for desc in SWITCHES)


class DelonghiSwitch(DelonghiComfortEntity, SwitchEntity):
    """A toggleable heater feature."""

    entity_description: DelonghiSwitchDescription

    def __init__(
        self,
        coordinator: DelonghiComfortCoordinator,
        description: DelonghiSwitchDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return whether the feature is on."""
        return self.entity_description.value_fn(self.status)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        await self._async_guard(
            self.entity_description.set_fn(self.coordinator.client, True)
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        await self._async_guard(
            self.entity_description.set_fn(self.coordinator.client, False)
        )
        await self.coordinator.async_request_refresh()
