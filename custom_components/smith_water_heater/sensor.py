"""Sensor entities for Smith Water Heater integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmithCoordinatorData, SmithDataUpdateCoordinator, SmithDeviceData

_LOGGER = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class SmithSensorDescription:
    """Describe a Smith sensor entity."""

    key: str
    name: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    unit: str | None = None
    value_fn: Callable[[dict[str, Any]], float | str | None] | None = None
    exists_fn: Callable[[dict[str, Any]], bool] | None = None


SENSOR_DESCRIPTIONS: list[SmithSensorDescription] = [
    SmithSensorDescription(
        key="realTemp",
        name="当前水温",
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: _safe_float(s.get("realTemp")),
    ),
    SmithSensorDescription(
        key="heatingTemp",
        name="目标温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: _safe_float(s.get("heatingTemp")),
    ),
    SmithSensorDescription(
        key="heatStatus",
        name="加热状态",
        state_class=None,
        value_fn=lambda s: "加热中" if str(s.get("heatStatus", "0")) == "1" else "待机",
        exists_fn=lambda s: "heatStatus" in s,
    ),
    SmithSensorDescription(
        key="workModel",
        name="工作模式",
        state_class=None,
        value_fn=lambda s: {
            "1": "标准", "2": "节能", "3": "速热"
        }.get(str(s.get("workModel", "")), str(s.get("workModel", ""))),
        exists_fn=lambda s: "workModel" in s,
    ),
    SmithSensorDescription(
        key="errorCode",
        name="故障代码",
        state_class=None,
        value_fn=lambda s: s.get("errorCode"),
        exists_fn=lambda s: "errorCode" in s,
    ),
    SmithSensorDescription(
        key="protectLevel",
        name="保护等级",
        state_class=None,
        value_fn=lambda s: s.get("protectLevel"),
        exists_fn=lambda s: "protectLevel" in s,
    ),
    SmithSensorDescription(
        key="preheatStatus1",
        name="预热状态",
        state_class=None,
        value_fn=lambda s: "开启" if str(s.get("preheatStatus1", "0")) == "1" else "关闭",
        exists_fn=lambda s: "preheatStatus1" in s,
    ),
    SmithSensorDescription(
        key="disinfection",
        name="杀菌状态",
        state_class=None,
        value_fn=lambda s: "开启" if str(s.get("disinfection", "0")) == "1" else "关闭",
        exists_fn=lambda s: "disinfection" in s,
    ),
    SmithSensorDescription(
        key="instantHeating",
        name="即热模式",
        state_class=None,
        value_fn=lambda s: "开启" if str(s.get("instantHeating", "0")) == "1" else "关闭",
        exists_fn=lambda s: "instantHeating" in s,
    ),
    SmithSensorDescription(
        key="increaseCapacity",
        name="增容模式",
        state_class=None,
        value_fn=lambda s: "开启" if str(s.get("increaseCapacity", "0")) == "1" else "关闭",
        exists_fn=lambda s: "increaseCapacity" in s,
    ),
    SmithSensorDescription(
        key="aes",
        name="AES模式",
        state_class=None,
        value_fn=lambda s: "开启" if str(s.get("aes", "0")) == "1" else "关闭",
        exists_fn=lambda s: "aes" in s,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: SmithDataUpdateCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for device in coordinator.data.devices:
        for desc in SENSOR_DESCRIPTIONS:
            # Check if sensor should exist for this device
            if desc.exists_fn and not desc.exists_fn(device.status):
                continue
            # Also check if the key is in status (for sensors without exists_fn)
            if desc.exists_fn is None and desc.key not in device.status:
                continue
            entities.append(SmithSensor(coordinator, device, desc))

    async_add_entities(entities)


class SmithSensor(CoordinatorEntity[SmithDataUpdateCoordinator], SensorEntity):
    """Representation of a Smith sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmithDataUpdateCoordinator,
        device: SmithDeviceData,
        description: SmithSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._description = description
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_native_unit_of_measurement = description.unit

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

    @property
    def native_value(self) -> float | str | None:
        status = self._get_status()
        if self._description.value_fn:
            return self._description.value_fn(status)
        return status.get(self._description.key)
