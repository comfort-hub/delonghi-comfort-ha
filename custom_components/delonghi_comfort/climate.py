"""Climate platform for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from .const import (
    COMMAND_CONFIRM_TIMEOUT_SECONDS,
    DOMAIN,
    MAX_TEMP,
    MAX_TEMP_F,
    MIN_TEMP,
    MIN_TEMP_F,
)
from .entity import DelonghiComfortEntity

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import DelonghiComfortCoordinator, DelonghiConfigEntry

PARALLEL_UPDATES = 1


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
    # Optimistically-commanded values shown until the device echoes them back.
    _optimistic_hvac_mode: HVACMode | None = None
    _optimistic_target: int | None = None
    _optimistic_preset: str | None = None
    _confirm_unsub: CALLBACK_TYPE | None = None

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

    def _real_hvac_mode(self) -> HVACMode:
        """Return the hvac mode implied by the reported status (ignoring overrides)."""
        if not self.status.is_on:
            return HVACMode.OFF
        return HVACMode.AUTO if self.status.schedule_enabled else HVACMode.HEAT

    def _real_preset_mode(self) -> str:
        """Return the preset implied by the reported status (ignoring overrides)."""
        return PRESET_ECO if self.status.eco else PRESET_NONE

    @property
    def hvac_mode(self) -> HVACMode:
        """Optimistic override while a command is pending, else the reported mode."""
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        return self._real_hvac_mode()

    @property
    def current_temperature(self) -> float | None:
        """Return the measured room temperature."""
        return self.status.current_temperature

    @property
    def target_temperature(self) -> int | None:
        """Optimistic override while a command is pending, else the reported setpoint."""
        if self._optimistic_target is not None:
            return self._optimistic_target
        return self.status.target_temperature

    @property
    def preset_mode(self) -> str:
        """Optimistic override while a command is pending, else the reported preset.

        Eco (``PowerLimit``) is the only power/heat lever the firmware exposes, so it
        maps to ``PRESET_ECO``. It is independent of the hvac mode and persists across
        heat/auto — the on-board schedule drives setpoints, not Eco.
        """
        if self._optimistic_preset is not None:
            return self._optimistic_preset
        return self._real_preset_mode()

    def _set_optimistic(
        self,
        *,
        hvac_mode: HVACMode | None = None,
        target: int | None = None,
        preset: str | None = None,
    ) -> None:
        """Show the just-commanded value immediately, pending the device's echo."""
        if hvac_mode is not None:
            self._optimistic_hvac_mode = hvac_mode
        if target is not None:
            self._optimistic_target = target
        if preset is not None:
            self._optimistic_preset = preset
        self.async_write_ha_state()
        self._schedule_confirm_timeout()

    def _has_pending(self) -> bool:
        return (
            self._optimistic_hvac_mode is not None
            or self._optimistic_target is not None
            or self._optimistic_preset is not None
        )

    @property
    def _issue_id(self) -> str:
        return f"command_unconfirmed_{self.coordinator.config_entry.entry_id}"

    def _schedule_confirm_timeout(self) -> None:
        """Start/restart the window for the device to confirm the optimistic value."""
        self._cancel_confirm_timeout()
        self._confirm_unsub = async_call_later(
            self.hass, COMMAND_CONFIRM_TIMEOUT_SECONDS, self._confirm_timeout
        )

    def _cancel_confirm_timeout(self) -> None:
        if self._confirm_unsub is not None:
            self._confirm_unsub()
            self._confirm_unsub = None

    def _confirm_all(self) -> None:
        """Stop the timer and clear the issue once every override is confirmed."""
        self._cancel_confirm_timeout()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    def _reconcile(self) -> None:
        """Clear each optimistic override the reported status now confirms."""
        if (
            self._optimistic_hvac_mode is not None
            and self._real_hvac_mode() == self._optimistic_hvac_mode
        ):
            self._optimistic_hvac_mode = None
        if (
            self._optimistic_target is not None
            and self.status.target_temperature == self._optimistic_target
        ):
            self._optimistic_target = None
        if (
            self._optimistic_preset is not None
            and self._real_preset_mode() == self._optimistic_preset
        ):
            self._optimistic_preset = None

    @callback
    def _confirm_timeout(self, _now: datetime) -> None:
        """Revert a never-confirmed optimistic value to truth and flag it for the user."""
        self._confirm_unsub = None
        # A no-op command, or an echo whose unchanged shadow was deduped by the
        # coordinator, leaves no reconciling update — re-check truth before alarming.
        self._reconcile()
        if not self._has_pending():
            self._confirm_all()
            return
        self._optimistic_hvac_mode = None
        self._optimistic_target = None
        self._optimistic_preset = None
        self.async_write_ha_state()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="command_unconfirmed",
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the confirm timer and clear the issue on unload."""
        self._cancel_confirm_timeout()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Clear each optimistic override the device has now confirmed, then write state."""
        had_pending = self._has_pending()
        self._reconcile()
        # Only clear the Repair issue on a real pending -> confirmed transition, so a
        # routine idle poll (nothing pending) never erases a still-valid warning.
        if had_pending and not self._has_pending():
            self._confirm_all()
        super()._handle_coordinator_update()

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
        self._set_optimistic(hvac_mode=hvac_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Enable Eco (power limit) for PRESET_ECO, disable it otherwise."""
        await self._async_guard(
            self.coordinator.client.async_set_eco(preset_mode == PRESET_ECO)
        )
        self._set_optimistic(preset=preset_mode)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the heater on, into whichever mode the device will resolve to."""
        await self._async_guard(self.coordinator.client.async_set_power(True))
        # Powering on resumes AUTO if the on-board schedule is enabled, else manual HEAT.
        # Optimistically show that resolved mode so it reconciles against the echo.
        self._set_optimistic(
            hvac_mode=HVACMode.AUTO if self.status.schedule_enabled else HVACMode.HEAT
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the heater off."""
        await self._async_guard(self.coordinator.client.async_set_power(False))
        self._set_optimistic(hvac_mode=HVACMode.OFF)
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
        self._set_optimistic(target=int(kwargs[ATTR_TEMPERATURE]))
        await self.coordinator.async_request_refresh()
