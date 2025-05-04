import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple, Type

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import ChargePointCommunicationException

from . import ChargePointChargerEntity, ChargePointEntityRequiredKeysMixin
from .const import (
    ACCT_HOME_CRGS,
    CHARGER_SESSION_STATE_IN_USE,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    EXCEPTION_WARNING_MSG,
)

_LOGGER = logging.getLogger(__name__)


class ChargePointChargerSwitchEntity(SwitchEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charger Device Switch."""

    entity_description: SwitchEntityDescription

    def __init__(self, hass, client, coordinator, description, charger_id):
        """Initialize account sensor."""
        super().__init__(client, coordinator, charger_id)
        self.hass = hass
        self.entity_description = description

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    def turn_on(self, **kwargs: Any) -> None:
        pass

    def turn_off(self, **kwargs: Any) -> None:
        pass


class ChargePointChargerChargingSessionSwitchEntity(ChargePointChargerSwitchEntity):
    """Specific entity for charging state toggle entity"""

    def __init__(self, hass, client, coordinator, description, charger_id):
        super().__init__(hass, client, coordinator, description, charger_id)
        self.last_toggled_on: Optional[datetime] = None

    @property
    def is_on(self) -> bool | None:
        if self.last_toggled_on is not None and (
            (self.last_toggled_on + timedelta(minutes=3)) > datetime.now()
        ):
            # The ChargePoint session API is eventually consistent.
            # Let's just assume we started a session for a bit.
            _LOGGER.warning(
                "Charging state switch state checked within three minutes of "
                "starting a new session, assuming charging."
            )
            return True
        if self.session:
            session_state = self.session.charging_state.upper()
            return session_state == CHARGER_SESSION_STATE_IN_USE
        return False

    async def async_turn_on(self) -> None:
        if not self.charger_status.plugged_in:
            self._attr_is_on = False
            raise HomeAssistantError("Cannot start session if charger not plugged in!")

        try:
            _LOGGER.info(
                "Starting new ChargePoint Session on Device ID: %s", self.charger_id
            )
            self.session = await self.hass.async_add_executor_job(
                self.client.start_charging_session, self.charger_id
            )
        except ChargePointCommunicationException:
            # This API is whack. We are just going to log an exception and still assume
            # the session started. Sometimes ChargePoint just lies and tells us there was an
            # error.
            # TODO: Maybe we should add some retry logic here just in case?
            _LOGGER.warning(EXCEPTION_WARNING_MSG)

        self.last_toggled_on = datetime.now()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        if not self.session:
            raise HomeAssistantError("Cannot stop a session that doesn't exist!")
        session_state = self.session.charging_state.upper()
        if session_state != CHARGER_SESSION_STATE_IN_USE:
            raise HomeAssistantError("You can't stop a session that hasn't started.")

        try:
            _LOGGER.info("Stopping ChargePoint Session: %s", self.session.session_id)
            await self.hass.async_add_executor_job(self.session.stop)
        except ChargePointCommunicationException:
            _LOGGER.warning(EXCEPTION_WARNING_MSG)

        self.session = None
        self.last_toggled_on = None
        await self.coordinator.async_request_refresh()


class ChargePointChargerSwitchEntityDescription(
    SwitchEntityDescription, ChargePointEntityRequiredKeysMixin
):
    """Switch entity description with required fields"""

    def __init__(self, **kwargs) -> None:
        self.name_suffix = kwargs.pop("name_suffix")
        super().__init__(**kwargs)


CHARGER_SWITCHES: List[
    Tuple[
        Type[ChargePointChargerSwitchEntity], ChargePointChargerSwitchEntityDescription
    ]
] = [
    (
        ChargePointChargerChargingSessionSwitchEntity,
        ChargePointChargerSwitchEntityDescription(
            key="charging_session",
            name_suffix="Charging Session",
            device_class=SwitchDeviceClass.SWITCH,
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

    entities: list[SwitchEntity] = []

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for switch_class, description in CHARGER_SWITCHES:
            entities.append(
                switch_class(hass, client, coordinator, description, charger_id)
            )

    async_add_entities(entities)
