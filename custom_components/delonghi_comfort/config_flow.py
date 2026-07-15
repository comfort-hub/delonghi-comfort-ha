"""Config flow for De'Longhi Comfort."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from delonghi_comfort import (
    AuthenticationError,
    DelonghiComfort,
    DelonghiComfortError,
    Device,
    GigyaCredentials,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CREDENTIALS,
    CONF_MODEL,
    CONF_REGION,
    CONF_SERIAL_NUMBER,
    CONF_THING_NAME,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class DelonghiComfortConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the De'Longhi Comfort config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise transient flow state."""
        self._email: str = ""
        self._credentials: GigyaCredentials | None = None
        self._devices: list[Device] = []

    async def _authenticate(
        self, email: str, password: str
    ) -> tuple[GigyaCredentials, list[Device]]:
        client = DelonghiComfort(session=async_get_clientsession(self.hass))
        credentials = await client.async_login(email, password)
        devices = await client.async_get_devices()
        return credentials, devices

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                credentials, devices = await self._authenticate(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except DelonghiComfortError:
                errors["base"] = "cannot_connect"
            else:
                self._email = user_input[CONF_EMAIL]
                self._credentials = credentials
                self._devices = devices
                if not devices:
                    errors["base"] = "no_devices"
                elif len(devices) == 1:
                    return await self._create_entry(devices[0])
                else:
                    return await self.async_step_device()
        return self.async_show_form(
            step_id="user", data_schema=_USER_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which appliance to add when several exist."""
        if user_input is not None:
            device = next(
                d for d in self._devices if d.thing_name == user_input[CONF_THING_NAME]
            )
            return await self._create_entry(device)
        options = [
            selector.SelectOptionDict(
                value=d.thing_name, label=f"{d.model} ({d.serial_number})"
            )
            for d in self._devices
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_THING_NAME): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="device", data_schema=schema)

    async def _create_entry(self, device: Device) -> ConfigFlowResult:
        assert self._credentials is not None
        await self.async_set_unique_id(device.thing_name)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.model or "De'Longhi Comfort",
            data={
                CONF_EMAIL: self._email,
                CONF_CREDENTIALS: asdict(self._credentials),
                CONF_THING_NAME: device.thing_name,
                CONF_REGION: "eu",
                CONF_SERIAL_NUMBER: device.serial_number,
                CONF_MODEL: device.model,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the stored session is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again and refresh the stored credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                credentials, _ = await self._authenticate(
                    reauth_entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except DelonghiComfortError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_CREDENTIALS: asdict(credentials)},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            description_placeholders={CONF_EMAIL: reauth_entry.data[CONF_EMAIL]},
            errors=errors,
        )
