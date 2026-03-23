"""Tests for ChargePoint number entities (LED brightness)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from .conftest import (
    CHARGER_ID,
    get_entity_id,
    make_communication_error,
    make_mock_charger_config,
)


async def test_led_brightness_exists(hass, setup_integration):
    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")
    assert entity_id is not None


async def test_led_brightness_current_level(hass, setup_integration):
    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")
    state = hass.states.get(entity_id)
    assert float(state.state) == 3


async def test_led_brightness_min_max(hass, setup_integration):
    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")
    state = hass.states.get(entity_id)
    assert float(state.attributes["min"]) == 0
    assert float(state.attributes["max"]) == 5
    assert float(state.attributes["step"]) == 1


async def test_led_brightness_unavailable_when_disabled(
    hass, config_entry, mock_client
):
    mock_client.get_home_charger_config = AsyncMock(
        return_value=make_mock_charger_config(led_enabled=False)
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")
    assert hass.states.get(entity_id).state == "unavailable"


async def test_set_led_brightness_success(hass, setup_integration, mock_client):
    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id, "value": 5},
        blocking=True,
    )
    mock_client.set_led_brightness.assert_awaited_once_with(CHARGER_ID, 5)


async def test_set_led_brightness_communication_error_raises(
    hass, setup_integration, mock_client
):
    mock_client.set_led_brightness = AsyncMock(side_effect=make_communication_error())
    entity_id = get_entity_id(hass, "number", f"{CHARGER_ID}_led_brightness")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": 2},
            blocking=True,
        )
