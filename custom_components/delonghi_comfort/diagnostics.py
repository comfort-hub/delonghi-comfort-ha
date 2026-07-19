"""Diagnostics support for De'Longhi Comfort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_CREDENTIALS, CONF_SERIAL_NUMBER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import DelonghiConfigEntry

TO_REDACT = {CONF_CREDENTIALS, CONF_SERIAL_NUMBER, "email"}
CAPS_REDACT = {"MAC", "SN"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DelonghiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (secrets redacted)."""
    coordinator = entry.runtime_data
    caps = coordinator.capabilities
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "status": dict(coordinator.data.raw) if coordinator.data else None,
        # Per-field report timestamps (metadata.reported) — reveals how stale each
        # reported value is, i.e. when the heater last reported it to the cloud.
        "status_metadata": dict(coordinator.data.metadata)
        if coordinator.data
        else None,
        "capabilities": (
            async_redact_data(dict(caps.raw), CAPS_REDACT) if caps else None
        ),
    }
