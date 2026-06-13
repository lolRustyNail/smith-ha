"""Water heater entity for Smith Water Heater integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmithCoordinatorData, SmithDataUpdateCoordinator, SmithDeviceData

_LOGGER = logging.getLogger(__name__)

# Status field mapping (from captured Al-Link API traffic)
FIELD_POWER_STATUS = "powerStatus"  # "1" = on, "0" = off
FIELD_TARGET_TEMP = "heatingTemp"  # target temperature (string, integer, range 40-65)
FIELD_CURRENT_TEMP = "realTemp"  # current water temperature
FIELD_WORK_MODEL = "workModel"  # operating mode (1/2/3)
FIELD_HEAT_STATUS = "heatStatus"  # active heating status
FIELD_ERROR_CODE = "errorCode"  # fault code

# Command identifier for this device type (productType=17, deviceType=EWH-HGAWi)
CMD_SET_HEATER = "SetElectricWaterHeater"

# Operation modes (workModel values)
OPERATION_MODES = {
    "0": "off",
    "1": "electric",  # standard heating mode
    "2": "eco",  # energy-saving mode
    "3": "performance",  # boost/rapid heating mode
}

STATE_OFF = "off"
STATE_ELECTRIC = "electric"
STATE_ECO = "eco"
STATE_PERFORMANCE = "performance"

OPERATION_LIST = [STATE_ECO, STATE_ELECTRIC, STATE_PERFORMANCE, STATE_OFF]


def _safe_float(value: Any) -> float | None:
    """Convert value to float safely."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up water heater entities from a config entry."""
    coordinator: SmithDataUpdateCoordinator = entry.runtime_data
    entities = []
    for device in coordinator.data.devices:
        entities.append(SmithWaterHeater(coordinator, device))
    async_add_entities(entities)


class SmithWaterHeater(CoordinatorEntity[SmithDataUpdateCoordinator], WaterHeaterEntity):
    """Representation of a Smith electric water heater."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_operation_list = OPERATION_LIST
    _attr_min_temp = 35.0
    _attr_max_temp = 75.0
    _attr_target_temperature_step = 1.0

    def __init__(
        self, coordinator: SmithDataUpdateCoordinator, device: SmithDeviceData
    ) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}"
        self._optimistic_target_temp: float | None = None
        self._optimistic_operation: str | None = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": self._device.room_name or self._device.product_name or "Smith Water Heater",
            "manufacturer": "A.O. Smith",
            "model": self._device.device_type,
        }

    def _get_status(self) -> dict[str, Any]:
        """Get current device status from coordinator."""
        for device in self.coordinator.data.devices:
            if device.device_id == self._device.device_id:
                return device.status
        return {}

    @property
    def current_temperature(self) -> float | None:
        """Return the current water temperature."""
        status = self._get_status()
        return _safe_float(status.get(FIELD_CURRENT_TEMP))

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._optimistic_target_temp is not None:
            # Clear optimistic value once coordinator confirms the change
            real = _safe_float(self._get_status().get(FIELD_TARGET_TEMP))
            if real is not None and int(real) == int(self._optimistic_target_temp):
                self._optimistic_target_temp = None
            else:
                return self._optimistic_target_temp
        status = self._get_status()
        return _safe_float(status.get(FIELD_TARGET_TEMP))

    @property
    def current_operation(self) -> str | None:
        """Return the current operation mode."""
        status = self._get_status()
        power = str(status.get(FIELD_POWER_STATUS, "0"))
        mode = str(status.get(FIELD_WORK_MODEL, "1"))
        real_op = STATE_OFF if power == "0" else OPERATION_MODES.get(mode, STATE_ELECTRIC)

        if self._optimistic_operation is not None:
            if real_op == self._optimistic_operation:
                self._optimistic_operation = None
            else:
                return self._optimistic_operation
        return real_op

    @property
    def is_on(self) -> bool:
        """Return if the device is on."""
        status = self._get_status()
        return str(status.get(FIELD_POWER_STATUS, "0")) == "1"

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temp = kwargs["temperature"]
        self._optimistic_target_temp = temp
        self.async_write_ha_state()

        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=CMD_SET_HEATER,
                input_data={"Temperature": str(int(temp))},
            )
        except Exception:
            self._optimistic_target_temp = None
            raise
        # Keep optimistic value until next poll confirms the change
        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode."""
        self._optimistic_operation = operation_mode
        self.async_write_ha_state()

        try:
            if operation_mode == STATE_OFF:
                await self.async_turn_off()
                return

            # Map operation mode to device mode value
            mode_map = {v: k for k, v in OPERATION_MODES.items()}
            mode_value = mode_map.get(operation_mode, "1")

            # Set power on + mode in one command
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=CMD_SET_HEATER,
                input_data={"powerStatus": "1", "workModel": mode_value},
            )
        except Exception:
            self._optimistic_operation = None
            raise
        # Keep optimistic value until next poll confirms the change
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the water heater on."""
        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=CMD_SET_HEATER,
                input_data={"powerStatus": "1"},
            )
        finally:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the water heater off."""
        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=CMD_SET_HEATER,
                input_data={"powerStatus": "0"},
            )
        finally:
            await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw status as extra attributes for debugging."""
        status = self._get_status()
        # Remove internal _profile key
        return {k: v for k, v in status.items() if not k.startswith("_")}
