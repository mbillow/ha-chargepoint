"""Tests for ChargePoint select entities."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from .conftest import (
    CHARGER_ID,
    get_entity_id,
    make_communication_error,
    make_mock_charger_status,
)


async def test_amperage_select_exists(hass, setup_integration):
    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    assert entity_id is not None


async def test_amperage_select_options(hass, setup_integration):
    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    state = hass.states.get(entity_id)
    assert state.attributes["options"] == ["16", "20", "24", "32"]


async def test_amperage_select_current_value(hass, setup_integration):
    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    state = hass.states.get(entity_id)
    assert state.state == "24"


async def test_set_amperage_limit_success(hass, config_entry, mock_client):
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

    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "32"},
        blocking=True,
    )
    mock_client.set_amperage_limit.assert_awaited_once_with(CHARGER_ID, 32)


async def test_set_amperage_limit_works_when_not_plugged_in(
    hass, setup_integration, mock_client
):
    # Default mock has is_plugged_in=False — limit should still be settable
    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "32"},
        blocking=True,
    )
    mock_client.set_amperage_limit.assert_awaited_once_with(CHARGER_ID, 32)


async def test_set_amperage_limit_communication_error_raises(
    hass, config_entry, mock_client
):
    mock_client.get_home_charger_status = AsyncMock(
        return_value=make_mock_charger_status(plugged_in=True)
    )
    mock_client.set_amperage_limit = AsyncMock(side_effect=make_communication_error())

    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "select", f"{CHARGER_ID}_charging_amperage_limit")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "32"},
            blocking=True,
        )
