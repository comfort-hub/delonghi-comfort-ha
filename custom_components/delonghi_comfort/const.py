"""Constants for the De'Longhi Comfort integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "delonghi_comfort"
MANUFACTURER: Final = "De'Longhi"

# Config entry keys.
CONF_CREDENTIALS: Final = "credentials"
CONF_THING_NAME: Final = "thing_name"
CONF_REGION: Final = "region"
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_MODEL: Final = "model"

# Poll interval (seconds). The live connection pushes updates in real time; this is a
# safety-net refresh in case a push is missed.
SCAN_INTERVAL_SECONDS: Final = 60

# How often to proactively re-mint the Gigya JWT. The token is long-lived, but
# refreshing well ahead of expiry keeps every hourly MQTT reconnect using a valid
# token, so an expiry never surfaces as a reauth prompt / unavailability.
JWT_REFRESH_INTERVAL_SECONDS: Final = 6 * 60 * 60

# How long to trust an optimistically-shown command value before the device confirms
# it. On expiry the entity reverts to the reported state and raises a Repair issue, so
# a command that was accepted but never applied is never left looking successful.
COMMAND_CONFIRM_TIMEOUT_SECONDS: Final = 60

# The Dragon 5 accepts whole-degree setpoints in this range. The firmware caps the
# setpoint at 28 °C (higher values are rejected — matches the physical dial's ceiling).
MIN_TEMP: Final = 15
MAX_TEMP: Final = 28

# Fahrenheit setpoint range when the device displays °F. Confirmed from the app
# (min 41 °F ≈ 5 °C — lower than a naive conversion of the °C minimum; max 82 °F).
MIN_TEMP_F: Final = 41
MAX_TEMP_F: Final = 82
