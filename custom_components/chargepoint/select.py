import logging
from typing import List, Tuple, Type

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import ChargePointCommunicationException

from . import ChargePointChargerEntity, ChargePointEntityRequiredKeysMixin
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)
EXCEPTION_WARNING_MSG = (
    "ChargePoint returned an exception, you might want to "
    + "double check the amperage in the app."
)


class ChargePointChargerSelectEntity(SelectEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charger Device Select."""

    entity_description: SelectEntityDescription

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.hass = hass
        self.entity_description = description

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    async def async_select_option(self, option: str) -> None:
        pass


class ChargePointChargerChargeLimitSelectEntity(ChargePointChargerSelectEntity):
    """Specific entity for charge limit entity"""

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(hass, client, coordinator, description, charger_id)
        self._attr_options = [
            str(v) for v in self.charger_status.possible_amperage_limits
        ]
        self._attr_current_option = str(self.charger_status.amperage_limit)

    async def async_select_option(self, option: str) -> None:
        if not self.charger_status.plugged_in:
            self._attr_current_option = self.charger_status.amperage_limit
            raise HomeAssistantError("Cannot set amperage if charger not plugged in!")

        try:
            _LOGGER.warn(
                "Setting new ChargePoint amperage on Device ID: %s to %d",
                self.charger_id,
                int(option),
            )
            await self.hass.async_add_executor_job(
                self.client.set_amperage_limit,
                self.charger_id,
                int(option),
            )
            self._attr_current_option = option
        except ChargePointCommunicationException:
            _LOGGER.exception("Cannot set new amperage limit")
            raise HomeAssistantError("Cannot set new amperage limit!")

        await self.coordinator.async_request_refresh()


class ChargePointChargerSelectEntityDescription(
    SelectEntityDescription, ChargePointEntityRequiredKeysMixin
):
    """Select entity description with required fields"""

    def __init__(self, **kwargs) -> None:
        self.name_suffix = kwargs.pop("name_suffix")
        super().__init__(**kwargs)


CHARGER_SELECTS: List[
    Tuple[
        Type[ChargePointChargerSelectEntity], ChargePointChargerSelectEntityDescription
    ]
] = [
    (
        ChargePointChargerChargeLimitSelectEntity,
        ChargePointChargerSelectEntityDescription(
            key="charging_amperage_limit",
            name_suffix="Charging Amperage Limit",
            unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            icon="mdi:lightning-bolt",
        ),
    )
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the selects."""

    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[SelectEntity] = []

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for select_class, description in CHARGER_SELECTS:
            entities.append(
                select_class(hass, client, coordinator, description, charger_id)
            )

    async_add_entities(entities)
