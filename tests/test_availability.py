"""Tests for offline availability and command-error handling."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import AuthenticationError, Device, MachineStatus
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

from .conftest import MAC, THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_OFFLINE_DEVICE = Device.from_dict(
    {
        "machineName": "EUPDL01COM000000000001",
        "serialNumber": "02:00:00:00:00:01",
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
        "machineName": "EUPDL01COM000000000001",
        "serialNumber": "02:00:00:00:00:01",
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


async def test_dead_session_triggers_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Reauth starts only when the session is dead — i.e. re-minting the JWT fails."""
    await _setup(hass, mock_config_entry)
    mock_client.async_get_devices = AsyncMock(
        side_effect=AuthenticationError("token rejected")
    )
    mock_client.async_refresh_jwt = AsyncMock(
        side_effect=AuthenticationError("session revoked")
    )

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert any(
        flow["context"]["source"] == config_entries.SOURCE_REAUTH
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_transient_cloud_403_fails_soft_not_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A transient cloud 403 (a freshly-minted token is still rejected) fails soft.

    Re-minting succeeds — the session is fine — so a persisting rejection is a
    flaky-cloud transient, not bad credentials: mark the update failed (retry next
    poll), never nag the user for reauth.
    """
    await _setup(hass, mock_config_entry)
    mock_client.async_get_devices = AsyncMock(
        side_effect=AuthenticationError("devices request unauthorized (HTTP 403)")
    )
    # async_refresh_jwt keeps its default (succeeds): the session is valid.

    coordinator = mock_config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False  # transient -> unavailable, retries
    assert not any(
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


async def _go_offline_then_push(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: MagicMock, back: Device
) -> str:
    """Take the heater offline, queue `back` as the next poll answer, and push."""
    cid = await _setup(hass, entry)
    offline = Device.from_dict(
        {"machineName": THING, "serialNumber": MAC, "status": "OFFLINE"}
    )
    mock_client.async_get_devices = AsyncMock(return_value=[offline])
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(cid).state == STATE_UNAVAILABLE

    mock_client.async_get_devices = AsyncMock(return_value=[back])
    push = mock_client.add_status_listener.call_args[0][0]
    push(MachineStatus.from_reported({"DeviceStatus": 1, "TempSetPoint": 22}))
    # Let the debounced refresh (cooldown after the poll above) fire.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    return cid


async def test_push_while_offline_stays_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A stale shadow pushed after reconnect must not mark an offline heater available."""
    offline = Device.from_dict(
        {"machineName": THING, "serialNumber": MAC, "status": "OFFLINE"}
    )
    cid = await _go_offline_then_push(hass, mock_config_entry, mock_client, offline)

    assert hass.states.get(cid).state == STATE_UNAVAILABLE
    mock_client.async_get_devices.assert_awaited()  # a refresh was requested


async def test_push_after_heater_returns_restores_availability(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    device: Device,
) -> None:
    """The refresh a push triggers brings entities back once the poll sees it online."""
    cid = await _go_offline_then_push(hass, mock_config_entry, mock_client, device)

    assert hass.states.get(cid).state != STATE_UNAVAILABLE
