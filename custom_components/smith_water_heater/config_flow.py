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
    SmithApiError,
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

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._login_data: dict[str, str] = {}
        self._client: SmithApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose login method."""
        if user_input is not None:
            method = user_input["login_method"]
            if method == "phone":
                return await self.async_step_phone()
            return await self.async_step_legacy()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("login_method", default="phone"): vol.In({
                    "phone": "手机号登录",
                    "legacy": "粘贴会话 JSON（高级）",
                }),
            }),
        )

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Enter phone number and send SMS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mobile = user_input["mobile"]
            self._login_data["mobile"] = mobile

            session = async_get_clientsession(self.hass)
            self._client = SmithApiClient(
                session,
                SmithSessionData(auth_token="", user_id="", family_id="", family_uk=""),
            )

            try:
                await self._client.async_send_sms(mobile)
                return await self.async_step_sms_code()
            except SmithApiError as err:
                _LOGGER.debug("SMS without CAPTCHA failed: %s", err)
                # Need CAPTCHA — go to captcha step
                return await self.async_step_captcha()
            except SmithApiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error sending SMS")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({
                vol.Required("mobile"): str,
            }),
            errors=errors,
            description_placeholders={
                "captcha_url": "/local/smith-water-heater/captcha.html",
            },
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Enter Tencent CAPTCHA ticket and randstr."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ticket = user_input["ticket"]
            randstr = user_input["randstr"]
            mobile = self._login_data["mobile"]

            try:
                await self._client.async_send_sms(mobile, ticket=ticket, randstr=randstr)
                return await self.async_step_sms_code()
            except (SmithApiError, SmithApiConnectionError) as err:
                _LOGGER.error("SMS with CAPTCHA failed: %s", err)
                errors["base"] = "captcha_failed"
            except Exception:
                _LOGGER.exception("Unexpected error sending SMS with CAPTCHA")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema({
                vol.Required("ticket"): str,
                vol.Required("randstr"): str,
            }),
            errors=errors,
        )

    async def async_step_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Enter SMS verification code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            captcha = user_input["captcha"]
            mobile = self._login_data["mobile"]

            try:
                # Step 1: Login to get JWT token
                await self._client.async_login(mobile, captcha)

                # Step 2: Get userId
                user_id = await self._client.async_get_user_id(mobile)
                if not user_id:
                    raise SmithApiError("Could not determine userId")

                # Step 3: Get familyId and familyUk
                family_id, family_uk = await self._client.async_get_family_info(user_id)

                session_data = SmithSessionData(
                    auth_token=self._client.session_data.auth_token,
                    user_id=user_id,
                    family_id=family_id,
                    family_uk=family_uk,
                    mobile=mobile,
                )

                # Validate by fetching homepage
                await _validate_session(self.hass, session_data)

                unique_id = f"smith:{user_id}:{family_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"A.O. Smith ({mobile})",
                    data={
                        CONF_AUTH_TOKEN: session_data.auth_token,
                        CONF_USER_ID: user_id,
                        CONF_FAMILY_ID: family_id,
                        CONF_FAMILY_UK: family_uk,
                        CONF_MOBILE: mobile,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )
            except SmithApiAuthError:
                errors["base"] = "invalid_auth"
            except SmithApiConnectionError:
                errors["base"] = "cannot_connect"
            except SmithApiError as err:
                _LOGGER.error("Login error: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="sms_code",
            data_schema=vol.Schema({
                vol.Required("captcha"): str,
            }),
            errors=errors,
        )

    async def async_step_legacy(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Legacy: paste session JSON."""
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
            step_id="legacy",
            data_schema=vol.Schema({
                vol.Required("session_json"): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=10, max=600)
                ),
            }),
            errors=errors,
        )
