"""Tests for setup / unload and entity creation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus

from homeassistant.config_entries import ConfigEntryState

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """The entry loads, creates entities, and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.async_connect.assert_awaited_once()
    # entities across the platforms exist
    assert hass.states.async_entity_ids("climate")
    assert hass.states.async_entity_ids("switch")
    assert hass.states.async_entity_ids("select")
    assert hass.states.async_entity_ids("sensor")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.async_close.assert_awaited()


async def test_climate_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """The climate entity reflects the reported status."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    climate_id = hass.states.async_entity_ids("climate")[0]
    state = hass.states.get(climate_id)
    assert state is not None
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 20.0
    assert state.attributes["temperature"] == 22


async def test_idle_poll_does_not_notify_listeners(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Refreshes that return unchanged status don't churn listeners (always_update=False).

    The heater's shadow is static between control events, so idle 60s polls re-read
    an identical document — those must not re-notify entities.
    """
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data

    # Poll returns a fixed status; prime the coordinator with it first so it
    # becomes the "previous" data before we start counting.
    reported = {
        "DeviceStatus": 1,
        "TempSetPoint": 22,
        "RoomTemp": 200,
        "TempUnit": True,
    }
    mock_client.async_get_status = AsyncMock(
        side_effect=lambda: MachineStatus.from_reported(dict(reported))
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    calls = 0

    def _listener() -> None:
        nonlocal calls
        calls += 1

    coordinator.async_add_listener(_listener)

    # Further polls return an EQUAL (but distinct) MachineStatus -> no notify.
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert calls == 0  # unchanged data -> no listener notifications
