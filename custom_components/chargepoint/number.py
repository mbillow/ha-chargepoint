"""Number platform for ChargePoint — LED brightness control."""

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from python_chargepoint.exceptions import CommunicationError

from . import ChargePointChargerEntity
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChargePointLEDBrightnessNumber(NumberEntity, ChargePointChargerEntity):
    """Number entity for controlling home charger LED brightness."""

    _attr_native_min_value = 0
    _attr_native_max_value = 5
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:brightness-6"

    def __init__(self, client, coordinator, charger_id):
        super().__init__(client, coordinator, charger_id)
        self._attr_name = f"{self.short_charger_model} LED Brightness"
        self._attr_unique_id = f"{self.account.user.user_id}_{charger_id}_led_brightness"

    @property
    def available(self) -> bool:
        cfg = self.charger_config
        return super().available and cfg is not None and cfg.led_brightness.is_enabled

    @property
    def native_value(self) -> float | None:
        cfg = self.charger_config
        if cfg is None:
            return None
        return float(cfg.led_brightness.level)

    async def async_set_native_value(self, value: float) -> None:
        level = int(value)
        try:
            _LOGGER.debug(
                "Setting LED brightness on charger %s to level %d",
                self.charger_id,
                level,
            )
            await self.client.set_led_brightness(self.charger_id, level)
        except CommunicationError as exc:
            raise HomeAssistantError(f"Failed to set LED brightness: {exc}") from exc
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities = [
        ChargePointLEDBrightnessNumber(client, coordinator, charger_id)
        for charger_id in coordinator.data[ACCT_HOME_CRGS].keys()
    ]

    async_add_entities(entities)
