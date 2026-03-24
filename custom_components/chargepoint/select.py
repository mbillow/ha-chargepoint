"""Select platform for ChargePoint."""

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import CommunicationError

from . import ChargePointChargerEntity
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

_EXCEPTION_MSG = (
    "ChargePoint returned an exception, you might want to "
    "double check the amperage in the app."
)


@dataclass(frozen=True)
class ChargePointChargerSelectEntityDescription(SelectEntityDescription):
    name_suffix: str = ""


_AMPERAGE_LIMIT_DESCRIPTION = ChargePointChargerSelectEntityDescription(
    key="charging_amperage_limit",
    name_suffix="Charging Amperage Limit",
    unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    icon="mdi:lightning-bolt",
)


class ChargePointChargerChargeLimitSelectEntity(SelectEntity, ChargePointChargerEntity):
    """Select entity for controlling the charging amperage limit."""

    def __init__(self, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"
        self._attr_options = [
            str(v) for v in self.charger_status.possible_amperage_limits
        ]
        self._attr_current_option = str(self.charger_status.amperage_limit)

    async def async_select_option(self, option: str) -> None:
        try:
            _LOGGER.warning(
                "Setting new ChargePoint amperage on Device ID: %s to %d",
                self.charger_id,
                int(option),
            )
            await self.client.set_amperage_limit(self.charger_id, int(option))
            self._attr_current_option = option
        except CommunicationError:
            _LOGGER.exception(_EXCEPTION_MSG)
            raise HomeAssistantError("Cannot set new amperage limit!")

        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        [
            ChargePointChargerChargeLimitSelectEntity(
                client, coordinator, _AMPERAGE_LIMIT_DESCRIPTION, charger_id
            )
            for charger_id in coordinator.data[ACCT_HOME_CRGS].keys()
        ]
    )
