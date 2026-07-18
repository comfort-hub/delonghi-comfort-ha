"""Tests for the climate entity, incl. the schedule HVACMode.AUTO mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID

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
