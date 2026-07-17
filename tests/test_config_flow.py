"""Tests for the De'Longhi Comfort config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import AuthenticationError, Device

from custom_components.delonghi_comfort.const import CONF_THING_NAME, DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_SECOND = Device.from_dict(
    {
        "machineName": "EUPDL01COM000000009999",
        "serialNumber": "aa:bb:cc:dd:ee:ff",
        "machineModel": "TRD5WIFI",
        "status": "ONLINE",
    }
)


async def test_user_flow_single_device(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A single-device account creates the entry directly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "me@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == THING
    assert result["data"][CONF_THING_NAME] == THING


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Bad credentials surface an invalid_auth error."""
    mock_client.async_login.side_effect = AuthenticationError("bad")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "me@example.com", CONF_PASSWORD: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_no_devices(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """An account with no appliances surfaces a no_devices error."""
    mock_client.async_get_devices = AsyncMock(return_value=[])
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "me@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_user_flow_multiple_devices(
    hass: HomeAssistant, mock_client: MagicMock, device: Device
) -> None:
    """Several appliances prompt a device-selection step."""
    mock_client.async_get_devices = AsyncMock(return_value=[device, _SECOND])
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "me@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_THING_NAME: _SECOND.thing_name}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == _SECOND.thing_name


async def test_reauth_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Reauth re-authenticates and reloads the entry."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
