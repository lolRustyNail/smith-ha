"""Smith Water Heater integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmithApiClient, SmithApiAuthError, SmithApiConnectionError, SmithSessionData
from .const import (
    CONF_AUTH_TOKEN,
    CONF_FAMILY_ID,
    CONF_FAMILY_UK,
    CONF_MOBILE,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SmithDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smith Water Heater from a config entry."""
    session_data = SmithSessionData(
        auth_token=entry.data[CONF_AUTH_TOKEN],
        user_id=entry.data[CONF_USER_ID],
        family_id=entry.data[CONF_FAMILY_ID],
        family_uk=entry.data.get(CONF_FAMILY_UK, ""),
        mobile=entry.data.get(CONF_MOBILE, ""),
    )

    session = async_get_clientsession(hass)
    client = SmithApiClient(session, session_data)

    # Validate connection
    try:
        await client.async_validate()
    except SmithApiAuthError as err:
        raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
    except SmithApiConnectionError as err:
        raise ConfigEntryNotReady(f"Connection failed: {err}") from err

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SmithDataUpdateCoordinator(hass, client, scan_interval)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
