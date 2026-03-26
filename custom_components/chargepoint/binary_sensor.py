"""Binary sensor platform for ChargePoint public stations."""

from typing import Any, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    ACCT_PUBLIC_STATIONS,
    DATA_COORDINATOR,
    DOMAIN,
    PUBLIC_STATION_ID_PREFIX,
)

# Ordered so longer/more-specific substrings (e.g. "ccs2") are checked before
# shorter ones that would otherwise match first (e.g. "ccs").
_PLUG_ICONS: list[tuple[str, str]] = [
    ("j1772", "mdi:ev-plug-type1"),
    ("type1", "mdi:ev-plug-type1"),
    ("type 1", "mdi:ev-plug-type1"),
    ("ccs2", "mdi:ev-plug-ccs2"),
    ("combo2", "mdi:ev-plug-ccs2"),
    ("ccs", "mdi:ev-plug-ccs1"),
    ("combo", "mdi:ev-plug-ccs1"),
    ("chademo", "mdi:ev-plug-chademo"),
    ("nacs", "mdi:ev-plug-tesla"),
    ("tesla", "mdi:ev-plug-tesla"),
    ("type2", "mdi:ev-plug-type2"),
    ("type 2", "mdi:ev-plug-type2"),
    ("mennekes", "mdi:ev-plug-type2"),
]
_DEFAULT_PLUG_ICON = "mdi:ev-station"


def _plug_icon(display_plug_type: str) -> str:
    """Return the MDI icon that best matches a connector's display_plug_type string."""
    key = display_plug_type.lower()
    for pattern, icon in _PLUG_ICONS:
        if pattern in key:
            return icon
    return _DEFAULT_PLUG_ICON


def _station_device_info(device_id: int, info: Any) -> DeviceInfo:
    """Build DeviceInfo for a public station. Both entity types share the same device."""
    station_name = " ".join(info.name) if info.name else f"Station {device_id}"
    address = ", ".join(filter(None, [info.address.address1, info.address.city]))
    if address:
        station_name = f"{station_name} ({address})"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{PUBLIC_STATION_ID_PREFIX}{device_id}")},
        name=station_name,
        model=info.model_number or None,
        manufacturer=info.network.display_name or "ChargePoint",
        sw_version=info.device_software_version or None,
        serial_number=str(device_id),
        configuration_url=f"https://driver.chargepoint.com/stations/{device_id}",
    )


class ChargePointPublicStationBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor reporting overall station availability."""

    _attr_has_entity_name = True
    _attr_translation_key = "public_station"

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        info = self._station_info
        self._attr_unique_id = f"{PUBLIC_STATION_ID_PREFIX}{device_id}_available"
        self._attr_name = "Available"
        self._attr_device_info = _station_device_info(device_id, info)

    @property
    def _station_info(self) -> Any:
        return self.coordinator.data[ACCT_PUBLIC_STATIONS][self._device_id]

    @property
    def is_on(self) -> bool:
        return self._station_info.station_status_v2.lower() == "available"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self._station_info
        available_ports = sum(
            1 for p in info.ports_info.ports if p.status_v2.lower() == "available"
        )
        addr = info.address
        address_str = ", ".join(filter(None, [addr.address1, addr.city, addr.state]))
        return {
            "available_ports": available_ports,
            "total_ports": info.ports_info.port_count,
            "address": address_str,
        }


class ChargePointPublicPortBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor reporting individual port availability."""

    _attr_has_entity_name = True
    _attr_translation_key = "public_port"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: int,
        outlet_number: int,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._outlet_number = outlet_number
        info = self._station_info
        self._attr_unique_id = (
            f"{PUBLIC_STATION_ID_PREFIX}{device_id}_port_{outlet_number}_available"
        )
        self._attr_device_info = _station_device_info(device_id, info)

        # Derive name and icon from the port's connector type when available.
        port = next(
            (p for p in info.ports_info.ports if p.outlet_number == outlet_number),
            None,
        )
        if port and port.connector_list:
            plug_types = [c.display_plug_type for c in port.connector_list]
            self._attr_name = f"Port {outlet_number} ({', '.join(plug_types)})"
            self._attr_icon = _plug_icon(plug_types[0])
        else:
            self._attr_name = f"Port {outlet_number}"
            self._attr_icon = _DEFAULT_PLUG_ICON

    @property
    def _station_info(self) -> Any:
        return self.coordinator.data[ACCT_PUBLIC_STATIONS][self._device_id]

    @property
    def _port(self) -> Optional[Any]:
        for p in self._station_info.ports_info.ports:
            if p.outlet_number == self._outlet_number:
                return p
        return None

    @property
    def is_on(self) -> Optional[bool]:
        port = self._port
        if port is None:
            return None
        return port.status_v2.lower() == "available"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self._port
        if port is None:
            return {}
        return {
            "level": port.level,
            "connectors": [c.display_plug_type for c in port.connector_list],
            "max_power_kw": port.power_range.max if port.power_range else None,
        }


class ChargePointPublicSharedPowerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor reporting whether a station shares power across its ports."""

    _attr_has_entity_name = True
    _attr_translation_key = "public_station_shared_power"
    _attr_icon = "mdi:share-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{PUBLIC_STATION_ID_PREFIX}{device_id}_shared_power"
        self._attr_device_info = _station_device_info(device_id, self._station_info)

    @property
    def _station_info(self) -> Any:
        return self.coordinator.data[ACCT_PUBLIC_STATIONS][self._device_id]

    @property
    def is_on(self) -> Optional[bool]:
        return self._station_info.shared_power


class ChargePointPublicReducedPowerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor reporting whether a station is operating at reduced power."""

    _attr_has_entity_name = True
    _attr_translation_key = "public_station_reduced_power"
    _attr_icon = "mdi:lightning-bolt-off"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{PUBLIC_STATION_ID_PREFIX}{device_id}_reduced_power"
        self._attr_device_info = _station_device_info(device_id, self._station_info)

    @property
    def _station_info(self) -> Any:
        return self.coordinator.data[ACCT_PUBLIC_STATIONS][self._device_id]

    @property
    def is_on(self) -> Optional[bool]:
        return self._station_info.reduced_power


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities for each tracked public station."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        DATA_COORDINATOR
    ]
    entities: list[BinarySensorEntity] = []
    for device_id, info in coordinator.data.get(ACCT_PUBLIC_STATIONS, {}).items():
        entities.append(ChargePointPublicStationBinarySensor(coordinator, device_id))
        for port in info.ports_info.ports:
            entities.append(
                ChargePointPublicPortBinarySensor(
                    coordinator, device_id, port.outlet_number
                )
            )
        if info.shared_power is not None:
            entities.append(
                ChargePointPublicSharedPowerBinarySensor(coordinator, device_id)
            )
        if info.reduced_power is not None:
            entities.append(
                ChargePointPublicReducedPowerBinarySensor(coordinator, device_id)
            )
    async_add_entities(entities)
