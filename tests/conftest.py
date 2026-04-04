"""Shared fixtures for ChargePoint integration tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry
from python_chargepoint.exceptions import (
    CommunicationError,
    DatadomeCaptcha,
    InvalidSession,
    LoginError,
)

from custom_components.chargepoint.const import (
    CONF_USERNAME,
    DOMAIN,
    OPTION_PUBLIC_CHARGERS,
)

# ---------------------------------------------------------------------------
# Enable custom integrations for every test in this package
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Ensure HA loads from custom_components/ for all tests."""


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

CHARGER_ID = 11111111
USER_ID = 12345
USERNAME = "test@example.com"
COULOMB_TOKEN = "test-coulomb-token-abc123"

PUBLIC_STATION_ID = 124429
PUBLIC_STATION_ID_2 = 567890


# ---------------------------------------------------------------------------
# Mock object factories
# Used directly in fixtures and in tests that need modified variants.
# ---------------------------------------------------------------------------


def make_mock_account():
    account = MagicMock()
    account.user.username = USERNAME
    account.user.user_id = USER_ID
    account.account_balance.currency = "USD"
    account.account_balance.amount = "10.50"
    return account


def make_mock_charger_status(*, plugged_in=False, connected=True):
    status = MagicMock()
    status.brand = "CP"
    status.model = "CPH50-NEMA6-50-L23"
    status.charging_status = "AVAILABLE"
    status.is_plugged_in = plugged_in
    status.is_connected = connected
    status.amperage_limit = 24
    status.possible_amperage_limits = [16, 20, 24, 32]
    status.charger_id = CHARGER_ID
    return status


def make_mock_tech_info():
    tech = MagicMock()
    tech.model_number = "CPH50-NEMA6-50-L23"
    tech.software_version = "1.2.3"
    tech.serial_number = "ABC123"
    return tech


def make_mock_charger_config(
    *, led_enabled=True, led_level=3, nickname="My Home Charger"
):
    config = MagicMock()
    config.station_nickname = nickname
    config.led_brightness.level = led_level
    config.led_brightness.is_enabled = led_enabled
    config.led_brightness.supported_levels = [0, 1, 2, 3, 4, 5]
    return config


def make_mock_session(*, state="IN_USE", device_id=CHARGER_ID):
    session = MagicMock()
    session.session_id = 99999
    session.device_id = device_id
    session.charging_state = state
    session.charging_time = 3_600_000  # 1 hour in milliseconds
    session.power_kw = 7.2
    session.energy_kwh = 7.2
    session.miles_added = 25.0
    session.miles_added_per_hour = 25.0
    session.total_amount = 1.50
    session.stop = AsyncMock()
    return session


def make_mock_station_info(*, available: bool = True) -> MagicMock:
    """Return a MagicMock shaped like StationInfo."""
    info = MagicMock()
    info.station_status_v2 = "available" if available else "in_use"
    info.name = ["Test Public Station"]
    info.model_number = "CPF50"
    info.device_software_version = "2.1.0"
    info.network.display_name = "ChargePoint"
    info.address.address1 = "123 Test St"
    info.address.city = "Testville"
    info.address.state = "CA"
    info.open_close_status = "Open 24 Hours"
    info.shared_power = False
    info.reduced_power = False
    info.ports_info.port_count = 2

    max_power = MagicMock()
    max_power.max = 7.2
    info.max_power = max_power

    connector = MagicMock()
    connector.display_plug_type = "J1772"

    port_power = MagicMock()
    port_power.max = 7.2

    port1 = MagicMock()
    port1.outlet_number = 1
    port1.status_v2 = "available" if available else "in_use"
    port1.level = "L2"
    port1.connector_list = [connector]
    port1.power_range = port_power

    port2 = MagicMock()
    port2.outlet_number = 2
    port2.status_v2 = "in_use"
    port2.level = "L2"
    port2.connector_list = [connector]
    port2.power_range = port_power

    info.ports_info.ports = [port1, port2]
    return info


def make_mock_map_station(
    device_id: int = PUBLIC_STATION_ID, name2: str | None = None
) -> MagicMock:
    """Return a MagicMock shaped like MapStation."""
    station = MagicMock()
    station.device_id = device_id
    station.name1 = "Test Public Station"
    station.name2 = name2
    station.address1 = "123 Test St"
    station.city = "Testville"
    station.station_status_v2 = "available"
    return station


def make_mock_user_charging_status():
    status = MagicMock()
    status.session_id = 99999
    return status


def make_mock_home_charger_schedule(*, enabled=True):
    weekdays = MagicMock()
    weekdays.start_time = "09:00"
    weekdays.end_time = "17:00"

    weekends = MagicMock()
    weekends.start_time = "10:00"
    weekends.end_time = "14:00"

    user_schedule = MagicMock()
    user_schedule.weekdays = weekdays
    user_schedule.weekends = weekends

    schedule = MagicMock()
    schedule.schedule_enabled = enabled
    schedule.user_schedule = user_schedule
    schedule.default_schedule = None
    return schedule


# ---------------------------------------------------------------------------
# Exception factories — constructors require args in python-chargepoint 2.x
# ---------------------------------------------------------------------------


def make_communication_error(message="API error"):
    return CommunicationError(MagicMock(), message)


def make_login_error(message="Invalid credentials"):
    return LoginError(MagicMock(), message)


def make_invalid_session(message="Session expired"):
    return InvalidSession(MagicMock(), message)


def make_datadome_captcha(
    captcha_url="https://geo.captcha-delivery.com/captcha/", message="Captcha required"
):
    return DatadomeCaptcha(captcha_url, message)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


def make_mock_client():
    """Build a fully-mocked ChargePoint client with no active session."""
    client = MagicMock()
    client.coulomb_token = COULOMB_TOKEN
    client.global_config.default_currency.symbol = "USD"
    client.get_account = AsyncMock(return_value=make_mock_account())
    client.get_user_charging_status = AsyncMock(return_value=None)
    client.get_home_chargers = AsyncMock(return_value=[CHARGER_ID])
    client.get_home_charger_status = AsyncMock(return_value=make_mock_charger_status())
    client.get_home_charger_technical_info = AsyncMock(
        return_value=make_mock_tech_info()
    )
    client.get_home_charger_config = AsyncMock(return_value=make_mock_charger_config())
    client.get_home_charger_schedule = AsyncMock(
        return_value=make_mock_home_charger_schedule()
    )
    client.set_home_charger_schedule = AsyncMock()
    client.disable_home_charger_schedule = AsyncMock()
    client.set_amperage_limit = AsyncMock()
    client.set_led_brightness = AsyncMock()
    client.restart_home_charger = AsyncMock()
    client.start_charging_session = AsyncMock(return_value=make_mock_session())
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_client():
    """A fully-mocked ChargePoint client with no active session."""
    return make_mock_client()


@pytest.fixture
def mock_client_with_session(mock_client):
    """A mock client that reports an active IN_USE charging session."""
    mock_client.get_user_charging_status = AsyncMock(
        return_value=make_mock_user_charging_status()
    )
    mock_client.get_charging_session = AsyncMock(return_value=make_mock_session())
    return mock_client


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: USERNAME,
            CONF_ACCESS_TOKEN: COULOMB_TOKEN,
        },
        entry_id="test_chargepoint_entry",
        version=1,
    )


@pytest.fixture
async def setup_integration(hass, config_entry, mock_client):
    """Set up the integration with no active session."""
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def config_entry_with_public_station():
    """Config entry pre-configured to track one public station."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: USERNAME,
            CONF_ACCESS_TOKEN: COULOMB_TOKEN,
        },
        options={
            OPTION_PUBLIC_CHARGERS: [
                {
                    "id": PUBLIC_STATION_ID,
                    "name": "Test Public Station",
                    "address": "123 Test St, Testville",
                }
            ]
        },
        entry_id="test_chargepoint_public_entry",
        version=1,
    )


@pytest.fixture
def mock_client_with_public_station(mock_client):
    """Mock client that returns a public station."""
    mock_client.get_station = AsyncMock(return_value=make_mock_station_info())
    return mock_client


@pytest.fixture
def mock_client_with_public_session(mock_client):
    """Mock client with an active IN_USE session at a public station (not a home charger)."""
    mock_client.get_user_charging_status = AsyncMock(
        return_value=make_mock_user_charging_status()
    )
    mock_client.get_charging_session = AsyncMock(
        return_value=make_mock_session(device_id=PUBLIC_STATION_ID)
    )
    return mock_client


@pytest.fixture
async def setup_integration_with_public_station(
    hass, config_entry_with_public_station, mock_client_with_public_station
):
    """Set up the integration with one tracked public station."""
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client_with_public_station,
    ):
        config_entry_with_public_station.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry_with_public_station.entry_id)
        await hass.async_block_till_done()
    return config_entry_with_public_station


@pytest.fixture
async def setup_integration_with_public_session(
    hass, config_entry, mock_client_with_public_session
):
    """Set up the integration with an active public charging session."""
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client_with_public_session,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


@pytest.fixture
async def setup_integration_with_session(hass, config_entry, mock_client_with_session):
    """Set up the integration with an active IN_USE charging session."""
    with patch(
        "custom_components.chargepoint.ChargePoint.create",
        new_callable=AsyncMock,
        return_value=mock_client_with_session,
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_entity_id(hass, platform, unique_id):
    """Look up an entity_id by platform and unique_id via the entity registry."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, unique_id)
