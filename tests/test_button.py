"""Tests for ChargePoint button entities."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from .conftest import (
    CHARGER_ID,
    get_entity_id,
    make_communication_error,
    make_mock_charger_status,
    make_mock_session,
)

# ---------------------------------------------------------------------------
# Restart charger button
# ---------------------------------------------------------------------------


async def test_restart_button_exists(hass, setup_integration):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_restart_charger")
    assert entity_id is not None
    assert hass.states.get(entity_id) is not None


async def test_restart_button_press(hass, setup_integration, mock_client):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_restart_charger")
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    mock_client.restart_home_charger.assert_awaited_once_with(CHARGER_ID)


async def test_restart_button_communication_error_raises(
    hass, setup_integration, mock_client
):
    mock_client.restart_home_charger = AsyncMock(side_effect=make_communication_error())
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_restart_charger")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )


# ---------------------------------------------------------------------------
# Start charging button
# ---------------------------------------------------------------------------


async def test_start_charging_button_exists(hass, setup_integration):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_start_charging_session")
    assert entity_id is not None


async def test_start_charging_button_press(hass, config_entry, mock_client):
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

    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_start_charging_session")
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    mock_client.start_charging_session.assert_awaited_once_with(CHARGER_ID)


async def test_start_charging_button_raises_when_not_plugged_in(
    hass, setup_integration, mock_client
):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_start_charging_session")
    # Default mock has is_plugged_in=False
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
    mock_client.start_charging_session.assert_not_awaited()


async def test_start_charging_communication_error_is_logged_not_raised(
    hass, config_entry, mock_client
):
    """ChargePoint sometimes errors even when the session started — treat as warning."""
    mock_client.get_home_charger_status = AsyncMock(
        return_value=make_mock_charger_status(plugged_in=True)
    )
    mock_client.start_charging_session = AsyncMock(
        side_effect=make_communication_error()
    )

    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_start_charging_session")
    # Should not raise — documented API quirk
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


# ---------------------------------------------------------------------------
# Stop charging button
# ---------------------------------------------------------------------------


async def test_stop_charging_button_exists(hass, setup_integration):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    assert entity_id is not None


async def test_stop_charging_button_unavailable_when_no_session(
    hass, setup_integration
):
    """Stop button should be unavailable when there is no active session."""
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    state = hass.states.get(entity_id)
    assert state.state == "unavailable"


async def test_stop_charging_button_available_when_session_in_use(
    hass, setup_integration_with_session
):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    state = hass.states.get(entity_id)
    assert state.state != "unavailable"


async def test_stop_charging_button_unavailable_when_session_not_in_use(
    hass, config_entry, mock_client
):
    from .conftest import make_mock_user_charging_status

    mock_client.get_user_charging_status = AsyncMock(
        return_value=make_mock_user_charging_status()
    )
    mock_client.get_charging_session = AsyncMock(
        return_value=make_mock_session(state="FULLY_CHARGED")
    )
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    assert hass.states.get(entity_id).state == "unavailable"


async def test_stop_charging_button_press(
    hass, setup_integration_with_session, mock_client_with_session
):
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    # session.stop() should have been called on the mock session object
    session = mock_client_with_session.get_charging_session.return_value
    session.stop.assert_awaited_once()


async def test_stop_charging_communication_error_does_not_raise(
    hass, setup_integration_with_session, mock_client_with_session
):
    session = mock_client_with_session.get_charging_session.return_value
    session.stop = AsyncMock(side_effect=make_communication_error())

    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


# ---------------------------------------------------------------------------
# Fast polling after charging actions
# ---------------------------------------------------------------------------


async def test_start_charging_schedules_fast_poll(hass, config_entry, mock_client):
    """Pressing start should schedule extra refreshes to pick up the new session state."""
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

    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_start_charging_session")
    with patch(
        "custom_components.chargepoint.button.async_call_later"
    ) as mock_call_later:
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )

    from custom_components.chargepoint.button import _CHARGING_FAST_POLL_DELAYS

    assert mock_call_later.call_count == len(_CHARGING_FAST_POLL_DELAYS)
    actual_delays = {call.args[1] for call in mock_call_later.call_args_list}
    assert actual_delays == set(_CHARGING_FAST_POLL_DELAYS)


async def test_stop_charging_schedules_fast_poll(
    hass, setup_integration_with_session, mock_client_with_session
):
    """Pressing stop should schedule extra refreshes to pick up the cleared session state."""
    entity_id = get_entity_id(hass, "button", f"{CHARGER_ID}_stop_charging_session")
    with patch(
        "custom_components.chargepoint.button.async_call_later"
    ) as mock_call_later:
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )

    from custom_components.chargepoint.button import _CHARGING_FAST_POLL_DELAYS

    assert mock_call_later.call_count == len(_CHARGING_FAST_POLL_DELAYS)
    actual_delays = {call.args[1] for call in mock_call_later.call_args_list}
    assert actual_delays == set(_CHARGING_FAST_POLL_DELAYS)
