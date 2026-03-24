"""Tests for the ChargePoint config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargepoint.const import (
    CONF_COULOMB_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    OPTION_POLL_INTERVAL,
    OPTION_PUBLIC_CHARGERS,
)

from .conftest import (
    COULOMB_TOKEN,
    PUBLIC_STATION_ID,
    USERNAME,
    make_communication_error,
    make_datadome_captcha,
    make_invalid_session,
    make_login_error,
    make_mock_map_station,
    make_mock_station_info,
)

# ---------------------------------------------------------------------------
# User step
# ---------------------------------------------------------------------------


async def test_user_step_shows_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_step_success(hass):
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(COULOMB_TOKEN, None, None)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == USERNAME
    assert result["data"][CONF_USERNAME] == USERNAME
    assert result["data"][CONF_ACCESS_TOKEN] == COULOMB_TOKEN


async def test_user_step_invalid_credentials(hass):
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "invalid_credentials", None)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}


async def test_user_step_communication_error(hass):
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "unknown_error", None)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown_error"}


async def test_user_step_captcha_redirects_to_captcha_token_step(hass):
    captcha_url = "https://example.com/captcha"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "captcha", captcha_url)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "captcha_token"
    assert result["description_placeholders"]["captcha_url"] == captcha_url


async def test_user_step_aborts_if_already_configured(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        unique_id=USERNAME,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(COULOMB_TOKEN, None, None)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Captcha token step
# ---------------------------------------------------------------------------


async def test_captcha_token_step_success(hass):
    captcha_url = "https://example.com/captcha"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "captcha", captcha_url)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    assert result["step_id"] == "captcha_token"

    with patch(
        "custom_components.chargepoint.config_flow._login_with_token",
        new=AsyncMock(return_value=(COULOMB_TOKEN, None)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_COULOMB_TOKEN: "my-coulomb-sess-cookie"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCESS_TOKEN] == COULOMB_TOKEN


async def test_captcha_token_step_invalid_token(hass):
    captcha_url = "https://example.com/captcha"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "captcha", captcha_url)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    with patch(
        "custom_components.chargepoint.config_flow._login_with_token",
        new=AsyncMock(return_value=(None, "invalid_token")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_COULOMB_TOKEN: "bad-token"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "captcha_token"
    assert result["errors"] == {"base": "invalid_token"}


async def test_captcha_token_step_empty_token(hass):
    captcha_url = "https://example.com/captcha"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "captcha", captcha_url)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": USERNAME, "password": "secret"},
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_COULOMB_TOKEN: ""},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "captcha_token"
    assert result["errors"] == {"base": "invalid_token"}


# ---------------------------------------------------------------------------
# Underlying auth helpers
# ---------------------------------------------------------------------------


async def test_login_with_password_success(hass):
    from custom_components.chargepoint.config_flow import _login_with_password

    mock_client = AsyncMock()
    mock_client.coulomb_token = COULOMB_TOKEN

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        token, error, captcha_url = await _login_with_password(USERNAME, "secret")

    assert token == COULOMB_TOKEN
    assert error is None
    assert captcha_url is None
    mock_client.login_with_password.assert_awaited_once_with("secret")
    mock_client.close.assert_awaited_once()


async def test_login_with_password_login_error(hass):
    from custom_components.chargepoint.config_flow import _login_with_password

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.return_value.login_with_password = AsyncMock(
            side_effect=make_login_error()
        )
        token, error, captcha_url = await _login_with_password(USERNAME, "bad")

    assert token is None
    assert error == "invalid_credentials"
    assert captcha_url is None


async def test_login_with_password_datadome_captcha(hass):
    from custom_components.chargepoint.config_flow import _login_with_password

    exc = make_datadome_captcha("https://captcha.example.com")

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.return_value.login_with_password = AsyncMock(side_effect=exc)
        token, error, captcha_url = await _login_with_password(USERNAME, "secret")

    assert token is None
    assert error == "captcha"
    assert captcha_url == "https://captcha.example.com"


async def test_login_with_password_communication_error(hass):
    from custom_components.chargepoint.config_flow import _login_with_password

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        side_effect=make_communication_error(),
    ):
        token, error, captcha_url = await _login_with_password(USERNAME, "secret")

    assert token is None
    assert error == "unknown_error"


async def test_login_with_token_success(hass):
    from custom_components.chargepoint.config_flow import _login_with_token

    mock_client = AsyncMock()
    mock_client.coulomb_token = COULOMB_TOKEN

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        token, error = await _login_with_token(USERNAME, "my-coulomb-sess")

    assert token == COULOMB_TOKEN
    assert error is None


async def test_login_with_token_invalid_session(hass):
    from custom_components.chargepoint.config_flow import _login_with_token

    with patch(
        "custom_components.chargepoint.config_flow.ChargePoint.create",
        side_effect=make_invalid_session(),
    ):
        token, error = await _login_with_token(USERNAME, "bad-token")

    assert token is None
    assert error == "invalid_token"


# ---------------------------------------------------------------------------
# Reauth flow
# ---------------------------------------------------------------------------


async def test_reauth_confirm_shows_form(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        entry_id="reauth_test_entry",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_confirm_success(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: "old-token"},
        entry_id="reauth_test_entry",
    )
    entry.add_to_hass(hass)

    new_token = "fresh-coulomb-token"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(new_token, None, None)),
    ), patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"password": "new-secret"},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == new_token


async def test_reauth_confirm_invalid_credentials(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        entry_id="reauth_test_entry",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "invalid_credentials", None)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"password": "wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}


async def test_reauth_confirm_captcha_redirects_to_captcha_token_step(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: USERNAME, CONF_ACCESS_TOKEN: COULOMB_TOKEN},
        entry_id="reauth_test_entry",
    )
    entry.add_to_hass(hass)

    captcha_url = "https://captcha.example.com"
    with patch(
        "custom_components.chargepoint.config_flow._login_with_password",
        new=AsyncMock(return_value=(None, "captcha", captcha_url)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"password": "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "captcha_token"


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


async def test_options_flow_shows_menu(hass, setup_integration, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert "update_settings" in result["menu_options"]
    assert "manage_chargers" in result["menu_options"]


async def test_options_update_settings(hass, setup_integration, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "update_settings"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "update_settings"

    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={OPTION_POLL_INTERVAL: "60"},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "options_successful"
    assert config_entry.options[OPTION_POLL_INTERVAL] == 60


async def test_options_manage_chargers_shows_submenu(
    hass, setup_integration, config_entry
):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "manage_chargers"
    assert "add_chargers" in result["menu_options"]
    # No chargers tracked yet — remove should not appear
    assert "remove_charger" not in result["menu_options"]


async def test_options_manage_chargers_shows_remove_when_chargers_exist(
    hass, setup_integration_with_public_station, config_entry_with_public_station
):
    result = await hass.config_entries.options.async_init(
        config_entry_with_public_station.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    assert result["type"] == FlowResultType.MENU
    assert "remove_charger" in result["menu_options"]


async def test_options_add_chargers_success(
    hass, setup_integration, config_entry, mock_client
):
    mock_client.get_nearby_stations = AsyncMock(return_value=[make_mock_map_station()])
    mock_client.get_station = AsyncMock(return_value=make_mock_station_info())

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_chargers"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_chargers"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "location": {"latitude": 37.0, "longitude": -122.0, "radius": 200.0}
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_chargers"

    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"charger_ids": [str(PUBLIC_STATION_ID)]},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "options_successful"
    chargers = config_entry.options[OPTION_PUBLIC_CHARGERS]
    assert len(chargers) == 1
    assert chargers[0]["id"] == PUBLIC_STATION_ID
    assert chargers[0]["name"] == "Test Public Station"


async def test_options_add_chargers_no_results(
    hass, setup_integration, config_entry, mock_client
):
    mock_client.get_nearby_stations = AsyncMock(return_value=[])

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"location": {"latitude": 0.0, "longitude": 0.0, "radius": 200.0}},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_chargers"
    assert result["errors"] == {"base": "no_stations_found"}


async def test_options_add_chargers_communication_error(
    hass, setup_integration, config_entry, mock_client
):
    mock_client.get_nearby_stations = AsyncMock(side_effect=make_communication_error())

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "location": {"latitude": 37.0, "longitude": -122.0, "radius": 200.0}
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_chargers"
    assert result["errors"] == {"base": "unknown_error"}


async def test_options_add_chargers_does_not_duplicate_existing(
    hass,
    setup_integration_with_public_station,
    config_entry_with_public_station,
    mock_client_with_public_station,
):
    """Selecting an already-tracked station in the search results doesn't duplicate it."""
    mock_client_with_public_station.get_nearby_stations = AsyncMock(
        return_value=[make_mock_map_station()]
    )

    result = await hass.config_entries.options.async_init(
        config_entry_with_public_station.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "location": {"latitude": 37.0, "longitude": -122.0, "radius": 200.0}
        },
    )
    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"charger_ids": [str(PUBLIC_STATION_ID)]},
        )

    assert result["type"] == FlowResultType.ABORT
    chargers = config_entry_with_public_station.options[OPTION_PUBLIC_CHARGERS]
    assert len(chargers) == 1


async def test_options_remove_charger_shows_multiselect(
    hass, setup_integration_with_public_station, config_entry_with_public_station
):
    """Remove charger shows a multi-select; single charger is pre-checked."""
    result = await hass.config_entries.options.async_init(
        config_entry_with_public_station.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "remove_charger"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_charger"

    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"charger_ids": [str(PUBLIC_STATION_ID)]},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "options_successful"
    assert config_entry_with_public_station.options[OPTION_PUBLIC_CHARGERS] == []


async def test_options_charger_ids_stored_as_ints(
    hass, setup_integration, config_entry, mock_client
):
    mock_client.get_nearby_stations = AsyncMock(return_value=[make_mock_map_station()])
    mock_client.get_station = AsyncMock(return_value=make_mock_station_info())

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_chargers"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "location": {"latitude": 37.0, "longitude": -122.0, "radius": 200.0}
        },
    )
    with patch("homeassistant.config_entries.ConfigEntries.async_reload"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"charger_ids": [str(PUBLIC_STATION_ID)]},
        )

    chargers = config_entry.options[OPTION_PUBLIC_CHARGERS]
    assert isinstance(chargers[0]["id"], int)
