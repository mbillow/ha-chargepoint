"""Diagnostics support for ChargePoint."""

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    ACCT_CRG_STATUS,
    ACCT_HOME_CRGS,
    ACCT_INFO,
    ACCT_PUBLIC_STATIONS,
    ACCT_SESSION,
    CONF_COULOMB_TOKEN,
    DATA_COORDINATOR,
    DOMAIN,
    VERSION,
)

TO_REDACT = {
    "email",
    "phone",
    "account_number",
    "mac_address",
    "wifi_mac",
    "device_ip",
    "serial_number",
    "station_nickname",
    "latitude",
    "longitude",
    "host_name",
    "street_address",
    "address1",
    "address2",
    "city",
    "zipCode",
    "zip_code",
    "full_name",
    "given_name",
    "family_name",
    "ccLastFour",
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_ACCESS_TOKEN,
    CONF_COULOMB_TOKEN,
}


def _serialize(obj: Any) -> Any:
    """Convert a python-chargepoint object to a JSON-safe dict."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return obj


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    data = coordinator.data

    home_chargers = {
        str(charger_id): {k: _serialize(v) for k, v in charger_data.items()}
        for charger_id, charger_data in data.get(ACCT_HOME_CRGS, {}).items()
    }

    public_stations = {
        str(device_id): _serialize(info)
        for device_id, info in data.get(ACCT_PUBLIC_STATIONS, {}).items()
    }

    entity_registry = er.async_get(hass)
    entities = [
        {
            "entity_id": entry.entity_id,
            "unique_id": entry.unique_id,
            "domain": entry.domain,
            "disabled_by": str(entry.disabled_by) if entry.disabled_by else None,
            "state": (
                state.state
                if (state := hass.states.get(entry.entity_id))
                else "unavailable"
            ),
        }
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
    ]

    last_exception = coordinator.last_exception
    return async_redact_data(
        {
            "integration_version": VERSION,
            "config_entry": {
                "data": dict(config_entry.data),
                "options": dict(config_entry.options),
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                "last_exception": str(last_exception) if last_exception else None,
            },
            "account": _serialize(data.get(ACCT_INFO)),
            "charging_status": _serialize(data.get(ACCT_CRG_STATUS)),
            "charging_session": _serialize(data.get(ACCT_SESSION)),
            "home_chargers": home_chargers,
            "public_stations": public_stations,
            "entities": entities,
        },
        TO_REDACT,
    )
