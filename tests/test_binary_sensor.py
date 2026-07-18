"""Tests for the alarm binary sensors (aggregate + per-category)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus

from custom_components.delonghi_comfort.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
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
    eid = er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, f"{THING}_{key}")
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
