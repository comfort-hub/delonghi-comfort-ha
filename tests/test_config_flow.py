"""Tests for the De'Longhi Comfort config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import ANY

from delonghi_comfort import (
    AuthenticationError,
    Device,
    DiscoveredDevice,
    GigyaCredentials,
    TransportError,
)

from custom_components.delonghi_comfort.const import (
    CONF_REGION,
    CONF_THING_NAME,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import AsyncMock, MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_CREDENTIALS = GigyaCredentials("4_x", "st", "secret")

_SECOND = Device.from_dict(
    {
        "machineName": "EUPDL01COM000000009999",
        "serialNumber": "aa:bb:cc:dd:ee:ff",
        "machineModel": "TRD5WIFI",
        "status": "ONLINE",
    }
)


def _option_labels(result: config_entries.ConfigFlowResult) -> list[str]:
    """Return the labels offered by the current form's device selector."""
    schema = result["data_schema"]
    assert schema is not None
    for key, value in schema.schema.items():
        if key == CONF_THING_NAME:
            return [str(option["label"]) for option in value.config["options"]]
    return []


async def _submit_credentials(
    hass: HomeAssistant,
) -> config_entries.ConfigFlowResult:
    """Start the user flow and submit valid-looking credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return cast(
        "config_entries.ConfigFlowResult",
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "me@example.com", CONF_PASSWORD: "pw"},
        ),
    )


async def test_user_flow_single_device(
    hass: HomeAssistant, mock_discover: AsyncMock, mock_client: MagicMock
) -> None:
    """A single eu device creates the entry directly, tagged region eu."""
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == THING
    assert result["data"][CONF_THING_NAME] == THING
    assert result["data"][CONF_REGION] == "eu"


async def test_user_flow_single_device_us(
    hass: HomeAssistant,
    mock_discover: AsyncMock,
    mock_client: MagicMock,
    device: Device,
) -> None:
    """A device discovered only in us stores region us."""
    mock_discover.return_value = (
        _CREDENTIALS,
        [DiscoveredDevice(device=device, region="us")],
    )
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REGION] == "us"


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, mock_discover: AsyncMock
) -> None:
    """Bad credentials surface an invalid_auth error."""
    mock_discover.side_effect = AuthenticationError("bad")
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_discover: AsyncMock
) -> None:
    """A transport failure surfaces a cannot_connect error."""
    mock_discover.side_effect = TransportError("boom")
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_no_devices(
    hass: HomeAssistant, mock_discover: AsyncMock
) -> None:
    """An account with no appliances surfaces a no_devices error."""
    mock_discover.return_value = (_CREDENTIALS, [])
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_discover: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Re-adding an already-configured appliance aborts."""
    mock_config_entry.add_to_hass(hass)
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_multiple_same_region(
    hass: HomeAssistant,
    mock_discover: AsyncMock,
    mock_client: MagicMock,
    device: Device,
) -> None:
    """Several devices in one region prompt a selection with no region labels."""
    mock_discover.return_value = (
        _CREDENTIALS,
        [
            DiscoveredDevice(device=device, region="eu"),
            DiscoveredDevice(device=_SECOND, region="eu"),
        ],
    )
    result = await _submit_credentials(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"
    assert all(" — " not in label for label in _option_labels(result))

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_THING_NAME: _SECOND.thing_name}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == _SECOND.thing_name
    assert result["data"][CONF_REGION] == "eu"


async def test_user_flow_multiple_cross_region(
    hass: HomeAssistant,
    mock_discover: AsyncMock,
    mock_client: MagicMock,
    device: Device,
) -> None:
    """Devices across regions show region labels; the choice sets the region."""
    mock_discover.return_value = (
        _CREDENTIALS,
        [
            DiscoveredDevice(device=device, region="eu"),
            DiscoveredDevice(device=_SECOND, region="us"),
        ],
    )
    result = await _submit_credentials(hass)
    assert result["step_id"] == "device"
    labels = _option_labels(result)
    assert any(label.endswith(" — EU") for label in labels)
    assert any(label.endswith(" — US") for label in labels)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_THING_NAME: _SECOND.thing_name}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REGION] == "us"


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
    # Reauth must build the client with the entry's stored region.
    mock_client.config_flow_ctor.assert_called_once_with(session=ANY, region="eu")
