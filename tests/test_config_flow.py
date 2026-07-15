"""Tests for the De'Longhi Comfort config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from delonghi_comfort import AuthenticationError

from custom_components.delonghi_comfort.const import CONF_THING_NAME, DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from .conftest import THING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


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
