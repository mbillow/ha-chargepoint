import logging
from datetime import datetime, timedelta
from typing import Any, List, Tuple, Type, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription
)

from python_chargepoint.exceptions import ChargePointCommunicationException

from . import ChargePointChargerEntity, ChargePointEntityRequiredKeysMixin
from .const import (
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    ACCT_HOME_CRGS
)

_LOGGER = logging.getLogger(__name__)
EXCEPTION_WARNING_MSG = "ChargePoint returned an exception, you might want to " + \
                        "double check the charging status in the app."

class ChargePointChargerButtonEntity(ButtonEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charger Device Button."""

    entity_description: ButtonEntityDescription

    def __init__(self, hass, client, coordinator, description, charger_id):
        """Initialize account sensor."""
        super().__init__(client, coordinator, charger_id)
        self.hass = hass
        self.entity_description = description

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    def press(self) -> None:
        """Press the button."""
        pass


class ChargePointChargerRestartChargerButton(ChargePointChargerButtonEntity):
    """Specific entity for restarting the charger"""

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(hass, client, coordinator, description, charger_id)
        self.last_toggled_on: Optional[datetime] = None

    async def async_press(self) -> None:

        try:
            _LOGGER.info(
                "Restarting ChargePoint Device ID: %s", self.charger_id
            )
            self.session = await self.hass.async_add_executor_job(
                self.client.restart_home_charger, self.charger_id
            )
        except ChargePointCommunicationException:
            _LOGGER.warning(EXCEPTION_WARNING_MSG)

        self.last_toggled_on = datetime.now()
        await self.coordinator.async_request_refresh()


class ChargePointChargerButtonEntityDescription(
    ButtonEntityDescription, ChargePointEntityRequiredKeysMixin
):
    """Button entity description with required fields"""

    def __init__(self, **kwargs) -> None:
        self.name_suffix = kwargs.pop("name_suffix")
        super().__init__(**kwargs)


CHARGER_BUTTONS: List[
    Tuple[
        Type[ChargePointChargerButtonEntity], ChargePointChargerButtonEntityDescription
    ]
] = [
    (
        ChargePointChargerRestartChargerButton,
        ChargePointChargerButtonEntityDescription(
            key="restart_charger",
            name_suffix="Restart Charger",
            device_class=ButtonDeviceClass.RESTART,
            icon="mdi:lightning-bolt",
        ),
    )
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""

    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[ButtonEntity] = []

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for button_class, description in CHARGER_BUTTONS:
            entities.append(
                button_class(hass, client, coordinator, description, charger_id)
            )

    async_add_entities(entities)
