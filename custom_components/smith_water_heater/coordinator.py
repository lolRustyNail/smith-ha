"""DataUpdateCoordinator for Smith Water Heater."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmithApiClient, SmithApiAuthError, SmithApiConnectionError, parse_device_status
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class SmithDeviceData:
    """Data for a single device."""

    device_id: str
    product_type: str
    device_type: str
    product_name: str
    room_name: str
    status: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmithCoordinatorData:
    """Data returned by the coordinator."""

    devices: list[SmithDeviceData] = field(default_factory=list)


class SmithDataUpdateCoordinator(DataUpdateCoordinator[SmithCoordinatorData]):
    """Coordinator to manage fetching data from the Smith API."""

    def __init__(
        self, hass: HomeAssistant, client: SmithApiClient, scan_interval: int = DEFAULT_SCAN_INTERVAL
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> SmithCoordinatorData:
        """Fetch data from the API."""
        try:
            homepage = await self.client.async_get_homepage()
        except SmithApiAuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except SmithApiConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        info = homepage.get("info", {})
        raw_devices = info.get("devInfoItemInfoList", [])

        devices: list[SmithDeviceData] = []
        for raw in raw_devices:
            status_raw = raw.get("statusInfo", "")
            status = parse_device_status(status_raw)
            profile = status.get("_profile", {})

            device = SmithDeviceData(
                device_id=raw.get("deviceId", ""),
                product_type=raw.get("productType", profile.get("productType", "")),
                device_type=raw.get("deviceType", profile.get("deviceType", "")),
                product_name=raw.get("productName", ""),
                room_name=raw.get("roomName", ""),
                status=status,
            )
            devices.append(device)

        return SmithCoordinatorData(devices=devices)
