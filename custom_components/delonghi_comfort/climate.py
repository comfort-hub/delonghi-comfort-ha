"""Climate platform for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import MAX_TEMP, MIN_TEMP
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
    """Set up the climate entity."""
    async_add_entities([DelonghiClimate(entry.runtime_data)])


class DelonghiClimate(DelonghiComfortEntity, ClimateEntity):
    """The heater as a climate entity."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the climate entity."""
        super().__init__(coordinator, "climate")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return heat when the appliance is on, otherwise off."""
        return HVACMode.HEAT if self.status.is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return whether the element is actually calling for heat.

        The heater is bang-bang thermostatic — it draws full power (or the Eco cap)
        only while the room is below the setpoint, and idles otherwise. There is no
        explicit "heating" flag in the cloud data, so derive it from room vs target
        temperature (the same inputs the firmware's own thermostat uses).
        """
        if not self.status.is_on:
            return HVACAction.OFF
        current = self.status.current_temperature
        target = self.status.target_temperature
        if current is not None and target is not None and current < target:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return the measured room temperature."""
        return self.status.current_temperature

    @property
    def target_temperature(self) -> int | None:
        """Return the target temperature."""
        return self.status.target_temperature

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the heater on (heat) or off."""
        await self.coordinator.client.async_set_power(hvac_mode == HVACMode.HEAT)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the heater on."""
        await self.coordinator.client.async_set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the heater off."""
        await self.coordinator.client.async_set_power(False)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        await self.coordinator.client.async_set_temperature(
            int(kwargs[ATTR_TEMPERATURE])
        )
        await self.coordinator.async_request_refresh()
