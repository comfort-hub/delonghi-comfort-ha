"""Tests that the switch and number entities call the library setters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.delonghi_comfort.const import DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.helpers import entity_registry as er

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    eid = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{THING}_{key}")
    assert eid is not None
    return eid


async def test_switch_toggle_calls_the_setter(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Turning the eco switch on and off calls the library setter both ways."""
    await _setup(hass, mock_config_entry)
    eid = _entity_id(hass, "switch", "eco")

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: eid}, blocking=True
    )
    mock_client.async_set_eco.assert_awaited_with(True)

    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: eid}, blocking=True
    )
    mock_client.async_set_eco.assert_awaited_with(False)


async def test_number_set_value_calls_the_setter(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setting the brightness number calls the library setter with the value."""
    await _setup(hass, mock_config_entry)
    eid = _entity_id(hass, "number", "brightness")

    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: eid, "value": 2}, blocking=True
    )
    mock_client.async_set_brightness.assert_awaited_with(2)
