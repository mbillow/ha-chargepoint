"""Switch platform for ChargePoint."""

from typing import Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import CommunicationError
from python_chargepoint.types import ChargeSchedule

from . import ChargePointChargerEntity
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN


class ChargePointScheduleSwitch(SwitchEntity, ChargePointChargerEntity):
    """Switch to enable or disable the home charger's charging schedule."""

    _attr_icon = "mdi:timer-outline"

    def __init__(self, client, coordinator, charger_id):
        super().__init__(client, coordinator, charger_id)
        self._attr_name = f"{self.short_charger_model} Charging Schedule"
        self._attr_unique_id = f"{self.account.user.user_id}_{charger_id}_charging_schedule"

    @property
    def available(self) -> bool:
        return super().available and self.charger_schedule is not None

    @property
    def is_on(self) -> bool:
        schedule = self.charger_schedule
        return schedule.schedule_enabled if schedule else False

    def _active_schedule(self) -> Optional[ChargeSchedule]:
        schedule = self.charger_schedule
        if not schedule:
            return None
        return schedule.user_schedule or schedule.default_schedule

    async def async_turn_on(self, **kwargs) -> None:
        src = self._active_schedule()
        if not src:
            raise HomeAssistantError("No schedule times configured")
        try:
            await self.client.set_home_charger_schedule(
                self.charger_id,
                src.weekdays.start_time,
                src.weekdays.end_time,
                src.weekends.start_time,
                src.weekends.end_time,
            )
        except CommunicationError as exc:
            raise HomeAssistantError(f"Failed to enable schedule: {exc}") from exc
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.client.disable_home_charger_schedule(self.charger_id)
        except CommunicationError as exc:
            raise HomeAssistantError(f"Failed to disable schedule: {exc}") from exc
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        [
            ChargePointScheduleSwitch(client, coordinator, charger_id)
            for charger_id in coordinator.data[ACCT_HOME_CRGS].keys()
        ]
    )
