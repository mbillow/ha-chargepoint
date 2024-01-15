import logging
from datetime import datetime
from typing import List, Tuple, Type

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)

from python_chargepoint.exceptions import ChargePointCommunicationException

from . import ChargePointChargerEntity, ChargePointEntityRequiredKeysMixin
from .const import (
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    ACCT_HOME_CRGS,
)

_LOGGER = logging.getLogger(__name__)
EXCEPTION_WARNING_MSG = "ChargePoint returned an exception, you might want to " + \
                        "double check the amperage in the app."

class ChargePointChargerNumberEntity(NumberEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charger Device Number."""

    entity_description: NumberEntityDescription

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.hass = hass
        self.entity_description = description

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    async def async_set_native_value(self, value: float) -> None:
        pass


class ChargePointChargerChargeLimitNumberEntity(ChargePointChargerNumberEntity):
    """Specific entity for charge limit entity"""

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(hass, client, coordinator, description, charger_id)
        self._min_value = min(self.charger_status.possible_amperage_limits)
        self._max_value = max(self.charger_status.possible_amperage_limits)
        self._value = self.charger_status.amperage_limit

    @property
    def mode(self) -> NumberMode:
        return NumberMode.AUTO
    
    @property
    def native_max_value(self) -> float:
        return self._max_value
    
    @property
    def native_min_value(self) -> float:
        return self._min_value
    
    @property
    def native_step(self) -> float:
        return 1
    
    @property
    def native_value(self) -> float:
        return self._value
    
    async def async_set_native_value(self, value: float) -> None:
        if not self.charger_status.plugged_in:
            self._attr_value = self.charger_status.amperage_limit
            raise HomeAssistantError("Cannot set amperage if charger not plugged in!")

        limit = int(value)
        try:
            _LOGGER.warn(
                "Setting new ChargePoint amperage on Device ID: %s to %d", self.charger_id, limit
            )
            self._attr_available = False
            await self.hass.async_add_executor_job(
                self.client.set_amperage_limit, self.charger_id, limit,
            )
            self._attr_available = True
            self._value = limit
        except ChargePointCommunicationException:
            _LOGGER.exception("Cannot set new amperage limit")
            raise HomeAssistantError("Cannot set new amperage limit!")

        await self.coordinator.async_request_refresh()


class ChargePointChargerNumberEntityDescription(
    NumberEntityDescription, ChargePointEntityRequiredKeysMixin
):
    """Number entity description with required fields"""

    def __init__(self, **kwargs) -> None:
        self.name_suffix = kwargs.pop("name_suffix")
        super().__init__(**kwargs)


CHARGER_NUMBERS: List[
    Tuple[
        Type[ChargePointChargerNumberEntity], ChargePointChargerNumberEntityDescription
    ]
] = [
    (
        ChargePointChargerChargeLimitNumberEntity,
        ChargePointChargerNumberEntityDescription(
            key="charging_amperage_limit",
            name_suffix="Charging Amperage Limit",
            device_class=NumberDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            icon="mdi:lightning-bolt",
        ),
    )
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the numbers."""

    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[NumberEntity] = []

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for number_class, description in CHARGER_NUMBERS:
            entities.append(
                number_class(hass, client, coordinator, description, charger_id)
            )

    async_add_entities(entities)
