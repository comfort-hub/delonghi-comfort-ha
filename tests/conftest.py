"""Fixtures for the De'Longhi Comfort tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from delonghi_comfort import (
    Device,
    DiscoveredDevice,
    GigyaCredentials,
    MachineCapabilities,
    MachineStatus,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.delonghi_comfort.const import (
    CONF_CREDENTIALS,
    CONF_MODEL,
    CONF_REGION,
    CONF_SERIAL_NUMBER,
    CONF_THING_NAME,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Generator

pytest_plugins = ["pytest_homeassistant_custom_component"]

THING = "EUPDL01COM000000004875"
MAC = "90:70:69:90:93:74"

_REPORTED = {
    "DeviceStatus": 1,
    "TempSetPoint": 22,
    "RoomTemp": 200,
    "PowerLimit": False,
    "KeyLock": False,
    "NightModeEnable": False,
    "SilentEnable": True,
    "BrightnessLevel": 1,
    "TempUnit": True,
    "alarms": {"TOS_alarm": False},
}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in every test."""


@pytest.fixture
def device() -> Device:
    return Device.from_dict(
        {
            "machineName": THING,
            "serialNumber": MAC,
            "sku": "0110070300",
            "machineModel": "TRD5WIFI",
            "status": "ONLINE",
        }
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="TRD5WIFI",
        unique_id=THING,
        data={
            "email": "me@example.com",
            CONF_CREDENTIALS: {
                "api_key": "4_x",
                "session_token": "st",
                "session_secret": "secret",
            },
            CONF_THING_NAME: THING,
            CONF_REGION: "eu",
            CONF_SERIAL_NUMBER: MAC,
            CONF_MODEL: "TRD5WIFI",
        },
    )


@pytest.fixture
def mock_discover(device: Device) -> Generator[AsyncMock]:
    """Patch config_flow.async_discover, returning one eu device by default."""
    discover = AsyncMock(
        return_value=(
            GigyaCredentials("4_x", "st", "secret"),
            [DiscoveredDevice(device=device, region="eu")],
        )
    )
    with patch(
        "custom_components.delonghi_comfort.config_flow.async_discover", discover
    ):
        yield discover


@pytest.fixture
def mock_client(device: Device) -> Generator[MagicMock]:
    """Patch DelonghiComfort in both modules that construct it."""
    client = MagicMock()
    client.async_login = AsyncMock(return_value=GigyaCredentials("4_x", "st", "secret"))
    client.async_refresh_jwt = AsyncMock(return_value="jwt")
    client.async_get_devices = AsyncMock(return_value=[device])
    client.async_connect = AsyncMock()
    client.async_close = AsyncMock()
    client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported(_REPORTED)
    )
    client.async_get_capabilities = AsyncMock(
        return_value=MachineCapabilities.from_reported(
            {
                "MAC": MAC,
                "SN": MAC,
                "MachineModel": "TRD5WIFI",
                "FWWiFiVersion": "2.1.4",
            }
        )
    )
    client.add_status_listener = MagicMock(return_value=lambda: None)
    for method in (
        "async_set_power",
        "async_set_temperature",
        "async_set_eco",
        "async_set_child_lock",
        "async_set_night_mode",
        "async_set_silent",
        "async_set_brightness",
        "async_set_schedule_enabled",
    ):
        setattr(client, method, AsyncMock())

    with (
        patch(
            "custom_components.delonghi_comfort.coordinator.DelonghiComfort",
            return_value=client,
        ),
        patch(
            "custom_components.delonghi_comfort.config_flow.DelonghiComfort",
            return_value=client,
        ) as config_flow_ctor,
    ):
        # Expose the config-flow constructor so tests can assert its call args
        # (e.g. reauth passing the entry's stored region).
        client.config_flow_ctor = config_flow_ctor
        yield client
