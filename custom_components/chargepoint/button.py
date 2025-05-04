import logging
from datetime import datetime
from typing import Any, List, Optional, Tuple, Type

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import ChargePointCommunicationException

from . import ChargePointChargerEntity, ChargePointEntityRequiredKeysMixin
from .const import (
    ACCT_HOME_CRGS,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    EXCEPTION_WARNING_MSG,
)

_LOGGER = logging.getLogger(__name__)


class ChargePointChargerButtonEntity(ButtonEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charger Device Button."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        client: Any,
        coordinator: Any,
        description: ButtonEntityDescription,
        charger_id: str,
    ) -> None:
        """Initialize account sensor."""
        super().__init__(client, coordinator, charger_id)
        self.hass: HomeAssistant = hass
        self.entity_description: ButtonEntityDescription = description
        self.last_toggled_on: Optional[datetime] = None

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    async def _async_press(self) -> None:
        pass

    async def async_press(self) -> None:
        """Press the button."""
        await self.on_press()
        self.last_toggled_on = datetime.now()
        await self.coordinator.async_request_refresh()


class ChargePointChargerRestartChargerButton(ChargePointChargerButtonEntity):
    """Specific entity for restarting the charger"""

    async def _async_press(self) -> None:
        try:
            self.session = await self.hass.async_add_executor_job(
                self.client.restart_home_charger, self.charger_id
            )
        except ChargePointCommunicationException:
            _LOGGER.exception(EXCEPTION_WARNING_MSG)


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
            icon="mdi:restart",
        ),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons."""

    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[ButtonEntity] = []

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for button_class, description in CHARGER_BUTTONS:
            entities.append(
                button_class(hass, client, coordinator, description, charger_id)
            )

    async_add_entities(entities)
