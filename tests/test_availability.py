"""Tests for offline availability and command-error handling."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import AuthenticationError, Device
from delonghi_comfort.exceptions import CommandTimeoutError
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.delonghi_comfort.const import JWT_REFRESH_INTERVAL_SECONDS
from homeassistant import config_entries
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

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

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: cid, ATTR_TEMPERATURE: 23},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"


_ONLINE_DEVICE = Device.from_dict(
    {
        "machineName": "EUPDL01COM000000004875",
        "serialNumber": "90:70:69:90:93:74",
        "machineModel": "TRD5WIFI",
        "status": "ONLINE",
    }
)


async def test_expired_jwt_self_heals_without_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """An expired JWT is re-minted and retried within the poll — no reauth, no blip."""
    await _setup(hass, mock_config_entry)

    attempts = {"n": 0}

    async def _devices() -> list[Device]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise AuthenticationError("token expired")
        return [_ONLINE_DEVICE]

    mock_client.async_get_devices = AsyncMock(side_effect=_devices)
    mock_client.async_refresh_jwt.reset_mock()

    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True  # recovered in-place
    mock_client.async_refresh_jwt.assert_awaited()  # re-minted the token
    assert not any(
        flow["context"]["source"] == config_entries.SOURCE_REAUTH
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_auth_rejection_triggers_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A persistent auth rejection (re-mint doesn't help) starts a reauth flow."""
    await _setup(hass, mock_config_entry)
    mock_client.async_get_devices = AsyncMock(
        side_effect=AuthenticationError("token expired")
    )

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert any(
        flow["context"]["source"] == config_entries.SOURCE_REAUTH
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_proactive_jwt_refresh_runs_on_schedule(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The JWT is proactively re-minted on a timer, before it can expire."""
    await _setup(hass, mock_config_entry)
    mock_client.async_refresh_jwt.reset_mock()

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=JWT_REFRESH_INTERVAL_SECONDS + 1)
    )
    await hass.async_block_till_done()

    mock_client.async_refresh_jwt.assert_awaited()
