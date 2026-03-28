"""Button platform for ChargePoint."""

import logging
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from python_chargepoint.exceptions import CommunicationError

from . import ChargePointChargerEntity
from .const import (
    ACCT_HOME_CRGS,
    CHARGER_SESSION_STATE_IN_USE,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    EXCEPTION_WARNING_MSG,
)

_LOGGER = logging.getLogger(__name__)

# After a start/stop action, poll at these intervals (seconds) to pick up the
# new charging state as soon as the API reflects it.
_CHARGING_FAST_POLL_DELAYS = (3, 8, 15, 30, 60)


def _schedule_charging_update(
    hass: HomeAssistant, coordinator: DataUpdateCoordinator
) -> None:
    """Schedule extra coordinator refreshes after a charging state change."""

    async def _refresh(_now: datetime) -> None:
        await coordinator.async_refresh()

    for delay in _CHARGING_FAST_POLL_DELAYS:
        async_call_later(hass, delay, _refresh)


@dataclass(frozen=True)
class ChargePointChargerButtonEntityDescription(ButtonEntityDescription):
    name_suffix: str = ""


class ChargePointChargerRestartChargerButton(ButtonEntity, ChargePointChargerEntity):
    """Button entity for restarting the home charger."""

    def __init__(self, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    async def async_press(self) -> None:
        try:
            await self.client.restart_home_charger(self.charger_id)
        except CommunicationError as exc:
            raise HomeAssistantError(
                f"Failed to restart charger {self.charger_id}: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()


class ChargePointChargerStartChargingButton(ButtonEntity, ChargePointChargerEntity):
    """Button entity for starting a charging session."""

    def __init__(self, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    async def async_press(self) -> None:
        if not self.charger_status.is_plugged_in:
            raise HomeAssistantError("Cannot start session if charger not plugged in!")
        try:
            _LOGGER.info(
                "Starting new ChargePoint session on Device ID: %s", self.charger_id
            )
            self.session = await self.client.start_charging_session(self.charger_id)
        except CommunicationError:
            # ChargePoint sometimes returns an error even when the session started.
            _LOGGER.warning(EXCEPTION_WARNING_MSG)
        await self.coordinator.async_request_refresh()
        _schedule_charging_update(self.hass, self.coordinator)


class ChargePointChargerStopChargingButton(ButtonEntity, ChargePointChargerEntity):
    """Button entity for stopping a charging session."""

    def __init__(self, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.session is not None
            and self.session.charging_state.upper() == CHARGER_SESSION_STATE_IN_USE
        )

    async def async_press(self) -> None:
        if not self.session:
            raise HomeAssistantError("Cannot stop a session that doesn't exist!")
        try:
            _LOGGER.info("Stopping ChargePoint session: %s", self.session.session_id)
            await self.session.stop()
        except CommunicationError:
            _LOGGER.warning(EXCEPTION_WARNING_MSG)
        self.session = None
        await self.coordinator.async_request_refresh()
        _schedule_charging_update(self.hass, self.coordinator)


_RESTART_DESCRIPTION = ChargePointChargerButtonEntityDescription(
    key="restart_charger",
    name_suffix="Restart Charger",
    device_class=ButtonDeviceClass.RESTART,
    icon="mdi:restart",
)
_START_CHARGING_DESCRIPTION = ChargePointChargerButtonEntityDescription(
    key="start_charging_session",
    name_suffix="Start Charging",
    icon="mdi:lightning-bolt",
)
_STOP_CHARGING_DESCRIPTION = ChargePointChargerButtonEntityDescription(
    key="stop_charging_session",
    name_suffix="Stop Charging",
    icon="mdi:stop",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities = []
    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        entities += [
            ChargePointChargerRestartChargerButton(
                client, coordinator, _RESTART_DESCRIPTION, charger_id
            ),
            ChargePointChargerStartChargingButton(
                client, coordinator, _START_CHARGING_DESCRIPTION, charger_id
            ),
            ChargePointChargerStopChargingButton(
                client, coordinator, _STOP_CHARGING_DESCRIPTION, charger_id
            ),
        ]

    async_add_entities(entities)
