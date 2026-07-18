"""Tests for offline availability and command-error handling."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import Device
from delonghi_comfort.exceptions import CommandTimeoutError
import pytest

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_OFFLINE_DEVICE = Device.from_dict(
    {
        "machineName": "EUPDL01COM000000004875",
        "serialNumber": "90:70:69:90:93:74",
        "machineModel": "TRD5WIFI",
        "status": "OFFLINE",
    }
)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return str(hass.states.async_entity_ids("climate")[0])


async def test_entities_go_unavailable_when_heater_offline(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """When the device reports offline, entities become unavailable."""
    cid = await _setup(hass, mock_config_entry)
    assert hass.states.get(cid).state != STATE_UNAVAILABLE

    mock_client.async_get_devices = AsyncMock(return_value=[_OFFLINE_DEVICE])
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(cid).state == STATE_UNAVAILABLE


async def test_command_failure_raises_home_assistant_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A library error during a command surfaces as HomeAssistantError, not a traceback."""
    cid = await _setup(hass, mock_config_entry)
    mock_client.async_set_temperature = AsyncMock(
        side_effect=CommandTimeoutError("no ack")
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 23},
            blocking=True,
        )
