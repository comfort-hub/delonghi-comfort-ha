"""Tests for the diagnostics platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from delonghi_comfort import MachineStatus

from custom_components.delonghi_comfort.diagnostics import (
    async_get_config_entry_diagnostics,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.core import HomeAssistant

_REDACTED = "**REDACTED**"


async def test_diagnostics_redacts_secrets_and_includes_status(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Diagnostics expose the live shadow but redact credentials/identifiers."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Secrets are redacted.
    assert diag["entry_data"]["credentials"] == _REDACTED
    assert diag["entry_data"]["email"] == _REDACTED
    # The live status is included for debugging.
    assert diag["status"]["DeviceStatus"] == 1
    assert diag["status"]["TempSetPoint"] == 22


async def test_diagnostics_includes_report_timestamps(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Diagnostics carry the shadow's per-field report timestamps for staleness triage."""
    mock_client.async_get_status = AsyncMock(
        return_value=MachineStatus.from_reported(
            {"DeviceStatus": 1}, metadata={"RoomTemp": {"timestamp": 1_700_000_000}}
        )
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diag["status_metadata"]["RoomTemp"] == {"timestamp": 1_700_000_000}
