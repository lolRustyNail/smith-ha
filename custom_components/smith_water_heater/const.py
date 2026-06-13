"""Constants for the Smith Water Heater integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "smith_water_heater"
PLATFORMS: list[Platform] = [Platform.WATER_HEATER, Platform.SENSOR, Platform.SWITCH, Platform.SELECT]

# API
BASE_URL = "https://ailink-api.hotwater.com.cn/AiLinkService"
API_GET_HOMEPAGE = "appDevice/getHomepageV2"
API_INVOKE_METHOD = "device/invokeMethod"
API_REFRESH_TOKEN = "api/getLastToken"

# Polling
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# Anti-replay crypto keys
SECRET_KEY = "ng957stzh4zy3dts"
ENCODE_KEY = "AILink_2021#"

# Config
CONF_AUTH_TOKEN = "auth_token"
CONF_USER_ID = "user_id"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_UK = "family_uk"
CONF_MOBILE = "mobile"
CONF_SCAN_INTERVAL = "scan_interval"

# Session JSON keys (flexible matching)
SESSION_KEYS = {
    "auth_token": ["auth_token", "token", "authToken"],
    "user_id": ["user_id", "userId"],
    "family_id": ["family_id", "familyId"],
    "family_uk": ["family_uk", "familyUk"],
}
