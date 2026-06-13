"""API client for A.O. Smith AI-LiNK water heaters."""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import md5
from typing import Any

import aiohttp

from .const import (
    API_GET_HOMEPAGE,
    API_GET_INFO,
    API_GET_USER_ID,
    API_INVOKE_METHOD,
    API_LOGIN,
    API_REFRESH_TOKEN,
    API_SEND_SMS,
    BASE_URL,
    ENCODE_KEY,
    SECRET_KEY,
)

_LOGGER = logging.getLogger(__name__)

ANDROID_TAG = "01"


@dataclass
class SmithSessionData:
    """Session data captured from the Al-Link app."""

    auth_token: str
    user_id: str
    family_id: str
    family_uk: str
    mobile: str = ""


class SmithApiError(Exception):
    """Base exception for API errors."""


class SmithApiAuthError(SmithApiError):
    """Authentication error."""


class SmithApiConnectionError(SmithApiError):
    """Connection error."""


def _md5(data: str) -> str:
    return md5(data.encode("utf-8")).hexdigest()


def _compute_encode(params: dict[str, Any]) -> str:
    """Compute the encode field: MD5 of sorted param values + ENCODE_KEY."""
    concat = "".join(str(params[key]) for key in sorted(params.keys()))
    return _md5(concat + ENCODE_KEY)


def _compute_anti_replay(params: dict[str, Any]) -> dict[str, str]:
    """Compute anti-replay headers: timestamp, nonce, md5data, sign."""
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4()).upper()

    if params:
        # Reverse insertion order concatenation
        concat = ""
        for key in params.keys():
            concat = str(params[key]) + concat
        md5data = _md5(concat)
    else:
        md5data = _md5(timestamp)

    sign = _md5(md5data + timestamp + nonce + SECRET_KEY)
    return {
        "timestamp": timestamp,
        "nonce": nonce,
        "md5data": md5data,
        "sign": sign,
    }


def _decode_jwt_exp(token: str) -> int | None:
    """Decode JWT exp claim without verification."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # Pad base64
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("exp")
    except Exception:
        return None


def parse_device_status(status_info_raw: str) -> dict[str, Any]:
    """Parse the statusInfo JSON string from device list response.

    The statusInfo field contains events[].outputData dicts that get
    flattened into a single dict per device.
    """
    try:
        status_info = json.loads(status_info_raw)
    except (json.JSONDecodeError, TypeError):
        return {}

    result: dict[str, Any] = {}
    for event in status_info.get("events", []):
        od = event.get("outputData")
        if isinstance(od, dict):
            result.update(od)
        elif isinstance(od, list):
            for item in od:
                if isinstance(item, dict):
                    result.update(item)

    profile = status_info.get("profile", {})
    if profile:
        result["_profile"] = profile

    return result


class SmithApiClient:
    """API client for A.O. Smith AI-LiNK."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        session_data: SmithSessionData,
    ) -> None:
        self._session = session
        self._session_data = session_data

    @property
    def session_data(self) -> SmithSessionData:
        return self._session_data

    def _build_headers(self, source: str = "Android") -> dict[str, str]:
        """Build common request headers."""
        millis = str(int(time.time() * 1000))
        rand4 = str(uuid.uuid4().int % 100000).zfill(5)
        trace_id = f"{millis}-{rand4}-{self._session_data.user_id}-{ANDROID_TAG}"

        headers = {
            "traceId": trace_id,
            "Authorization": self._session_data.auth_token,
            "Content-Type": "application/json;charset=UTF-8",
            "userId": self._session_data.user_id,
            "familyId": self._session_data.family_id,
            "version": "V1.0.1",
            "source": source,
            "familyUk": self._session_data.family_uk or "",
        }

        # Add anti-replay headers
        anti_replay = _compute_anti_replay({})
        headers.update(anti_replay)

        return headers

    async def _upstream_request(
        self, endpoint: str, body_json: dict[str, Any], source: str = "Android"
    ) -> tuple[dict[str, Any], int]:
        """Make a raw upstream request. Returns (response_data, status_code)."""
        url = f"{BASE_URL}/{endpoint}"
        headers = self._build_headers(source=source)

        # Add encode field and sort body
        relay_body = dict(body_json)
        relay_body["encode"] = _compute_encode(body_json)
        relay_body = dict(sorted(relay_body.items()))

        try:
            async with self._session.post(
                url, json=relay_body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                # Capture new token from response headers if present
                auth_header = resp.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    self._session_data.auth_token = auth_header

                data = await resp.json()
                return data, resp.status
        except aiohttp.ClientError as err:
            raise SmithApiConnectionError(f"Connection error: {err}") from err
        except TimeoutError as err:
            raise SmithApiConnectionError(f"Timeout: {err}") from err

    async def _ensure_fresh_token(self) -> None:
        """Proactively refresh token if it expires within 90 seconds."""
        # Strip "Bearer " prefix if present for JWT decoding
        token = self._session_data.auth_token
        if token.startswith("Bearer "):
            token = token[7:]

        exp = _decode_jwt_exp(token)
        if not exp:
            return

        now = int(datetime.now(tz=timezone.utc).timestamp())
        if exp - now > 90:
            return

        _LOGGER.debug("Token expiring soon (%ds), refreshing", exp - now)
        await self._refresh_token()

    async def _refresh_token(self) -> None:
        """Refresh the JWT token via getLastToken endpoint."""
        body_json = {"token": self._session_data.auth_token}
        try:
            data, status = await self._upstream_request(API_REFRESH_TOKEN, body_json)
            if status != 200:
                _LOGGER.warning("Token refresh failed with status %d", status)
                return
            token = (data.get("info") or {}).get("token")
            if isinstance(token, str) and token:
                if not token.startswith("Bearer "):
                    token = f"Bearer {token}"
                self._session_data.auth_token = token
                _LOGGER.debug("Token refreshed successfully")
        except SmithApiConnectionError as err:
            _LOGGER.warning("Token refresh connection error: %s", err)

    async def _call_api(
        self, endpoint: str, body_json: dict[str, Any], source: str = "Android"
    ) -> dict[str, Any]:
        """Call an API endpoint with token refresh and retry logic."""
        await self._ensure_fresh_token()

        data, status = await self._upstream_request(endpoint, body_json, source)

        # Retry on auth failure
        if status in (401, 403):
            _LOGGER.debug("Got %d, refreshing token and retrying", status)
            await self._refresh_token()
            data, status = await self._upstream_request(endpoint, body_json, source)

        if status in (401, 403):
            raise SmithApiAuthError("Authentication failed after token refresh")

        if status != 200:
            raise SmithApiError(f"API error: status={status}, data={data}")

        if data.get("status") != 200:
            raise SmithApiError(f"API returned error: {data}")

        return data

    async def async_validate(self) -> dict[str, Any]:
        """Validate the connection by fetching homepage data."""
        return await self.async_get_homepage()

    async def async_get_homepage(self) -> dict[str, Any]:
        """Get device list and status from getHomepageV2."""
        body = {
            "homePageVersion": "3",
            "userId": self._session_data.user_id,
            "familyId": self._session_data.family_id,
        }
        return await self._call_api(API_GET_HOMEPAGE, body)

    async def async_invoke_method(
        self,
        device_id: str,
        product_type: str,
        device_type: str,
        identifier: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a command to a device via invokeMethod."""
        payload = {
            "profile": {
                "deviceId": device_id,
                "productType": product_type,
                "deviceType": device_type,
            },
            "service": {
                "identifier": identifier,
                "inputData": input_data,
            },
        }

        body = {
            "userId": self._session_data.user_id,
            "familyId": self._session_data.family_id,
            "appSource": 2,
            "commandSource": 1,
            "invokeTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "payLoad": json.dumps(payload),
        }

        return await self._call_api(API_INVOKE_METHOD, body, source="Web")

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Get parsed device list with status info."""
        homepage = await self.async_get_homepage()
        info = homepage.get("info", {})
        devices = info.get("devInfoItemInfoList", [])

        result = []
        for device in devices:
            status_raw = device.get("statusInfo", "")
            status = parse_device_status(status_raw)
            device["_parsed_status"] = status
            result.append(device)

        return result

    # --- Login methods (unauthenticated) ---

    def _build_headers_login(self) -> dict[str, str]:
        """Build headers for unauthenticated login requests."""
        millis = str(int(time.time() * 1000))
        rand4 = str(uuid.uuid4().int % 100000).zfill(5)
        trace_id = f"{millis}-{rand4}--{ANDROID_TAG}"

        headers = {
            "traceId": trace_id,
            "Authorization": "",
            "Content-Type": "application/json;charset=UTF-8",
            "userId": "",
            "familyId": "",
            "version": "V1.0.1",
            "source": "Android",
            "familyUk": "",
        }
        anti_replay = _compute_anti_replay({})
        headers.update(anti_replay)
        return headers

    async def _login_request(
        self, endpoint: str, body_json: dict[str, Any], with_auth: bool = False
    ) -> tuple[dict[str, Any], int]:
        """Make a login-phase request. If with_auth, include Authorization header."""
        url = f"{BASE_URL}/{endpoint}"
        headers = self._build_headers_login()
        if with_auth:
            headers["Authorization"] = self._session_data.auth_token
            headers["userId"] = self._session_data.user_id

        relay_body = dict(body_json)
        relay_body["encode"] = _compute_encode(body_json)
        relay_body = dict(sorted(relay_body.items()))

        try:
            async with self._session.post(
                url, json=relay_body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                # Capture token from response if present
                auth_header = resp.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    self._session_data.auth_token = auth_header

                data = await resp.json()
                return data, resp.status
        except aiohttp.ClientError as err:
            raise SmithApiConnectionError(f"Connection error: {err}") from err
        except TimeoutError as err:
            raise SmithApiConnectionError(f"Timeout: {err}") from err

    async def async_send_sms(
        self, mobile: str, ticket: str = "", randstr: str = ""
    ) -> bool:
        """Send SMS verification code. Returns True on success."""
        body = {
            "mobile": mobile,
            "ticket": ticket,
            "randstr": randstr,
            "type": "1",
        }
        data, status = await self._login_request(API_SEND_SMS, body)
        if status != 200:
            raise SmithApiConnectionError(f"SMS request failed: status={status}")
        # Server returns {} on success, or error info on failure
        if data.get("status") and data["status"] != 200:
            raise SmithApiError(f"SMS error: {data.get('info', data)}")
        return True

    async def async_login(self, mobile: str, captcha: str) -> str:
        """Login with phone + SMS code. Returns the JWT token."""
        body = {
            "adCode": "",
            "address": "",
            "captcha": captcha,
            "city": "",
            "country": "",
            "district": "",
            "latitude": "",
            "longitude": "",
            "mobile": mobile,
            "province": "",
            "street": "",
            "streetNum": "",
        }
        data, status = await self._login_request(API_LOGIN, body)
        if status != 200:
            raise SmithApiConnectionError(f"Login failed: status={status}")
        if data.get("status") != 200:
            raise SmithApiAuthError(f"Login error: {data.get('info', data)}")

        token = self._session_data.auth_token
        if not token:
            raise SmithApiAuthError("No token received from login response")

        # Extract userId from JWT payload for subsequent requests
        raw_token = token[7:] if token.startswith("Bearer ") else token
        parts = raw_token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            self._session_data.user_id = payload.get("username", "")
            self._session_data.mobile = mobile

        return token

    async def async_get_user_id(self, mobile: str) -> str:
        """Get userId from phone number. Must be called after login."""
        body = {"mobile": mobile}
        data, status = await self._login_request(API_GET_USER_ID, body, with_auth=True)
        if status != 200:
            raise SmithApiConnectionError(f"getUserId failed: status={status}")
        if data.get("status") != 200:
            raise SmithApiError(f"getUserId error: {data}")

        user_id = data.get("info", {}).get("userId", "")
        if not user_id:
            # Fallback: extract from JWT token
            token = self._session_data.auth_token
            if token.startswith("Bearer "):
                token = token[7:]
            payload_b64 = token.split(".")[1] if "." in token else ""
            if payload_b64:
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += "=" * padding
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                user_id = payload.get("username", "")
        return user_id

    async def async_get_family_info(self, user_id: str) -> tuple[str, str]:
        """Get familyId and familyUk from userId. Returns (family_id, family_uk)."""
        body = {"userId": user_id}
        data, status = await self._login_request(API_GET_INFO, body, with_auth=True)
        if status != 200:
            raise SmithApiConnectionError(f"getInfo failed: status={status}")
        if data.get("status") != 200:
            raise SmithApiError(f"getInfo error: {data}")

        info = data.get("info", {})
        family_id = info.get("familyId", "")
        family_uk = info.get("familyUk", "")
        if not family_id:
            raise SmithApiError("No familyId in getInfo response")
        return family_id, family_uk


def parse_session_payload(raw: str) -> SmithSessionData | None:
    """Parse session JSON from user input.

    Supports flat JSON with keys like auth_token/user_id/family_id/family_uk,
    or nested JSON where it searches for a dict containing all required keys.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    from .const import SESSION_KEYS

    def _find_value(obj: dict, key_variants: list[str]) -> str | None:
        for key in key_variants:
            if key in obj:
                val = obj[key]
                if isinstance(val, str) and val:
                    return val
        return None

    # Try flat structure first
    auth_token = _find_value(data, SESSION_KEYS["auth_token"])
    user_id = _find_value(data, SESSION_KEYS["user_id"])
    family_id = _find_value(data, SESSION_KEYS["family_id"])
    family_uk = _find_value(data, SESSION_KEYS["family_uk"])

    if auth_token and user_id and family_id:
        return SmithSessionData(
            auth_token=auth_token,
            user_id=user_id,
            family_id=family_id,
            family_uk=family_uk or "",
            mobile=_find_value(data, ["mobile", "phone"]) or "",
        )

    # Try nested structure — search values for a dict with all keys
    for value in data.values():
        if isinstance(value, dict):
            auth_token = _find_value(value, SESSION_KEYS["auth_token"])
            user_id = _find_value(value, SESSION_KEYS["user_id"])
            family_id = _find_value(value, SESSION_KEYS["family_id"])
            family_uk = _find_value(value, SESSION_KEYS["family_uk"])

            if auth_token and user_id and family_id:
                return SmithSessionData(
                    auth_token=auth_token,
                    user_id=user_id,
                    family_id=family_id,
                    family_uk=family_uk or "",
                    mobile=_find_value(value, ["mobile", "phone"]) or "",
                )

    return None
