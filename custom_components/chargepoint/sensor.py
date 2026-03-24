"""Sensor platform for ChargePoint."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import ChargePointChargerEntity, ChargePointEntity
from .const import (
    ACCT_HOME_CRGS,
    ACCT_PUBLIC_STATIONS,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    PUBLIC_STATION_ID_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChargePointSensorEntityDescription(SensorEntityDescription):
    """Describes a ChargePoint sensor entity."""

    name_suffix: str = ""
    value: Callable[..., StateType] = field(default=lambda _: None)
    unit: Optional[Callable[..., StateType]] = None


class ChargePointSensorEntity(SensorEntity, ChargePointEntity):
    """Representation of a ChargePoint Account sensor."""

    entity_description: ChargePointSensorEntityDescription  # type: ignore[assignment]

    def __init__(self, client, coordinator, description):
        super().__init__(client, coordinator)
        self.entity_description = description
        self._attr_name = f"{self.account.user.username} {description.name_suffix}"
        self._attr_unique_id = f"{self.account.user.user_id}_{description.key}"

    @property
    def native_unit_of_measurement(self):
        if unit_fn := self.entity_description.unit:
            return unit_fn(self)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self):
        return self.entity_description.value(self)


class ChargePointChargerSensorEntity(SensorEntity, ChargePointChargerEntity):
    """Representation of a ChargePoint Charging Device Sensor."""

    entity_description: ChargePointSensorEntityDescription  # type: ignore[assignment]

    def __init__(self, client, coordinator, description, charger_id):
        super().__init__(client, coordinator, charger_id)
        self.entity_description = description
        self._attr_name = f"{self.short_charger_model} {description.name_suffix}"
        self._attr_unique_id = f"{charger_id}_{description.key}"

    @property
    def native_unit_of_measurement(self):
        if unit_fn := self.entity_description.unit:
            return unit_fn(self)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self):
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
    ChargePointSensorEntityDescription(
        key="session_state",
        name_suffix="Session State",
        icon="mdi:battery-charging",
        value=lambda entity: (
            str(entity.session.charging_state).replace("_", " ").title()
            if entity.session
            else "Not Charging"
        ),
    ),
    ChargePointSensorEntityDescription(
        key="session_power_kw",
        name_suffix="Session Power",
        icon="mdi:transmission-tower",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kW",
        value=lambda entity: round(entity.session.power_kw, 2) if entity.session else 0,
    ),
    ChargePointSensorEntityDescription(
        key="session_energy_kwh",
        name_suffix="Session Energy",
        icon="mdi:lightning-bolt-circle",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="kWh",
        value=lambda entity: (
            round(entity.session.energy_kwh, 2) if entity.session else 0
        ),
    ),
    ChargePointSensorEntityDescription(
        key="session_cost",
        name_suffix="Session Cost",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit=lambda entity: entity.client.global_config.default_currency.symbol,
        value=lambda entity: (
            f"{entity.session.total_amount:.2f}" if entity.session else "0.00"
        ),
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
            "Plugged In" if entity.charger_status.is_plugged_in else "Unplugged"
        ),
    ),
    ChargePointSensorEntityDescription(
        key="connected",
        name_suffix="Network",
        icon="mdi:wifi",
        value=lambda entity: (
            "Connected" if entity.charger_status.is_connected else "Disconnected"
        ),
    ),
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


class ChargePointPublicStationSensor(CoordinatorEntity, SensorEntity):
    """Base class for diagnostic sensors on a tracked public station."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        # Reference the device already registered by the binary_sensor platform.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{PUBLIC_STATION_ID_PREFIX}{device_id}")}
        )

    @property
    def _info(self) -> Any:
        return self.coordinator.data[ACCT_PUBLIC_STATIONS][self._device_id]


class ChargePointPublicMaxPowerSensor(ChargePointPublicStationSensor):
    """Reports the station's maximum charge rate in kW."""

    _attr_name = "Max Power"
    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kW"

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{PUBLIC_STATION_ID_PREFIX}{device_id}_max_power"

    @property
    def native_value(self) -> Optional[float]:
        mp = self._info.max_power
        return round(mp.max, 1) if mp else None


class ChargePointPublicOpenStatusSensor(ChargePointPublicStationSensor):
    """Reports whether the station is currently open or closed."""

    _attr_name = "Hours"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = (
            f"{PUBLIC_STATION_ID_PREFIX}{device_id}_open_close_status"
        )

    @property
    def native_value(self) -> Optional[str]:
        return self._info.open_close_status or None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = [
        ChargePointSensorEntity(client, coordinator, description)
        for description in ACCOUNT_SENSORS
    ]

    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        for description in CHARGER_SENSORS:
            entities.append(
                ChargePointChargerSensorEntity(
                    client, coordinator, description, charger_id
                )
            )

    for device_id in coordinator.data.get(ACCT_PUBLIC_STATIONS, {}).keys():
        entities.extend(
            [
                ChargePointPublicMaxPowerSensor(coordinator, device_id),
                ChargePointPublicOpenStatusSensor(coordinator, device_id),
            ]
        )

    async_add_entities(entities)
