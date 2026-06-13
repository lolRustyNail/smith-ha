"""Switch entities for Smith Water Heater integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmithDataUpdateCoordinator, SmithDeviceData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmithSwitchDescription:
    """Describe a Smith switch entity."""

    key: str
    name: str
    command_identifier: str
    input_data_on: dict[str, str]
    input_data_off: dict[str, str]
    status_key: str = "powerStatus"
    exists_fn: Callable[[dict[str, Any]], bool] | None = None


# Switch definitions based on captured Al-Link API traffic
CMD_SET_HEATER = "SetElectricWaterHeater"

SWITCH_DESCRIPTIONS: list[SmithSwitchDescription] = [
    SmithSwitchDescription(
        key="power",
        name="电源",
        command_identifier=CMD_SET_HEATER,
        input_data_on={"powerStatus": "1"},
        input_data_off={"powerStatus": "0"},
        status_key="powerStatus",
    ),
    SmithSwitchDescription(
        key="preheat",
        name="预热",
        command_identifier=CMD_SET_HEATER,
        input_data_on={"preheatStatus1": "1"},
        input_data_off={"preheatStatus1": "0"},
        status_key="preheatStatus1",
        exists_fn=lambda s: "preheatStatus1" in s,
    ),
    SmithSwitchDescription(
        key="instant_heating",
        name="即热模式",
        command_identifier=CMD_SET_HEATER,
        input_data_on={"instantHeating": "1"},
        input_data_off={"instantHeating": "0"},
        status_key="instantHeating",
        exists_fn=lambda s: "instantHeating" in s,
    ),
    SmithSwitchDescription(
        key="disinfection",
        name="杀菌",
        command_identifier=CMD_SET_HEATER,
        input_data_on={"disinfection": "1"},
        input_data_off={"disinfection": "0"},
        status_key="disinfection",
        exists_fn=lambda s: "disinfection" in s,
    ),
    SmithSwitchDescription(
        key="increase_capacity",
        name="增容",
        command_identifier=CMD_SET_HEATER,
        input_data_on={"increaseCapacity": "1"},
        input_data_off={"increaseCapacity": "0"},
        status_key="increaseCapacity",
        exists_fn=lambda s: "increaseCapacity" in s,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from a config entry."""
    coordinator: SmithDataUpdateCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    for device in coordinator.data.devices:
        for desc in SWITCH_DESCRIPTIONS:
            if desc.exists_fn and not desc.exists_fn(device.status):
                continue
            entities.append(SmithSwitch(coordinator, device, desc))

    async_add_entities(entities)


class SmithSwitch(CoordinatorEntity[SmithDataUpdateCoordinator], SwitchEntity):
    """Representation of a Smith switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmithDataUpdateCoordinator,
        device: SmithDeviceData,
        description: SmithSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device = device
        self._description = description
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}_{description.key}"
        self._attr_name = description.name
        self._optimistic_state: bool | None = None

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
    def is_on(self) -> bool | None:
        if self._optimistic_state is not None:
            return self._optimistic_state
        status = self._get_status()
        return str(status.get(self._description.status_key, "0")) == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._optimistic_state = True
        self.async_write_ha_state()
        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=self._description.command_identifier,
                input_data=self._description.input_data_on,
            )
        except Exception:
            self._optimistic_state = None
            raise
        finally:
            self._optimistic_state = None
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._optimistic_state = False
        self.async_write_ha_state()
        try:
            await self.coordinator.client.async_invoke_method(
                device_id=self._device.device_id,
                product_type=self._device.product_type,
                device_type=self._device.device_type,
                identifier=self._description.command_identifier,
                input_data=self._description.input_data_off,
            )
        except Exception:
            self._optimistic_state = None
            raise
        finally:
            self._optimistic_state = None
            await self.coordinator.async_request_refresh()
