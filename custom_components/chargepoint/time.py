"""Time platform for ChargePoint."""

from dataclasses import dataclass
from datetime import time
from typing import Optional

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import CommunicationError
from python_chargepoint.types import ChargeSchedule

from . import ChargePointChargerEntity
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN


@dataclass(frozen=True)
class ChargePointScheduleTimeDescription(TimeEntityDescription):
    name_suffix: str = ""
    is_weekday: bool = True
    is_start: bool = True


SCHEDULE_TIME_DESCRIPTIONS = [
    ChargePointScheduleTimeDescription(
        key="weekday_schedule_start",
        name_suffix="Weekday Schedule Start",
        icon="mdi:timer-play-outline",
        is_weekday=True,
        is_start=True,
    ),
    ChargePointScheduleTimeDescription(
        key="weekday_schedule_end",
        name_suffix="Weekday Schedule End",
        icon="mdi:timer-stop-outline",
        is_weekday=True,
        is_start=False,
    ),
    ChargePointScheduleTimeDescription(
        key="weekend_schedule_start",
        name_suffix="Weekend Schedule Start",
        icon="mdi:timer-play-outline",
        is_weekday=False,
        is_start=True,
    ),
    ChargePointScheduleTimeDescription(
        key="weekend_schedule_end",
        name_suffix="Weekend Schedule End",
        icon="mdi:timer-stop-outline",
        is_weekday=False,
        is_start=False,
    ),
]


class ChargePointScheduleTimeEntity(TimeEntity, ChargePointChargerEntity):
    """Time entity for one slot of the home charger's charging schedule."""

    entity_description: ChargePointScheduleTimeDescription

    def __init__(self, client, coordinator, charger_id, description):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{self.account.user.user_id}_{charger_id}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and self._active_schedule() is not None

    def _active_schedule(self) -> Optional[ChargeSchedule]:
        schedule = self.charger_schedule
        if not schedule:
            return None
        return schedule.user_schedule or schedule.default_schedule

    @property
    def native_value(self) -> Optional[time]:
        src = self._active_schedule()
        if not src:
            return None
        window = src.weekdays if self.entity_description.is_weekday else src.weekends
        time_str = (
            window.start_time if self.entity_description.is_start else window.end_time
        )
        if not time_str:
            return None
        h, m = time_str.split(":")
        return time(int(h), int(m))

    async def async_set_value(self, value: time) -> None:
        src = self._active_schedule()
        if not src:
            raise HomeAssistantError("No schedule data available")
        wd_start = src.weekdays.start_time
        wd_end = src.weekdays.end_time
        we_start = src.weekends.start_time
        we_end = src.weekends.end_time
        time_str = value.strftime("%H:%M")
        desc = self.entity_description
        if desc.is_weekday and desc.is_start:
            wd_start = time_str
        elif desc.is_weekday and not desc.is_start:
            wd_end = time_str
        elif not desc.is_weekday and desc.is_start:
            we_start = time_str
        else:
            we_end = time_str
        try:
            await self.client.set_home_charger_schedule(
                self.charger_id, wd_start, wd_end, we_start, we_end
            )
        except CommunicationError as exc:
            raise HomeAssistantError(f"Failed to set schedule time: {exc}") from exc
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the time platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        [
            ChargePointScheduleTimeEntity(client, coordinator, charger_id, description)
            for charger_id in coordinator.data[ACCT_HOME_CRGS].keys()
            for description in SCHEDULE_TIME_DESCRIPTIONS
        ]
    )
