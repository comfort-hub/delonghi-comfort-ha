"""Tests for setup / unload and entity creation."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
