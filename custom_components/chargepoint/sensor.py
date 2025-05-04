"""Sensor platform for ChargePoint."""

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import (
    ChargePointChargerEntity,
    ChargePointEntity,
    ChargePointEntityRequiredKeysMixin,
)
from .const import ACCT_HOME_CRGS, DATA_CLIENT, DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChargePointSensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this sensor, given the coordinator data and the configured unit system
    value: Callable[
        [Union["ChargePointSensorEntity", "ChargePointChargerSensorEntity"]], StateType
    ]


@dataclass
class ChargePointSensorEntityDescription(
    SensorEntityDescription,
    ChargePointEntityRequiredKeysMixin,
    ChargePointSensorRequiredKeysMixin,
):
    """Describes a ChargePoint sensor entity."""

    # Function to determine the unit of measurement for this sensor, given the configured unit system
    # Falls back to description.native_unit_of_measurement if it is not provided
    unit: Optional[
        Callable[
            [Union["ChargePointSensorEntity", "ChargePointChargerSensorEntity"]],
            StateType,
        ]
    ] = None


class ChargePointSensorEntity(SensorEntity, ChargePointEntity):
    """Representation of a ChargePoint Account sensor."""

    entity_description: ChargePointSensorEntityDescription

    def __init__(self, client, coordinator, description):
        """Initialize account sensor."""
        super().__init__(client, coordinator)
        self.entity_description = description

        self._attr_name = f"{self.account.user.username} {description.name_suffix}"
        self._attr_unique_id = f"{self.account.user.user_id}_{description.key}"

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement for the sensor, according to the configured unit system."""
        if unit_fn := self.entity_description.unit:
            return unit_fn(self)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.entity_description.value(self)


class ChargePointChargerSensorEntity(SensorEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charging Device Sensor."""

    entity_description: ChargePointSensorEntityDescription

    def __init__(self, client, coordinator, description, charger_id):
        """Initialize account sensor."""
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description

        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement for the sensor, according to the configured unit system."""
        if unit_fn := self.entity_description.unit:
            return unit_fn(self)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.entity_description.value(self)


ACCOUNT_SENSORS = [
    ChargePointSensorEntityDescription(
        key="account_balance",
        name_suffix="Account Balance",
        icon="mdi:wallet",
        device_class=SensorDeviceClass.MONETARY,
        unit=lambda entity: entity.account.account_balance.currency,
        state_class=SensorStateClass.TOTAL,
        value=lambda entity: f"{float(entity.account.account_balance.amount):.2f}",
    ),
]

CHARGER_SENSORS = [
    ChargePointSensorEntityDescription(
        key="charging_status",
        name_suffix="Charging Status",
        icon="mdi:lightning-bolt",
        value=lambda entity: str(entity.charger_status.charging_status)
        .replace("_", " ")
        .title(),
    ),
    ChargePointSensorEntityDescription(
        key="plugged_in",
        name_suffix="Charging Cable",
        icon="mdi:power-plug",
        value=lambda entity: (
            "Plugged In" if entity.charger_status.plugged_in else "Unplugged"
        ),
    ),
    ChargePointSensorEntityDescription(
        key="connected",
        name_suffix="Network",
        icon="mdi:wifi",
        value=lambda entity: (
            "Connected" if entity.charger_status.connected else "Disconnected"
        ),
    ),
    # Problem with ChargePoint API?  Disabling per https://github.com/mbillow/ha-chargepoint/issues/33
    #    ChargePointSensorEntityDescription(
    #        key="last_connected_at",
    #        name_suffix="Last Connected At",
    #        device_class=SensorDeviceClass.TIMESTAMP,
    #        icon="mdi:progress-clock",
    #        value=lambda entity: entity.charger_status.last_connected_at,
    #    ),
    ChargePointSensorEntityDescription(
        key="session_charging_state",
        name_suffix="Charger State",
        icon="mdi:battery-charging",
        value=lambda entity: (
            str(entity.session.charging_state).replace("_", " ").title()
            if entity.session
            else "Not Charging"
        ),
    ),
    ChargePointSensorEntityDescription(
        key="session_charging_time",
        name_suffix="Charging Time",
        icon="mdi:timer",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda entity: (
            int(entity.session.charging_time / 1000) if entity.session else 0
        ),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    ChargePointSensorEntityDescription(
        key="session_power_kw",
        name_suffix="Power Output",
        icon="mdi:transmission-tower",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda entity: round(entity.session.power_kw, 2) if entity.session else 0,
        native_unit_of_measurement="kW",
    ),
    ChargePointSensorEntityDescription(
        key="session_energy_kwh",
        name_suffix="Energy Output",
        icon="mdi:lightning-bolt-circle",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda entity: (
            round(entity.session.energy_kwh, 2) if entity.session else 0
        ),
        native_unit_of_measurement="kWh",
    ),
    ChargePointSensorEntityDescription(
        key="session_miles_added",
        name_suffix="Miles Added",
        icon="mdi:road-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda entity: (
            round(entity.session.miles_added, 2) if entity.session else 0
        ),
        native_unit_of_measurement="miles",
    ),
    ChargePointSensorEntityDescription(
        key="session_miles_added_per_hour",
        name_suffix="Miles / Hour Added",
        icon="mdi:car-speed-limiter",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda entity: (
            round(entity.session.miles_added_per_hour, 2) if entity.session else 0
        ),
        native_unit_of_measurement="mph",
    ),
    ChargePointSensorEntityDescription(
        key="session_cost",
        name_suffix="Charge Cost",
        icon="mdi:cash-multiple",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        value=lambda entity: (
            f"{entity.session.total_amount:.2f}" if entity.session else "0.00"
        ),
        unit=lambda entity: entity.client.global_config.default_currency.symbol,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = []

    for description in ACCOUNT_SENSORS:
        entities.append(ChargePointSensorEntity(client, coordinator, description))

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for description in CHARGER_SENSORS:
            entities.append(
                ChargePointChargerSensorEntity(
                    client, coordinator, description, charger_id
                )
            )

    async_add_entities(entities)
