"""Tests for ChargePoint sensor entities."""

from unittest.mock import AsyncMock, patch

from custom_components.chargepoint.const import (
    ACCT_CHARGER_STATUS,
    ACCT_HOME_CRGS,
    DOMAIN,
    DATA_COORDINATOR,
)

from .conftest import CHARGER_ID, USER_ID, get_entity_id, make_communication_error, make_mock_charger_status

# ---------------------------------------------------------------------------
# Account sensors
# ---------------------------------------------------------------------------


async def test_account_balance_state(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{USER_ID}_account_balance")
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "10.50"
    assert state.attributes["unit_of_measurement"] == "USD"


# ---------------------------------------------------------------------------
# Charger sensors — idle (no session)
# ---------------------------------------------------------------------------


async def test_charging_status_sensor(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_charging_status")
    state = hass.states.get(entity_id)
    assert state.state == "Available"


async def test_charging_cable_unplugged(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_plugged_in")
    state = hass.states.get(entity_id)
    assert state.state == "Unplugged"


async def test_charging_cable_plugged_in(hass, config_entry, mock_client):
    mock_client.get_home_charger_status = AsyncMock(
        return_value=make_mock_charger_status(plugged_in=True)
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_plugged_in")
    assert hass.states.get(entity_id).state == "Plugged In"


async def test_network_connected(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_connected")
    assert hass.states.get(entity_id).state == "Connected"


async def test_network_disconnected(hass, config_entry, mock_client):
    mock_client.get_home_charger_status = AsyncMock(
        return_value=make_mock_charger_status(connected=False)
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_connected")
    assert hass.states.get(entity_id).state == "Disconnected"


async def test_charger_state_not_charging(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_charging_state")
    assert hass.states.get(entity_id).state == "Not Charging"


async def test_session_sensors_zero_when_idle(hass, setup_integration):
    """All session sensors report 0 when no session is active."""
    for key in (
        "session_charging_time",
        "session_power_kw",
        "session_energy_kwh",
        "session_miles_added",
        "session_miles_added_per_hour",
    ):
        entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_{key}")
        assert hass.states.get(entity_id).state == "0", f"{key} should be 0 when idle"


async def test_session_cost_zero_when_idle(hass, setup_integration):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_cost")
    assert hass.states.get(entity_id).state == "0.00"


# ---------------------------------------------------------------------------
# Charger sensors — active IN_USE session
# ---------------------------------------------------------------------------


async def test_charger_state_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_charging_state")
    assert hass.states.get(entity_id).state == "In Use"


async def test_charging_time_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_charging_time")
    # 3_600_000 ms / 1000 = 3600 seconds
    assert hass.states.get(entity_id).state == "3600"


async def test_power_output_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_power_kw")
    assert hass.states.get(entity_id).state == "7.2"


async def test_energy_output_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_energy_kwh")
    assert hass.states.get(entity_id).state == "7.2"


async def test_miles_added_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_miles_added")
    assert hass.states.get(entity_id).state == "25.0"


async def test_miles_per_hour_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(
        hass, "sensor", f"{CHARGER_ID}_session_miles_added_per_hour"
    )
    assert hass.states.get(entity_id).state == "25.0"


async def test_charge_cost_active_session(hass, setup_integration_with_session):
    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_session_cost")
    assert hass.states.get(entity_id).state == "1.50"


# ---------------------------------------------------------------------------
# Charger entity availability
# ---------------------------------------------------------------------------


async def test_charger_entity_unavailable_when_status_is_none(
    hass, setup_integration, mock_client
):
    """When charger status fetch fails, charger entities become unavailable."""
    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]

    # Simulate a failed status fetch by patching the coordinator data directly
    coordinator.data[ACCT_HOME_CRGS][CHARGER_ID][ACCT_CHARGER_STATUS] = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_charging_status")
    state = hass.states.get(entity_id)
    assert state.state == "unavailable"


async def test_charger_entity_available_after_status_recovers(
    hass, setup_integration, mock_client
):
    """Charger entities recover availability when the API starts responding again."""
    from .conftest import make_mock_charger_status

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]

    # First fail the status fetch
    mock_client.get_home_charger_status = AsyncMock(
        side_effect=make_communication_error()
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "sensor", f"{CHARGER_ID}_charging_status")
    assert hass.states.get(entity_id).state == "unavailable"

    # Then recover
    mock_client.get_home_charger_status = AsyncMock(
        return_value=make_mock_charger_status()
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state != "unavailable"
