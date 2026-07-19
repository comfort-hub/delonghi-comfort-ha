"""Tests for the timer and diagnostic sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus

from custom_components.delonghi_comfort.const import DOMAIN
from homeassistant.const import STATE_ON
from homeassistant.helpers import entity_registry as er

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_STATUS = {
    "DeviceStatus": 1,
    "TempUnit": True,
    "TimerRemain": 45,
    "TimerStatus": 1,
    "LanIpAddress": "192.168.1.50",
    "RunningPartition": 1,
    "OTAdownloadCompleteness": 30,
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


def _state(hass: HomeAssistant, platform: str, key: str) -> str:
    """Resolve an entity by its unique id and return its state."""
    eid = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{THING}_{key}")
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    return str(state.state)


async def test_timer_remaining_sensor(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The timer-remaining sensor reports the minutes left."""
    await _setup(hass, mock_config_entry, mock_client)
    assert _state(hass, "sensor", "timer_remaining") == "45"


async def test_timer_active_binary_sensor(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The timer-active binary sensor is on while a timer runs."""
    await _setup(hass, mock_config_entry, mock_client)
    assert _state(hass, "binary_sensor", "timer_active") == STATE_ON


async def test_last_reported_sensor(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The last-reported sensor exposes when the device last updated its shadow."""
    ts = 1_700_000_000
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported(
            _STATUS, metadata={"RoomTemp": {"timestamp": ts}}
        )
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert (
        _state(hass, "sensor", "last_reported")
        == datetime.fromtimestamp(ts, tz=UTC).isoformat()
    )


_LOW_VALUE_DIAGNOSTICS = ("lan_ip", "firmware_partition", "ota_progress")


async def test_low_value_diagnostics_disabled_by_default(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """LAN IP, firmware partition and OTA progress are registered but off by default."""
    await _setup(hass, mock_config_entry, mock_client)
    registry = er.async_get(hass)
    for key in _LOW_VALUE_DIAGNOSTICS:
        eid = registry.async_get_entity_id("sensor", DOMAIN, f"{THING}_{key}")
        assert eid is not None, key
        entry = registry.async_get(eid)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
        assert hass.states.get(eid) is None  # disabled -> no state


async def test_low_value_diagnostics_report_when_enabled(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Once a user enables them, the diagnostic sensors report their values."""
    await _setup(hass, mock_config_entry, mock_client)
    registry = er.async_get(hass)
    for key in _LOW_VALUE_DIAGNOSTICS:
        eid = registry.async_get_entity_id("sensor", DOMAIN, f"{THING}_{key}")
        assert eid is not None
        registry.async_update_entity(eid, disabled_by=None)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "lan_ip") == "192.168.1.50"
    assert _state(hass, "sensor", "firmware_partition") == "1"
    assert _state(hass, "sensor", "ota_progress") == "30"
