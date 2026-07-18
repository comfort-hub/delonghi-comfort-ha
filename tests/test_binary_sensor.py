"""Tests for the alarm binary sensors (aggregate + per-category)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import ConnectionState, MachineStatus

from custom_components.delonghi_comfort.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_STATUS = {
    "DeviceStatus": 1,
    "TempUnit": True,
    "alarms": {
        "TOS_alarm": True,
        "HTMAX_alarmPowerBoard": False,
        "PF_someFault": True,
    },
}


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported(_STATUS)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, key: str) -> str:
    eid = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{THING}_{key}"
    )
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    return str(state.state)


async def test_alarm_categories(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Each alarm flag maps to its category by prefix; the aggregate ORs them."""
    await _setup(hass, mock_config_entry, mock_client)
    assert _state(hass, "alarm") == STATE_ON  # aggregate: any alarm
    assert _state(hass, "safety_alarm") == STATE_ON  # TOS_alarm
    assert _state(hass, "overheat_alarm") == STATE_OFF  # HTMAX_* is False
    assert _state(hass, "problem_alarm") == STATE_ON  # PF_someFault (uncategorised)


async def test_connectivity_tracks_state_and_stays_available(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The connectivity sensor follows the live link and stays available when offline."""
    await _setup(hass, mock_config_entry, mock_client)
    # No CONNECTED event has fired yet, so the link reads as down.
    assert _state(hass, "connection") == STATE_OFF

    mock_client.fire_connection(ConnectionState.CONNECTED)
    await hass.async_block_till_done()
    assert _state(hass, "connection") == STATE_ON

    # Force the coordinator to fail (heater offline): a normal entity goes
    # unavailable, but the connectivity sensor must stay available to report state.
    mock_client.async_get_devices = AsyncMock(return_value=[])
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.last_update_success is False
    assert _state(hass, "alarm") == STATE_UNAVAILABLE
    assert _state(hass, "connection") == STATE_ON
