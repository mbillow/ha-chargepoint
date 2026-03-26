"""Tests for ChargePoint integration setup and coordinator."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargepoint.const import (
    CONF_USERNAME,
    DOMAIN,
    OPTION_PUBLIC_CHARGERS,
)

from .conftest import (
    CHARGER_ID,
    COULOMB_TOKEN,
    PUBLIC_STATION_ID,
    USERNAME,
    make_communication_error,
    make_datadome_captcha,
    make_invalid_session,
    make_mock_station_info,
)

# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def test_setup_entry_success(hass, setup_integration, config_entry):
    assert config_entry.state == ConfigEntryState.LOADED


async def test_setup_entry_datadome_captcha_fails_auth(hass, config_entry):
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        side_effect=make_datadome_captcha(),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.SETUP_ERROR


async def test_setup_entry_invalid_session_fails_auth(hass, config_entry):
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        side_effect=make_invalid_session(),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.SETUP_ERROR


async def test_setup_entry_communication_error_not_ready(hass, config_entry):
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        side_effect=make_communication_error(),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.SETUP_RETRY


# ---------------------------------------------------------------------------
# Coordinator data fetching
# ---------------------------------------------------------------------------


async def test_coordinator_fetches_all_data(hass, setup_integration, mock_client):
    from custom_components.chargepoint.const import (
        ACCT_CHARGER_CONFIG,
        ACCT_CHARGER_STATUS,
        ACCT_CHARGER_TECH_INFO,
        ACCT_HOME_CRGS,
        ACCT_INFO,
        DATA_COORDINATOR,
    )

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]
    data = coordinator.data

    assert data[ACCT_INFO] is not None
    assert CHARGER_ID in data[ACCT_HOME_CRGS]

    charger_data = data[ACCT_HOME_CRGS][CHARGER_ID]
    assert charger_data[ACCT_CHARGER_STATUS] is not None
    assert charger_data[ACCT_CHARGER_TECH_INFO] is not None
    assert charger_data[ACCT_CHARGER_CONFIG] is not None


async def test_coordinator_fetches_active_session(
    hass, setup_integration_with_session, mock_client_with_session
):
    from custom_components.chargepoint.const import ACCT_SESSION, DATA_COORDINATOR

    coordinator = hass.data[DOMAIN][setup_integration_with_session.entry_id][
        DATA_COORDINATOR
    ]
    assert coordinator.data[ACCT_SESSION] is not None
    assert coordinator.data[ACCT_SESSION].session_id == 99999


async def test_coordinator_no_session_when_not_charging(hass, setup_integration):
    from custom_components.chargepoint.const import ACCT_SESSION, DATA_COORDINATOR

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]
    assert coordinator.data[ACCT_SESSION] is None


async def test_coordinator_invalid_session_raises_auth_failed(
    hass, setup_integration, mock_client
):
    from custom_components.chargepoint.const import DATA_COORDINATOR

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]
    mock_client.get_account = AsyncMock(side_effect=make_invalid_session())

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_datadome_captcha_raises_auth_failed(
    hass, setup_integration, mock_client
):
    from custom_components.chargepoint.const import DATA_COORDINATOR

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]
    mock_client.get_account = AsyncMock(side_effect=make_datadome_captcha())

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_communication_error_raises_update_failed(
    hass, setup_integration, mock_client
):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.chargepoint.const import DATA_COORDINATOR

    coordinator = hass.data[DOMAIN][setup_integration.entry_id][DATA_COORDINATOR]
    mock_client.get_account = AsyncMock(side_effect=make_communication_error())

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# ---------------------------------------------------------------------------
# async_unload_entry
# ---------------------------------------------------------------------------


async def test_unload_entry_calls_client_close(hass, setup_integration, mock_client):
    await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.state == ConfigEntryState.NOT_LOADED
    mock_client.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Legacy entity cleanup
# ---------------------------------------------------------------------------


async def test_old_switch_entity_removed_on_setup(hass, config_entry, mock_client):
    """The legacy charging_session switch is removed from the entity registry on setup."""
    entity_registry = er.async_get(hass)
    # Pre-populate the old switch entity as it would exist in an existing installation
    entity_registry.async_get_or_create(
        "switch", DOMAIN, f"{CHARGER_ID}_charging_session"
    )
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{CHARGER_ID}_charging_session"
        )
        is not None
    )

    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{CHARGER_ID}_charging_session"
        )
        is None
    )


async def test_old_switch_cleanup_is_idempotent(
    hass, setup_integration, config_entry, mock_client
):
    """Running setup again when the old entity is already gone does not error."""
    entity_registry = er.async_get(hass)
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{CHARGER_ID}_charging_session"
        )
        is None
    )

    # Reload should succeed cleanly
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.LOADED


# ---------------------------------------------------------------------------
# v0 → v1 migration
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# v1 → v2 migration: name2 field
# ---------------------------------------------------------------------------


async def test_migrate_v1_to_v2_adds_name2_to_public_chargers(hass, mock_client):
    """V1 → V2 migration adds name2: None to each tracked public charger entry."""
    v1_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        options={
            OPTION_PUBLIC_CHARGERS: [
                {"id": PUBLIC_STATION_ID, "name": "Old Station", "address": "1 St"},
            ]
        },
        entry_id="test_v1_entry",
        version=1,
    )
    mock_client.get_station = AsyncMock(return_value=make_mock_station_info())
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        v1_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(v1_entry.entry_id)
        await hass.async_block_till_done()

    assert v1_entry.version == 2
    chargers = v1_entry.options[OPTION_PUBLIC_CHARGERS]
    assert "name2" in chargers[0]


async def test_migrate_v1_to_v2_with_no_public_chargers(hass, mock_client):
    """V1 → V2 migration succeeds even when no public chargers are tracked."""
    v1_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        options={},
        entry_id="test_v1_no_chargers",
        version=1,
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        v1_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(v1_entry.entry_id)
        await hass.async_block_till_done()

    assert v1_entry.version == 2
    assert v1_entry.state == ConfigEntryState.LOADED


async def test_setup_backfills_name2_from_station_info(hass, mock_client):
    """On startup, name2 is populated from StationInfo.name when it was None."""
    info = make_mock_station_info()
    info.name = ["Station Name", "Port A"]
    mock_client.get_station = AsyncMock(return_value=info)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        options={
            OPTION_PUBLIC_CHARGERS: [
                {
                    "id": PUBLIC_STATION_ID,
                    "name": "Station Name",
                    "name2": None,
                    "address": "123 Test St, Testville",
                }
            ]
        },
        entry_id="test_backfill_entry",
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

    chargers = entry.options[OPTION_PUBLIC_CHARGERS]
    assert chargers[0]["name2"] == "Port A"


async def test_setup_does_not_update_when_name2_already_set(hass, mock_client):
    """name2 is not overwritten when it is already populated."""
    info = make_mock_station_info()
    info.name = ["Station Name", "Port B"]
    mock_client.get_station = AsyncMock(return_value=info)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        options={
            OPTION_PUBLIC_CHARGERS: [
                {
                    "id": PUBLIC_STATION_ID,
                    "name": "Station Name",
                    "name2": "Port A",
                    "address": "123 Test St, Testville",
                }
            ]
        },
        entry_id="test_no_overwrite_entry",
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

    chargers = entry.options[OPTION_PUBLIC_CHARGERS]
    assert chargers[0]["name2"] == "Port A"


# ---------------------------------------------------------------------------
# v0 → v1 migration
# ---------------------------------------------------------------------------


async def test_password_scrubbed_from_config_entry_on_setup(hass, mock_client):
    """Existing entries that stored a password should have it removed on first load."""
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: USERNAME,
            CONF_ACCESS_TOKEN: COULOMB_TOKEN,
            CONF_PASSWORD: "hunter2",
        },
        entry_id="test_chargepoint_entry",
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        legacy_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(legacy_entry.entry_id)
        await hass.async_block_till_done()

    assert CONF_PASSWORD not in legacy_entry.data
    assert legacy_entry.data[CONF_ACCESS_TOKEN] == COULOMB_TOKEN
    assert legacy_entry.data[CONF_USERNAME] == USERNAME
