"""Config flow for Smith Water Heater integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SmithApiAuthError,
    SmithApiConnectionError,
    SmithApiClient,
    SmithSessionData,
    parse_session_payload,
)
from .const import (
    CONF_AUTH_TOKEN,
    CONF_FAMILY_ID,
    CONF_FAMILY_UK,
    CONF_MOBILE,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("session_json"): str,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
        int, vol.Range(min=10, max=600)
    ),
})


async def _validate_session(
    hass: HomeAssistant, session_data: SmithSessionData
) -> dict[str, Any]:
    """Validate session data by calling the API."""
    session = async_get_clientsession(hass)
    client = SmithApiClient(session, session_data)
    return await client.async_validate()


class SmithWaterHeaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smith Water Heater."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_json = user_input["session_json"]
            session_data = parse_session_payload(raw_json)

            if session_data is None:
                errors["session_json"] = "invalid_json"
            else:
                try:
                    await _validate_session(self.hass, session_data)
                except SmithApiAuthError:
                    errors["base"] = "invalid_auth"
                except SmithApiConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error during validation")
                    errors["base"] = "unknown"
                else:
                    unique_id = f"smith:{session_data.user_id}:{session_data.family_id}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    title = f"A.O. Smith ({session_data.user_id})"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_AUTH_TOKEN: session_data.auth_token,
                            CONF_USER_ID: session_data.user_id,
                            CONF_FAMILY_ID: session_data.family_id,
                            CONF_FAMILY_UK: session_data.family_uk,
                            CONF_MOBILE: session_data.mobile,
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
