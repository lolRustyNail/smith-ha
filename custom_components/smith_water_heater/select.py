"""Select entities for Smith Water Heater integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmithDataUpdateCoordinator, SmithDeviceData

_LOGGER = logging.getLogger(__name__)

CMD_SET_HEATER = "SetElectricWaterHeater"

# CircleTimer bitmask: each bit = one 4-hour slot
# bit0=0:00, bit1=4:00, bit2=8:00, bit3=12:00, bit4=16:00, bit5=20:00
def _build_schedule_options() -> dict[str, str]:
    """Build all possible schedule combinations as name -> hex mapping."""
    hours = [0, 4, 8, 12, 16, 20]
    opts = {"关闭": "00,00"}
    for mask in range(1, 64):
        bits = []
        for i in range(6):
            if mask & (1 << i):
                bits.append(str(hours[i]))
        name = ",".join(bits)
        hex_val = f"{mask:02X},00"
        opts[name] = hex_val
    return opts


SCHEDULE_OPTIONS = _build_schedule_options()

# Reverse mapping: hex value -> display name
_HEX_TO_NAME = {v: k for k, v in SCHEDULE_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    coordinator: SmithDataUpdateCoordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    for device in coordinator.data.devices:
        entities.append(SmithScheduleSelect(coordinator, device))
    async_add_entities(entities)


class SmithScheduleSelect(CoordinatorEntity[SmithDataUpdateCoordinator], SelectEntity):
    """Select entity for scheduled heating (CircleTimer)."""

    _attr_has_entity_name = True
    _attr_name = "预约加热"
    _attr_options = list(SCHEDULE_OPTIONS.keys())
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self, coordinator: SmithDataUpdateCoordinator, device: SmithDeviceData
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}_schedule"
        self._optimistic_value: str | None = None

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": self._device.room_name or self._device.product_name or "Smith Water Heater",
            "manufacturer": "A.O. Smith",
            "model": self._device.device_type,
        }

    def _get_status(self) -> dict[str, Any]:
        for device in self.coordinator.data.devices:
            if device.device_id == self._device.device_id:
                return device.status
        return {}

    def _get_current_hex(self) -> str:
        """Get current CircleTimer hex value from status."""
        status = self._get_status()
        # CircleTimer might be in timingData or as a direct field
        circle_timer = status.get("CirlceTimer", "")
        if circle_timer:
            return circle_timer.upper()
        # Try parsing from timingData
        timing_data = status.get("timingData", "")
        if isinstance(timing_data, dict):
            timers = timing_data.get("deviceTimer", [])
            if timers and timers[0]:
                # deviceTimer is [[hex1, hex2, hex3], ...]
                t = timers[0]
                if len(t) >= 1:
                    return f"{t[0]:02X},{t[1]:02X}" if len(t) >= 2 else f"{t[0]:02X},00"
        return "00,00"

    @property
    def current_option(self) -> str | None:
        if self._optimistic_value is not None:
            real = self._get_current_hex()
            if real.upper() == self._optimistic_value.upper():
                self._optimistic_value = None
            else:
                return _HEX_TO_NAME.get(self._optimistic_value, self._optimistic_value)
        hex_val = self._get_current_hex()
        return _HEX_TO_NAME.get(hex_val, hex_val)

    async def async_select_option(self, option: str) -> None:
        """Select a scheduled heating option."""
        hex_value = SCHEDULE_OPTIONS.get(option)
        if hex_value is None:
            return

        self._optimistic_value = hex_value
        self.async_write_ha_state()

        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=CMD_SET_HEATER,
                input_data={"CirlceTimer": hex_value},
            )
        except Exception:
            self._optimistic_value = None
            raise
        await self.coordinator.async_request_refresh()
