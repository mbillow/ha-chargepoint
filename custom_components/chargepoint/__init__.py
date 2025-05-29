"""
Custom integration to integrate ChargePoint with Home Assistant.

"""

import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from python_chargepoint import ChargePoint
from python_chargepoint.exceptions import (
    ChargePointBaseException,
    ChargePointCommunicationException,
    ChargePointInvalidSession,
    ChargePointLoginError,
)
from python_chargepoint.session import ChargingSession
from python_chargepoint.types import (
    ChargePointAccount,
    HomeChargerStatus,
    HomeChargerTechnicalInfo,
    UserChargingStatus,
)

from .const import (
    ACCT_CRG_STATUS,
    ACCT_HOME_CRGS,
    ACCT_INFO,
    ACCT_SESSION,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    ISSUE_URL,
    OPTION_POLL_INTERVAL,
    PLATFORMS,
    POLL_INTERVAL_DEFAULT,
    POLL_INTERVAL_OPTIONS,
    TOKEN_FILE_NAME,
    VERSION,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def remove_session_token_from_disk(hass: HomeAssistant) -> None:
    config_dir = hass.config.config_dir
    file = os.path.join(config_dir, TOKEN_FILE_NAME)
    if os.path.isfile(file):
        os.remove(file)


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
    session_token = entry.data[CONF_ACCESS_TOKEN]

    # Cleanup the old session token from disk, we only store it in the ConfigEntry now.
    await hass.async_add_executor_job(remove_session_token_from_disk, hass)

    try:
        client: ChargePoint = await hass.async_add_executor_job(
            ChargePoint, username, password, session_token
        )

        if client.session_token != session_token:
            _LOGGER.debug("Session token refreshed by client, updating config entry")
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_ACCESS_TOKEN: session_token,
                },
            )
    except ChargePointLoginError as exc:
        _LOGGER.error("Failed to authenticate to ChargePoint")
        raise ConfigEntryAuthFailed(exc) from exc
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
            _LOGGER.debug("Account information: %s", account)
            data[ACCT_INFO] = account

            crg_status: Optional[UserChargingStatus] = (
                await hass.async_add_executor_job(client.get_user_charging_status)
            )
            _LOGGER.debug("User charging status: %s", crg_status)
            data[ACCT_CRG_STATUS] = crg_status

            if crg_status:
                crg_session: ChargingSession = await hass.async_add_executor_job(
                    client.get_charging_session, crg_status.session_id
                )
                _LOGGER.debug("Charging session: %s", crg_session)
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
                try:
                    await hass.async_add_executor_job(client.login, username, password)
                    hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_ACCESS_TOKEN: session_token,
                        },
                    )
                    return await async_update_data(is_retry=True)
                except ChargePointLoginError as exc:
                    _LOGGER.error("Failed to authenticate to ChargePoint")
                    raise ConfigEntryAuthFailed(exc) from exc

        except ChargePointCommunicationException as err:
            _LOGGER.error("Failed to update ChargePoint State")
            raise UpdateFailed from err

    poll_interval = entry.options.get(OPTION_POLL_INTERVAL, POLL_INTERVAL_DEFAULT)
    if poll_interval not in POLL_INTERVAL_OPTIONS.values():
        _LOGGER.warning(
            "Invalid poll interval %s, using default %s",
            poll_interval,
            POLL_INTERVAL_DEFAULT,
        )
        poll_interval = POLL_INTERVAL_DEFAULT

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=poll_interval),
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
            name=(
                f"{self.manufacturer} Home Flex ({self.short_charger_model})"
                if "CPH" in self.short_charger_model
                else f"{self.manufacturer} {self.short_charger_model}"
            ),
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
        if not session:
            return

        _LOGGER.debug(
            "Session in progress, checking if home charger (%s): %s",
            self.charger_id,
            session,
        )
        if session.device_id == self.charger_id:
            return self.coordinator.data[ACCT_SESSION]

    @session.setter
    def session(self, new_session: Optional[ChargingSession]):
        self.coordinator.data[ACCT_SESSION] = new_session


@dataclass
class ChargePointEntityRequiredKeysMixin:
    """Mixin for required keys on all entities."""

    # Suffix to be appended to the entity name
    name_suffix: str
