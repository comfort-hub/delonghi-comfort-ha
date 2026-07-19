"""Tests for the climate entity, incl. the schedule HVACMode.AUTO mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus, TemperatureUnit
import pytest

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_ECO,
    PRESET_NONE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_BASE = {
    "DeviceStatus": 1,
    "TempSetPoint": 22,
    "RoomTemp": 200,
    "PowerLimit": False,
    "TempUnit": True,
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return str(hass.states.async_entity_ids("climate")[0])


async def test_hvac_modes_include_auto(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The climate entity offers off/heat/auto."""
    cid = await _setup(hass, mock_config_entry)
    modes = hass.states.get(cid).attributes["hvac_modes"]
    assert HVACMode.AUTO in modes
    assert HVACMode.HEAT in modes
    assert HVACMode.OFF in modes


async def test_hvac_mode_is_auto_when_schedule_enabled(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A running heater with the schedule enabled reports hvac_mode auto."""
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "ScheduleEnable": True})
    )
    cid = await _setup(hass, mock_config_entry)
    assert hass.states.get(cid).state == HVACMode.AUTO


async def test_set_auto_enables_schedule(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Selecting auto turns the on-board schedule on."""
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: cid, ATTR_HVAC_MODE: HVACMode.AUTO},
        blocking=True,
    )
    mock_client.async_set_schedule_enabled.assert_awaited_with(True)


async def test_set_heat_disables_schedule(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Selecting heat turns the on-board schedule off (manual setpoint)."""
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: cid, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_client.async_set_schedule_enabled.assert_awaited_with(False)


async def test_set_off_powers_down(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Selecting off powers the heater down."""
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: cid, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    mock_client.async_set_power.assert_awaited_with(False)


async def test_celsius_device_bounds(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A Celsius device reports the 15-28 °C setpoint range."""
    cid = await _setup(hass, mock_config_entry)
    attrs = hass.states.get(cid).attributes
    assert attrs["min_temp"] == 15
    assert attrs["max_temp"] == 28


async def test_fahrenheit_device_bounds(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A Fahrenheit device reports the 41-82 °F setpoint range (native unit)."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "TempUnit": False})
    )
    cid = await _setup(hass, mock_config_entry)
    attrs = hass.states.get(cid).attributes
    assert attrs["min_temp"] == 41
    assert attrs["max_temp"] == 82


async def test_set_temperature_on_celsius_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setting the temperature on a Celsius device sends a Celsius setpoint."""
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 20},
        blocking=True,
    )
    mock_client.async_set_temperature.assert_awaited_once_with(
        20, unit=TemperatureUnit.CELSIUS
    )


async def test_set_temperature_on_fahrenheit_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setting the temperature on a Fahrenheit device sends a Fahrenheit setpoint."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "TempUnit": False})
    )
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 70},
        blocking=True,
    )
    mock_client.async_set_temperature.assert_awaited_once_with(
        70, unit=TemperatureUnit.FAHRENHEIT
    )


async def test_hvac_action_is_omitted(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """With no heating flag in the cloud, we don't claim an hvac_action.

    The reading is event-driven and often stale, so deriving heating/idle from it
    would be a guess; peers with no flag (evohome, Adax, Tuya, LG ThinQ) return None.
    """
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported(
            {**_BASE, "RoomTemp": 180, "TempSetPoint": 22}
        )
    )
    cid = await _setup(hass, mock_config_entry)
    assert hass.states.get(cid).attributes.get("hvac_action") is None


async def test_set_temperature_is_optimistic(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The commanded setpoint shows immediately, before the device echoes it back."""
    cid = await _setup(hass, mock_config_entry)  # reported TempSetPoint stays 22
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 25},
        blocking=True,
    )
    assert hass.states.get(cid).attributes[ATTR_TEMPERATURE] == 25  # optimistic


async def test_optimistic_clears_once_device_confirms(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Once the reported setpoint matches, the override clears and later changes show."""
    cid = await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 25},
        blocking=True,
    )
    # Device confirms 25 -> the override is cleared.
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "TempSetPoint": 25})
    )
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(cid).attributes[ATTR_TEMPERATURE] == 25

    # A later external change is no longer masked by a stuck override.
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "TempSetPoint": 26})
    )
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(cid).attributes[ATTR_TEMPERATURE] == 26


async def test_preset_mode_reflects_eco(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The climate preset reports eco while the power limit is on."""
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "PowerLimit": True})
    )
    cid = await _setup(hass, mock_config_entry)
    state = hass.states.get(cid)
    assert state.attributes["preset_mode"] == PRESET_ECO
    assert set(state.attributes["preset_modes"]) == {PRESET_NONE, PRESET_ECO}


async def test_set_preset_toggles_power_limit(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Selecting the eco/none preset toggles the library power-limit setter."""
    cid = await _setup(hass, mock_config_entry)  # _BASE PowerLimit False -> none
    assert hass.states.get(cid).attributes["preset_mode"] == PRESET_NONE

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: cid, ATTR_PRESET_MODE: PRESET_ECO},
        blocking=True,
    )
    mock_client.async_set_eco.assert_awaited_with(True)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: cid, ATTR_PRESET_MODE: PRESET_NONE},
        blocking=True,
    )
    mock_client.async_set_eco.assert_awaited_with(False)


async def test_set_temperature_rejected_in_auto(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setting a target temperature while the on-board schedule (AUTO) runs is rejected."""
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported({**_BASE, "ScheduleEnable": True})
    )
    cid = await _setup(hass, mock_config_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 20},
            blocking=True,
        )
    mock_client.async_set_temperature.assert_not_awaited()
