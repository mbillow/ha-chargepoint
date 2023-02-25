"""
Custom integration to integrate ChargePoint with Home Assistant.

"""
import os
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_ACCESS_TOKEN
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
    CoordinatorEntity,
)

from python_chargepoint import ChargePoint
from python_chargepoint.session import ChargingSession
from python_chargepoint.types import (
    ChargePointAccount,
    UserChargingStatus,
    HomeChargerStatus,
    HomeChargerTechnicalInfo,
)
from python_chargepoint.exceptions import (
    ChargePointLoginError,
    ChargePointCommunicationException,
    ChargePointBaseException,
    ChargePointInvalidSession,
)

from .const import (
    DOMAIN,
    ISSUE_URL,
    PLATFORMS,
    VERSION,
    ACCT_INFO,
    ACCT_CRG_STATUS,
    ACCT_SESSION,
    ACCT_HOME_CRGS,
    DATA_CLIENT,
    DATA_COORDINATOR,
    TOKEN_FILE_NAME,
)

SCAN_INTERVAL = timedelta(minutes=5)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def persist_session_token(
    hass: HomeAssistant, entry: ConfigEntry, session_token: str
) -> None:
    config_dir = hass.config.config_dir
    file = os.path.join(config_dir, TOKEN_FILE_NAME)
    session_dict = {}
    if os.path.isfile(file):
        with open(file, "r") as spf:
            try:
                session_dict = json.load(spf)
            except json.decoder.JSONDecodeError:
                _LOGGER.error("Failed to load existing session data, overwriting!")
    _LOGGER.info("Persisting session token to %s", file)
    session_dict[entry.entry_id] = session_token
    with open(os.open(file, os.O_CREAT | os.O_WRONLY, 0o600), "w") as spf:
        json.dump(session_dict, spf)


def retrieve_session_token(hass: HomeAssistant, entry: ConfigEntry) -> Optional[str]:
    config_dir = hass.config.config_dir
    file = os.path.join(config_dir, TOKEN_FILE_NAME)
    _LOGGER.info("Retrieving session token from: %s", file)
    if os.path.isfile(file):
        with open(file, "r") as spf:
            try:
                sessions = json.load(spf)
                return sessions.get(entry.entry_id)
            except json.decoder.JSONDecodeError:
                _LOGGER.error("Failed to decode JSON session data in %s", file)
                return


async def async_setup(hass: HomeAssistant, entry: ConfigEntry):
    """Disallow configuration via YAML"""

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Load the saved entities."""
    _LOGGER.info(
        "Version %s is starting, if you have any issues please report" " them here: %s",
        VERSION,
        ISSUE_URL,
    )
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    original_session_token = entry.data[CONF_ACCESS_TOKEN]
    session_token = retrieve_session_token(hass, entry) or original_session_token

    try:
        client: ChargePoint = await hass.async_add_executor_job(
            ChargePoint, username, password, session_token
        )
        persist_session_token(hass, entry, client.session_token)
    except ChargePointLoginError as exc:
        _LOGGER.error("Failed to authenticate to ChargePoint")
        raise ConfigEntryAuthFailed from exc
    except ChargePointBaseException as exc:
        _LOGGER.error("Unknown ChargePoint Error!")
        raise ConfigEntryNotReady from exc

    hass.data.setdefault(DOMAIN, {})

    async def async_update_data(is_retry: bool = False):
        """Fetch data from ChargePoint API"""
        data = {
            ACCT_INFO: None,
            ACCT_CRG_STATUS: None,
            ACCT_SESSION: None,
            ACCT_HOME_CRGS: {},
        }
        try:
            account: ChargePointAccount = await hass.async_add_executor_job(
                client.get_account
            )
            data[ACCT_INFO] = account

            crg_status: Optional[
                UserChargingStatus
            ] = await hass.async_add_executor_job(client.get_user_charging_status)
            data[ACCT_CRG_STATUS] = crg_status

            if crg_status:
                crg_session: ChargingSession = await hass.async_add_executor_job(
                    client.get_charging_session, crg_status.session_id
                )
                data[ACCT_SESSION] = crg_session

            home_chargers: list = await hass.async_add_executor_job(
                client.get_home_chargers
            )
            for charger in home_chargers:
                hcrg_status: HomeChargerStatus = await hass.async_add_executor_job(
                    client.get_home_charger_status, charger
                )
                hcrg_tech_info: HomeChargerTechnicalInfo = (
                    await hass.async_add_executor_job(
                        client.get_home_charger_technical_info, charger
                    )
                )
                data[ACCT_HOME_CRGS][charger] = (hcrg_status, hcrg_tech_info)

            return data
        except ChargePointInvalidSession:
            if not is_retry:
                _LOGGER.warning(
                    "ChargePoint Session Token is invalid, attempting to re-login"
                )
                await hass.async_add_executor_job(client.login, username, password)
                persist_session_token(hass, entry, client.session_token)
                return await async_update_data(is_retry=True)
            raise
        except ChargePointCommunicationException as err:
            _LOGGER.error("Failed to update ChargePoint State")
            raise UpdateFailed from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=3),
    )

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Setup components
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ChargePointEntity(CoordinatorEntity):
    """Base ChargePoint Entity"""

    def __init__(self, client, coordinator):
        """Initialize the ChargePoint entity."""
        super().__init__(coordinator)
        self.client = client

    @property
    def account(self) -> ChargePointAccount:
        """Shortcut to access account info for the entity."""
        return self.coordinator.data[ACCT_INFO]

    @property
    def charging_status(self) -> UserChargingStatus:
        """Shortcut to access charging status for the entity."""
        return self.coordinator.data[ACCT_CRG_STATUS]


class ChargePointChargerEntity(CoordinatorEntity):
    """Base ChargePoint Entity"""

    def __init__(
        self, client: ChargePoint, coordinator: DataUpdateCoordinator, charger_id: int
    ):
        """Initialize the ChargePoint entity."""
        super().__init__(coordinator)
        self.client = client
        self.charger_id = charger_id
        self.manufacturer = (
            "ChargePoint"
            if self.charger_status.brand == "CP"
            else self.charger_status.brand
        )
        self.short_charger_model = self.charger_status.model.split("-")[0]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.charger_id))},
            manufacturer=self.manufacturer,
            model=self.charger_status.model,
            name=f"{self.manufacturer} Home Flex ({self.short_charger_model})"
            if "CPH" in self.short_charger_model
            else f"{self.manufacturer} {self.short_charger_model}",
            sw_version=self.technical_info.software_version,
        )

    @property
    def charger_status(self) -> HomeChargerStatus:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id][0]

    @property
    def technical_info(self) -> HomeChargerTechnicalInfo:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id][1]

    @property
    def session(self) -> Optional[ChargingSession]:
        session: ChargingSession = self.coordinator.data[ACCT_SESSION]
        if session and session.device_id == self.charger_id:
            return self.coordinator.data[ACCT_SESSION]

    @session.setter
    def session(self, new_session: Optional[ChargingSession]):
        self.coordinator.data[ACCT_SESSION] = new_session


@dataclass
class ChargePointEntityRequiredKeysMixin:
    """Mixin for required keys on all entities."""

    # Suffix to be appended to the entity name
    name_suffix: str
