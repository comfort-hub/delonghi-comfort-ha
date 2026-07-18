"""Climate platform for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, MAX_TEMP, MAX_TEMP_F, MIN_TEMP, MIN_TEMP_F
from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

PARALLEL_UPDATES = 1

# Hysteresis (in the device's current unit) around the setpoint within which
# hvac_action holds its previous value, so a room reading that hovers on a whole-degree
# setpoint (against the 0.1° RoomTemp resolution) does not flap between heating and idle.
HVAC_ACTION_DEADBAND = 0.5


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
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = [PRESET_NONE, PRESET_ECO]
    _attr_target_temperature_step = 1
    _last_hvac_action: HVACAction | None = None

    def __init__(self, coordinator: DelonghiComfortCoordinator) -> None:
        """Initialise the climate entity."""
        super().__init__(coordinator, "climate")

    @property
    def temperature_unit(self) -> str:
        """Report whichever unit the device is currently displaying."""
        return (
            UnitOfTemperature.CELSIUS
            if self.status.celsius
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def min_temp(self) -> float:
        """Minimum settable setpoint in the device's current unit."""
        return MIN_TEMP if self.status.celsius else MIN_TEMP_F

    @property
    def max_temp(self) -> float:
        """Maximum settable setpoint in the device's current unit."""
        return MAX_TEMP if self.status.celsius else MAX_TEMP_F

    @property
    def hvac_mode(self) -> HVACMode:
        """Off when powered down, auto when following the on-board schedule, else heat."""
        if not self.status.is_on:
            return HVACMode.OFF
        return HVACMode.AUTO if self.status.schedule_enabled else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Return whether the element is actually calling for heat, with hysteresis.

        The heater is bang-bang thermostatic — it draws full power (or the Eco cap)
        only while the room is below the setpoint, and idles otherwise. There is no
        explicit "heating" flag in the cloud data (PowerLevel is inert at 255), so
        derive it from room vs target. A deadband holds the last action while the room
        sits within ``HVAC_ACTION_DEADBAND`` of the setpoint, so a room hovering on the
        whole-degree setpoint doesn't flip the action every update.
        """
        if not self.status.is_on:
            self._last_hvac_action = None
            return HVACAction.OFF
        current = self.status.current_temperature
        target = self.status.target_temperature
        if current is None or target is None:
            return self._last_hvac_action or HVACAction.IDLE
        if current <= target - HVAC_ACTION_DEADBAND:
            action = HVACAction.HEATING
        elif current >= target + HVAC_ACTION_DEADBAND:
            action = HVACAction.IDLE
        else:
            action = self._last_hvac_action or HVACAction.IDLE
        self._last_hvac_action = action
        return action

    @property
    def current_temperature(self) -> float | None:
        """Return the measured room temperature."""
        return self.status.current_temperature

    @property
    def target_temperature(self) -> int | None:
        """Return the target temperature."""
        return self.status.target_temperature

    @property
    def preset_mode(self) -> str:
        """Eco (power-limited) vs none.

        Eco (``PowerLimit``) is the only power/heat lever the firmware exposes, so it
        maps to ``PRESET_ECO``. It is independent of the hvac mode and persists across
        heat/auto — the on-board schedule drives setpoints, not Eco.
        """
        return PRESET_ECO if self.status.eco else PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch between off, manual heat, and the on-board weekly schedule (auto)."""
        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await self._async_guard(client.async_set_power(False))
        else:
            if not self.status.is_on:
                await self._async_guard(client.async_set_power(True))
            # AUTO follows the device's weekly schedule; HEAT uses the manual setpoint.
            await self._async_guard(
                client.async_set_schedule_enabled(hvac_mode == HVACMode.AUTO)
            )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Enable Eco (power limit) for PRESET_ECO, disable it otherwise."""
        await self._async_guard(
            self.coordinator.client.async_set_eco(preset_mode == PRESET_ECO)
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the heater on."""
        await self._async_guard(self.coordinator.client.async_set_power(True))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the heater off."""
        await self._async_guard(self.coordinator.client.async_set_power(False))
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature in the device's current unit.

        Rejected while the on-board weekly schedule (AUTO) is driving the setpoint —
        the schedule owns the temperature, so the user must switch to Heat first.
        """
        if self.hvac_mode == HVACMode.AUTO:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="set_temperature_in_auto",
            )
        await self._async_guard(
            self.coordinator.client.async_set_temperature(
                int(kwargs[ATTR_TEMPERATURE]), unit=self.status.temperature_unit
            )
        )
        await self.coordinator.async_request_refresh()
