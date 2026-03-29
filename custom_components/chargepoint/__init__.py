"""
Custom integration to integrate ChargePoint with Home Assistant.

"""

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any, Mapping, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from python_chargepoint import ChargePoint
from python_chargepoint.exceptions import (
    CommunicationError,
    DatadomeCaptcha,
    InvalidSession,
    LoginError,
)
from python_chargepoint.session import ChargingSession
from python_chargepoint.types import (
    Account,
    HomeChargerConfiguration,
    HomeChargerSchedule,
    HomeChargerStatus,
    HomeChargerTechnicalInfo,
    UserChargingStatus,
)

from .const import (
    ACCT_CHARGER_CONFIG,
    ACCT_CHARGER_SCHEDULE,
    ACCT_CHARGER_STATUS,
    ACCT_CHARGER_TECH_INFO,
    ACCT_CRG_STATUS,
    ACCT_HOME_CRGS,
    ACCT_INFO,
    ACCT_PUBLIC_STATIONS,
    ACCT_SESSION,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    ISSUE_URL,
    OPTION_POLL_INTERVAL,
    OPTION_PUBLIC_CHARGERS,
    PLATFORMS,
    POLL_INTERVAL_DEFAULT,
    POLL_INTERVAL_OPTIONS,
    PUBLIC_STATION_ID_PREFIX,
    TOKEN_FILE_NAME,
    VERSION,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _migrate_public_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename public station entity IDs from name-based slugs to ID-based slugs.

    Entities registered before this fix have entity_ids derived from the station
    name (e.g. binary_sensor.my_station_123_main_st_available). This renames them
    to the stable ID-based form (e.g. binary_sensor.public_124429_available) so
    that the entity_id no longer changes if the station name or address changes.
    """
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        uid = entity_entry.unique_id or ""
        if not uid.startswith(PUBLIC_STATION_ID_PREFIX):
            continue
        desired_entity_id = f"{entity_entry.domain}.{uid}"
        if entity_entry.entity_id == desired_entity_id:
            continue
        try:
            entity_registry.async_update_entity(
                entity_entry.entity_id, new_entity_id=desired_entity_id
            )
            _LOGGER.debug(
                "Migrated public station entity ID: %s -> %s",
                entity_entry.entity_id,
                desired_entity_id,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Could not migrate entity ID %s to %s, skipping",
                entity_entry.entity_id,
                desired_entity_id,
            )


def _remove_stale_public_entities(
    hass: HomeAssistant, entry: ConfigEntry, current_public_ids: set
) -> None:
    """Remove entities and devices for public stations no longer being tracked."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        uid = entity_entry.unique_id or ""
        if not uid.startswith(PUBLIC_STATION_ID_PREFIX):
            continue
        try:
            device_id = int(uid.split("_")[1])
        except (IndexError, ValueError):
            continue
        if device_id not in current_public_ids:
            _LOGGER.debug(
                "Removing stale public station entity: %s", entity_entry.entity_id
            )
            entity_registry.async_remove(entity_entry.entity_id)

    # Remove the device itself for each stale station. HA won't do this
    # automatically when entities are removed programmatically.
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        for identifier in device_entry.identifiers:
            if identifier[0] != DOMAIN:
                continue
            key = identifier[1]
            if not isinstance(key, str) or not key.startswith(PUBLIC_STATION_ID_PREFIX):
                continue
            try:
                device_id = int(key.split("_")[1])
            except (IndexError, ValueError):
                break
            if device_id not in current_public_ids:
                _LOGGER.debug(
                    "Removing stale public station device: %s", device_entry.id
                )
                device_registry.async_remove_device(device_entry.id)
            break


async def _fetch_public_stations(
    client: ChargePoint, options: Mapping[str, Any]
) -> dict[int, Any]:
    """Fetch StationInfo for every tracked public station, concurrently."""
    chargers = options.get(OPTION_PUBLIC_CHARGERS, [])
    if not chargers:
        return {}

    async def _fetch_one(device_id: int) -> tuple[int, Any]:
        try:
            return device_id, await client.get_station(device_id)
        except CommunicationError:
            _LOGGER.warning("Failed to fetch public station %s, skipping", device_id)
            return device_id, None

    results = await asyncio.gather(*(_fetch_one(c["id"]) for c in chargers))
    return {device_id: info for device_id, info in results if info is not None}


def remove_legacy_password(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove stored password from config entry data when upgrading from <1.0.0."""
    if CONF_PASSWORD in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={k: v for k, v in entry.data.items() if k != CONF_PASSWORD}
        )


def remove_session_token_from_disk(hass: HomeAssistant) -> None:
    config_dir = hass.config.config_dir
    file = os.path.join(config_dir, TOKEN_FILE_NAME)
    if os.path.isfile(file):
        os.remove(file)


def _backfill_station_name2(
    hass: HomeAssistant, entry: ConfigEntry, public_data: dict
) -> None:
    """Populate name2 for any tracked public station where it is still None."""
    updated_chargers = []
    changed = False
    for charger in entry.options.get(OPTION_PUBLIC_CHARGERS, []):
        if charger.get("name2") is None:
            info = public_data.get(charger["id"])
            if info and len(info.name) > 1:
                charger = {**charger, "name2": info.name[1]}
                changed = True
        updated_chargers.append(charger)
    if changed:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, OPTION_PUBLIC_CHARGERS: updated_chargers},
        )


async def _async_fetch_home_charger_data(
    client: ChargePoint, charger: int
) -> dict[str, Any]:
    """Fetch all data for a single home charger concurrently, tolerating partial failures."""

    async def _safe_fetch(coro, warning_msg):
        try:
            return await coro
        except CommunicationError:
            _LOGGER.warning(warning_msg, charger)
            return None

    hcrg_status, hcrg_tech_info, hcrg_config, hcrg_schedule = await asyncio.gather(
        _safe_fetch(
            client.get_home_charger_status(charger),
            "Failed to get status for charger %s, charger will be marked unavailable",
        ),
        _safe_fetch(
            client.get_home_charger_technical_info(charger),
            "Failed to get technical info for charger %s",
        ),
        _safe_fetch(
            client.get_home_charger_config(charger),
            "Failed to get configuration for charger %s",
        ),
        _safe_fetch(
            client.get_home_charger_schedule(charger),
            "Failed to get schedule for charger %s",
        ),
    )

    return {
        ACCT_CHARGER_STATUS: hcrg_status,
        ACCT_CHARGER_TECH_INFO: hcrg_tech_info,
        ACCT_CHARGER_CONFIG: hcrg_config,
        ACCT_CHARGER_SCHEDULE: hcrg_schedule,
    }


async def _async_coordinator_update(
    client: ChargePoint, entry: ConfigEntry
) -> dict[str, Any]:
    """Fetch all ChargePoint data for one coordinator update cycle."""
    data: dict[str, Any] = {
        ACCT_INFO: None,
        ACCT_CRG_STATUS: None,
        ACCT_SESSION: None,
        ACCT_HOME_CRGS: {},
        ACCT_PUBLIC_STATIONS: {},
    }
    try:
        account: Account = await client.get_account()
        _LOGGER.debug("Account information: %s", account)
        data[ACCT_INFO] = account

        try:
            crg_status: Optional[UserChargingStatus] = (
                await client.get_user_charging_status()
            )
            _LOGGER.debug("User charging status: %s", crg_status)
            data[ACCT_CRG_STATUS] = crg_status

            if crg_status:
                try:
                    crg_session: ChargingSession = await client.get_charging_session(
                        crg_status.session_id
                    )
                    _LOGGER.debug("Charging session: %s", crg_session)
                    data[ACCT_SESSION] = crg_session
                except CommunicationError:
                    _LOGGER.warning(
                        "Failed to fetch active charging session details, "
                        "session data will be unavailable this update"
                    )
        except CommunicationError:
            _LOGGER.warning(
                "Failed to fetch user charging status, "
                "session data will be unavailable this update"
            )

        home_chargers: list = await client.get_home_chargers()
        results = await asyncio.gather(
            *(
                _async_fetch_home_charger_data(client, charger)
                for charger in home_chargers
            )
        )
        data[ACCT_HOME_CRGS] = dict(zip(home_chargers, results))

        data[ACCT_PUBLIC_STATIONS] = await _fetch_public_stations(client, entry.options)

        return data
    except (DatadomeCaptcha, InvalidSession) as exc:
        _LOGGER.error(
            "ChargePoint session is invalid or blocked by Datadome captcha. "
            "Reauthentication required."
        )
        raise ConfigEntryAuthFailed(exc) from exc
    except CommunicationError as err:
        _LOGGER.error("Failed to update ChargePoint State")
        raise UpdateFailed from err


async def async_setup(hass: HomeAssistant, entry: ConfigEntry):
    """Disallow configuration via YAML"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Load the saved entities."""
    _LOGGER.info(
        "Version %s is starting, if you have any issues please report them here: %s",
        VERSION,
        ISSUE_URL,
    )
    username = entry.data[CONF_USERNAME]
    coulomb_token: str = entry.data.get(CONF_ACCESS_TOKEN) or ""

    # Scrub the password from the config entry if upgrading from <1.0.0.
    remove_legacy_password(hass, entry)

    # Cleanup the old session token from disk, we only store it in the ConfigEntry now.
    await hass.async_add_executor_job(remove_session_token_from_disk, hass)

    try:
        client: ChargePoint = await ChargePoint.create(
            username,
            coulomb_token=coulomb_token,
        )
    except DatadomeCaptcha:
        _LOGGER.error(
            "Datadome bot-protection captcha triggered during ChargePoint setup. "
            "Reauthentication required."
        )
        raise ConfigEntryAuthFailed("Datadome captcha required — please reauthenticate")
    except InvalidSession:
        _LOGGER.error("ChargePoint coulomb token is invalid or expired")
        raise ConfigEntryAuthFailed("Session expired — please reauthenticate")
    except LoginError as exc:
        _LOGGER.error("Failed to authenticate to ChargePoint")
        raise ConfigEntryAuthFailed(exc) from exc
    except CommunicationError as exc:
        _LOGGER.error("Failed to communicate with ChargePoint during setup")
        raise ConfigEntryNotReady from exc

    hass.data.setdefault(DOMAIN, {})

    async def async_update_data():
        nonlocal client
        try:
            data = await _async_coordinator_update(client, entry)
        except RuntimeError:
            # The library raises RuntimeError("Must login to use ChargePoint API")
            # when the coulomb_sess cookie has expired from the aiohttp cookie jar.
            # Attempt to recover automatically using the stored token before
            # falling back to a full reauthentication prompt.
            _LOGGER.warning(
                "ChargePoint session has expired; attempting automatic re-login"
            )
            stored_token: str = entry.data.get(CONF_ACCESS_TOKEN) or ""
            try:
                await client.close()
                client = await ChargePoint.create(
                    username,
                    coulomb_token=stored_token,
                )
                hass.data[DOMAIN][entry.entry_id][DATA_CLIENT] = client
            except (DatadomeCaptcha, InvalidSession) as exc:
                _LOGGER.error(
                    "Automatic re-login failed; manual reauthentication required"
                )
                raise ConfigEntryAuthFailed(exc) from exc
            except CommunicationError as exc:
                raise UpdateFailed from exc
            data = await _async_coordinator_update(client, entry)

        current_token = entry.data.get(CONF_ACCESS_TOKEN)
        fresh_token = client.coulomb_token
        if fresh_token and fresh_token != current_token:
            _LOGGER.debug("Persisting refreshed coulomb_sess token to config entry")
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_ACCESS_TOKEN: fresh_token}
            )
        return data

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

    # Back-fill name2 for existing tracked public stations from live StationInfo data.
    _backfill_station_name2(hass, entry, coordinator.data.get(ACCT_PUBLIC_STATIONS, {}))

    # Remove the old charging_session switch entity — replaced by Start/Stop buttons
    entity_registry = er.async_get(hass)
    for charger_id in coordinator.data[ACCT_HOME_CRGS].keys():
        old_entity_id = entity_registry.async_get_entity_id(
            "switch", DOMAIN, f"{charger_id}_charging_session"
        )
        if old_entity_id:
            _LOGGER.debug(
                "Removing legacy charging_session switch entity: %s", old_entity_id
            )
            entity_registry.async_remove(old_entity_id)

    # Remove entities and devices for public stations that are no longer tracked.
    _remove_stale_public_entities(
        hass, entry, set(coordinator.data.get(ACCT_PUBLIC_STATIONS, {}).keys())
    )

    # Migrate public station entity IDs from name-based slugs to ID-based slugs.
    _migrate_public_entity_ids(hass, entry)

    # Setup components
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        client: ChargePoint = entry_data[DATA_CLIENT]
        await client.close()

    return unload_ok


class ChargePointEntity(CoordinatorEntity):
    """Base ChargePoint Entity"""

    def __init__(self, client, coordinator):
        """Initialize the ChargePoint entity."""
        super().__init__(coordinator)
        self.client = client

    @property
    def account(self) -> Account:
        """Shortcut to access account info for the entity."""
        return self.coordinator.data[ACCT_INFO]

    @property
    def charging_status(self) -> UserChargingStatus:
        """Shortcut to access charging status for the entity."""
        return self.coordinator.data[ACCT_CRG_STATUS]

    @property
    def session(self) -> Optional[ChargingSession]:
        """Shortcut to access the active charging session, if any."""
        return self.coordinator.data[ACCT_SESSION]


class ChargePointChargerEntity(CoordinatorEntity):
    """Base ChargePoint Charger Entity"""

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

        # Use station_nickname from config if available, fall back to model-based name
        charger_config = self.charger_config
        if charger_config and charger_config.station_nickname:
            device_name = charger_config.station_nickname
        elif "CPH" in self.short_charger_model:
            device_name = f"{self.manufacturer} Home Flex ({self.short_charger_model})"
        else:
            device_name = f"{self.manufacturer} {self.short_charger_model}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.charger_id))},
            manufacturer=self.manufacturer,
            model=self.charger_status.model,
            name=device_name,
            sw_version=self.technical_info.software_version,
            configuration_url="https://www.chargepoint.com",
        )

    @property
    def available(self) -> bool:
        """Return True only when coordinator has fresh status data for this charger."""
        if not super().available:
            return False
        charger_data = self.coordinator.data.get(ACCT_HOME_CRGS, {}).get(
            self.charger_id
        )
        return (
            charger_data is not None
            and charger_data.get(ACCT_CHARGER_STATUS) is not None
        )

    @property
    def charger_status(self) -> HomeChargerStatus:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id][
            ACCT_CHARGER_STATUS
        ]

    @property
    def technical_info(self) -> HomeChargerTechnicalInfo:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id][
            ACCT_CHARGER_TECH_INFO
        ]

    @property
    def charger_config(self) -> Optional[HomeChargerConfiguration]:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id].get(
            ACCT_CHARGER_CONFIG
        )

    @property
    def charger_schedule(self) -> Optional[HomeChargerSchedule]:
        return self.coordinator.data[ACCT_HOME_CRGS][self.charger_id].get(
            ACCT_CHARGER_SCHEDULE
        )

    @property
    def session(self) -> Optional[ChargingSession]:
        session: Optional[ChargingSession] = self.coordinator.data[ACCT_SESSION]
        if not session:
            return None

        _LOGGER.debug(
            "Session in progress, checking if home charger (%s): %s",
            self.charger_id,
            session,
        )
        if session.device_id == self.charger_id:
            return self.coordinator.data[ACCT_SESSION]
        return None

    @session.setter
    def session(self, new_session: Optional[ChargingSession]):
        self.coordinator.data[ACCT_SESSION] = new_session
