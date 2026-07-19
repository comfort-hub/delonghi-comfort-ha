"""DataUpdateCoordinator for De'Longhi Comfort.

The library keeps a live MQTT connection and pushes ``MachineStatus`` updates in real
time; the coordinator forwards those to entities via ``async_set_updated_data`` and also
polls on an interval as a safety net.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from delonghi_comfort import (
    AuthenticationError,
    ConnectionState,
    DelonghiComfort,
    DelonghiComfortError,
    GigyaCredentials,
    MachineCapabilities,
    MachineStatus,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CREDENTIALS,
    CONF_REGION,
    CONF_THING_NAME,
    DOMAIN,
    JWT_REFRESH_INTERVAL_SECONDS,
    SCAN_INTERVAL_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

type DelonghiConfigEntry = ConfigEntry[DelonghiComfortCoordinator]


class DelonghiComfortCoordinator(DataUpdateCoordinator[MachineStatus]):
    """Own the live connection to one heater and expose its status to entities."""

    config_entry: DelonghiConfigEntry
    capabilities: MachineCapabilities | None = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED

    def __init__(self, hass: HomeAssistant, config_entry: DelonghiConfigEntry) -> None:
        """Initialise the coordinator and its underlying client."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            # The heater's shadow is static between control events, so the poll
            # usually re-reads an identical MachineStatus. Skip the redundant
            # entity writes on unchanged data (MachineStatus compares by value).
            always_update=False,
        )
        credentials = GigyaCredentials(**config_entry.data[CONF_CREDENTIALS])
        self.client = DelonghiComfort(
            session=async_get_clientsession(hass),
            region=config_entry.data[CONF_REGION],
            credentials=credentials,
        )
        self._unsub_push: Callable[[], None] | None = None
        self._unsub_jwt: Callable[[], None] | None = None

    async def _async_setup(self) -> None:
        """Authenticate and open the live connection once, before the first refresh."""
        self.client.add_connection_listener(self._handle_connection)
        try:
            await self.client.async_refresh_jwt()
            await self.client.async_connect(self.config_entry.data[CONF_THING_NAME])
            self.capabilities = await self.client.async_get_capabilities()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DelonghiComfortError as err:
            raise UpdateFailed(str(err)) from err
        self._unsub_push = self.client.add_status_listener(self._handle_push)
        self._unsub_jwt = async_track_time_interval(
            self.hass,
            self._async_refresh_token,
            timedelta(seconds=JWT_REFRESH_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> MachineStatus:
        """Poll the current status (the live connection also pushes updates)."""
        try:
            return await self._async_fetch()
        except AuthenticationError:
            # The JWT may have lapsed. Re-mint it from the stored credentials and
            # retry once, so an expired token self-heals in place instead of
            # surfacing as a reauth prompt (and a spell of unavailability). Only a
            # genuinely dead session — the refresh itself failing — escalates.
            try:
                await self.client.async_refresh_jwt()
                return await self._async_fetch()
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DelonghiComfortError as err:
                raise UpdateFailed(str(err)) from err
        except DelonghiComfortError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_fetch(self) -> MachineStatus:
        """Verify connectivity and read the current status shadow."""
        await self._async_verify_online()
        return await self.client.async_get_status()

    async def _async_refresh_token(self, _now: datetime) -> None:
        """Proactively re-mint the JWT so reconnects never hit an expired token."""
        try:
            await self.client.async_refresh_jwt()
        except DelonghiComfortError as err:
            # Transient failures are fine — the next poll's self-heal or the next
            # scheduled refresh recovers; a dead session surfaces via reauth there.
            _LOGGER.debug("proactive JWT refresh failed: %s", err)

    async def _async_verify_online(self) -> None:
        """Raise ``UpdateFailed`` when the heater is offline.

        The cloud keeps serving the last shadow document after the heater drops
        off Wi-Fi, so a plain status read cannot tell live from stale. A REST
        device lookup gives the real connectivity, and re-exercises the JWT so an
        expired token surfaces as ``AuthenticationError`` (-> reauth) instead of a
        silent stall.
        """
        thing = self.config_entry.data[CONF_THING_NAME]
        devices = await self.client.async_get_devices()
        if not any(d.thing_name == thing and d.online for d in devices):
            raise UpdateFailed("the heater is offline")

    @callback
    def _handle_push(self, status: MachineStatus) -> None:
        """Forward a pushed status update to entities."""
        self.async_set_updated_data(status)

    @callback
    def _handle_connection(self, state: ConnectionState) -> None:
        """Track the live-connection state and refresh dependent entities."""
        self.connection_state = state
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Close the live connection when the entry is unloaded."""
        if self._unsub_jwt is not None:
            self._unsub_jwt()
            self._unsub_jwt = None
        if self._unsub_push is not None:
            self._unsub_push()
            self._unsub_push = None
        await self.client.async_close()
        await super().async_shutdown()
