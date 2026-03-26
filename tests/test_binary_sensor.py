"""Tests for ChargePoint public station binary sensor entities."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargepoint.const import (
    CONF_USERNAME,
    DOMAIN,
    OPTION_PUBLIC_CHARGERS,
)

from .conftest import (
    COULOMB_TOKEN,
    PUBLIC_STATION_ID,
    USERNAME,
    get_entity_id,
    make_communication_error,
    make_mock_station_info,
)

# ---------------------------------------------------------------------------
# Station-level binary sensor
# ---------------------------------------------------------------------------


async def test_public_station_entity_exists(
    hass, setup_integration_with_public_station
):
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id) is not None


async def test_public_station_is_available(hass, setup_integration_with_public_station):
    """Station is 'on' when station_status_v2 == 'available'."""
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    assert hass.states.get(entity_id).state == "on"


async def test_public_station_is_unavailable(
    hass, config_entry_with_public_station, mock_client_with_public_station
):
    """Station is 'off' when the charger is in use."""
    mock_client_with_public_station.get_station = AsyncMock(
        return_value=make_mock_station_info(available=False)
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client_with_public_station,
    ):
        config_entry_with_public_station.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry_with_public_station.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    assert hass.states.get(entity_id).state == "off"


async def test_public_station_available_ports_attribute(
    hass, setup_integration_with_public_station
):
    """available_ports attribute counts ports with status_v2 == 'available'."""
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    state = hass.states.get(entity_id)
    # make_mock_station_info(available=True): port1=available, port2=in_use → 1 available
    assert state.attributes["available_ports"] == 1
    assert state.attributes["total_ports"] == 2


# ---------------------------------------------------------------------------
# Per-port binary sensors
# ---------------------------------------------------------------------------


async def test_public_port_entities_created(
    hass, setup_integration_with_public_station
):
    """One binary sensor per port is created (2 ports in mock)."""
    port1_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_port_1_available"
    )
    port2_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_port_2_available"
    )
    assert port1_id is not None
    assert port2_id is not None


async def test_public_port_is_available(hass, setup_integration_with_public_station):
    """Port 1 is 'on' — mock sets it available=True."""
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_port_1_available"
    )
    assert hass.states.get(entity_id).state == "on"


async def test_public_port_is_in_use(hass, setup_integration_with_public_station):
    """Port 2 is always 'off' in the mock regardless of station availability."""
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_port_2_available"
    )
    assert hass.states.get(entity_id).state == "off"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_no_entities_when_no_locations_configured(hass, setup_integration):
    """No binary_sensor entities are created when no public locations are configured."""
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    assert entity_id is None


async def test_station_fetch_error_skipped(
    hass, config_entry_with_public_station, mock_client_with_public_station
):
    """CommunicationError for a station is logged and skipped; no coordinator failure."""
    mock_client_with_public_station.get_station = AsyncMock(
        side_effect=make_communication_error()
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client_with_public_station,
    ):
        config_entry_with_public_station.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry_with_public_station.entry_id)
        await hass.async_block_till_done()

    from homeassistant.config_entries import ConfigEntryState

    assert config_entry_with_public_station.state == ConfigEntryState.LOADED

    # Station should not have created any entities
    entity_id = get_entity_id(
        hass, "binary_sensor", f"public_{PUBLIC_STATION_ID}_available"
    )
    assert entity_id is None


# ---------------------------------------------------------------------------
# Multi-name device naming
# ---------------------------------------------------------------------------


async def test_station_device_name_combines_multiple_names(hass, mock_client):
    """When StationInfo.name has two entries, the device name joins them with a space."""
    info = make_mock_station_info()
    info.name = ["CLPCCD", "DO STATION 1"]
    mock_client.get_station = AsyncMock(return_value=info)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        options={
            OPTION_PUBLIC_CHARGERS: [
                {
                    "id": PUBLIC_STATION_ID,
                    "name": "CLPCCD",
                    "name2": "DO STATION 1",
                    "address": "123 Test St, Testville",
                }
            ]
        },
        entry_id="test_multi_name_entry",
        version=2,
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    identifier = (DOMAIN, f"public_{PUBLIC_STATION_ID}")
    device = device_registry.async_get_device(identifiers={identifier})
    assert device is not None
    assert device.name == "CLPCCD DO STATION 1 (123 Test St, Testville)"


async def test_station_device_name_single_name_unchanged(
    hass, setup_integration_with_public_station
):
    """When StationInfo.name has only one entry, the device name is unchanged."""
    device_registry = dr.async_get(hass)
    identifier = (DOMAIN, f"public_{PUBLIC_STATION_ID}")
    device = device_registry.async_get_device(identifiers={identifier})
    assert device is not None
    assert device.name == "Test Public Station (123 Test St, Testville)"
