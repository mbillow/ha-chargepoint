"""Adds config flow for ChargePoint."""

import asyncio
import logging
import math
from collections import OrderedDict
from typing import Any, Mapping, Tuple

import voluptuous as vol
from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import selector
from python_chargepoint import ChargePoint
from python_chargepoint.exceptions import (
    CommunicationError,
    DatadomeCaptcha,
    InvalidSession,
    LoginError,
)
from python_chargepoint.global_config import ZoomBounds
from python_chargepoint.types import MapStation

from .const import (
    CONF_COULOMB_TOKEN,
    DATA_CLIENT,
    DOMAIN,
    OPTION_POLL_INTERVAL,
    OPTION_PUBLIC_CHARGERS,
    POLL_INTERVAL_DEFAULT,
    POLL_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


def _login_schema(username: str = "") -> vol.Schema:
    return vol.Schema(
        OrderedDict(
            [
                (vol.Required(CONF_USERNAME, default=username), str),
                (vol.Required("password", default=""), str),
            ]
        )
    )


def _reauth_schema() -> vol.Schema:
    return vol.Schema({vol.Required("password", default=""): str})


def _captcha_token_schema() -> vol.Schema:
    return vol.Schema({vol.Required(CONF_COULOMB_TOKEN, default=""): str})


def _poll_interval_schema(
    poll_interval: int | str = POLL_INTERVAL_DEFAULT,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(OPTION_POLL_INTERVAL, default=str(poll_interval)): selector(
                {
                    "select": {
                        "mode": "dropdown",
                        "options": [
                            {"label": k, "value": str(v)}
                            for k, v in POLL_INTERVAL_OPTIONS.items()
                        ],
                    }
                }
            )
        }
    )


def _connector_summary(info: Any) -> str:
    """Return a compact per-port connector summary, e.g. 'CHAdeMO/Combo, 2x J1772'."""
    port_types: list[str] = []
    for port in info.ports_info.ports:
        types = [c.display_plug_type for c in port.connector_list]
        if types:
            port_types.append("/".join(types))
    counts: dict[str, int] = {}
    for pt in port_types:
        counts[pt] = counts.get(pt, 0) + 1
    return ", ".join(f"{n}x {pt}" if n > 1 else pt for pt, n in sorted(counts.items()))


def _bounds_from_center(lat: float, lon: float, radius_m: float) -> ZoomBounds:
    """Convert a center point + radius (metres) to a lat/lon bounding box."""
    lat_d = radius_m / 111_000
    lon_d = radius_m / (111_000 * math.cos(math.radians(lat)))
    return ZoomBounds(
        sw_lat=lat - lat_d,
        sw_lon=lon - lon_d,
        ne_lat=lat + lat_d,
        ne_lon=lon + lon_d,
    )


async def _login_with_password(
    username: str, password: str
) -> Tuple[str | None, str | None, str | None]:
    """Attempt password login. Returns (coulomb_token, error_key, captcha_url)."""
    try:
        client = await ChargePoint.create(username)
        await client.login_with_password(password)
        token = client.coulomb_token
        await client.close()
        return token, None, None
    except DatadomeCaptcha as exc:
        _LOGGER.warning("Datadome captcha triggered for user %s", username)
        return None, "captcha", exc.captcha
    except LoginError:
        _LOGGER.exception("Invalid credentials for ChargePoint user %s", username)
        return None, "invalid_credentials", None
    except CommunicationError:
        _LOGGER.exception("Failed to communicate with ChargePoint")
        return None, "unknown_error", None


async def _login_with_token(
    username: str, coulomb_token: str
) -> Tuple[str | None, str | None]:
    """Attempt token login. Returns (coulomb_token, error_key)."""
    try:
        client = await ChargePoint.create(username, coulomb_token=coulomb_token)
        token = client.coulomb_token
        await client.close()
        return token, None
    except (DatadomeCaptcha, InvalidSession):
        _LOGGER.exception("Invalid or expired coulomb token for user %s", username)
        return None, "invalid_token"
    except CommunicationError:
        _LOGGER.exception("Failed to communicate with ChargePoint")
        return None, "unknown_error"


class ChargePointFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for ChargePoint."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self):
        self._reauth_entry: ConfigEntry | None = None
        self._username: str | None = None
        self._captcha_url: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup: ask for username and password."""
        username = ""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input["password"]

            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()

            token, error, captcha_url = await _login_with_password(username, password)

            if captcha_url:
                self._username = username
                self._captcha_url = captcha_url
                return await self.async_step_captcha_token()

            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=username,
                    data={CONF_USERNAME: username, CONF_ACCESS_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_login_schema(username),
            errors=errors,
        )

    async def async_step_captcha_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a coulomb token after bot-protection was triggered."""
        errors = {}

        if user_input is not None:
            coulomb_token = user_input.get(CONF_COULOMB_TOKEN, "").strip()
            if not coulomb_token:
                errors["base"] = "invalid_token"
            else:
                assert self._username is not None
                token, error = await _login_with_token(self._username, coulomb_token)
                if error:
                    errors["base"] = error
                else:
                    if self._reauth_entry is not None:
                        self.hass.config_entries.async_update_entry(
                            self._reauth_entry,
                            data={
                                **self._reauth_entry.data,
                                CONF_ACCESS_TOKEN: token,
                            },
                        )
                        await self.hass.config_entries.async_reload(
                            self._reauth_entry.entry_id
                        )
                        return self.async_abort(reason="reauth_successful")

                    return self.async_create_entry(
                        title=self._username,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_ACCESS_TOKEN: token,
                        },
                    )

        return self.async_show_form(
            step_id="captcha_token",
            data_schema=_captcha_token_schema(),
            description_placeholders={
                "captcha_url": self._captcha_url or "",
                "driver_url": "https://driver.chargepoint.com",
                "faq_url": "https://github.com/mbillow/ha-chargepoint/blob/main/FAQ.md#how-do-i-get-my-coulomb_sess-session-token",
            },
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Triggered when reauth is needed."""
        entry_id: str = self.context.get("entry_id", "")
        self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        assert self._reauth_entry is not None
        self._username = self._reauth_entry.data[CONF_USERNAME]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authenticate with password."""
        errors = {}

        assert self._username is not None
        assert self._reauth_entry is not None

        if user_input is not None:
            password = user_input["password"]
            token, error, captcha_url = await _login_with_password(
                self._username, password
            )

            if captcha_url:
                self._captcha_url = captcha_url
                return await self.async_step_captcha_token()

            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_ACCESS_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_reauth_schema(),
            description_placeholders={"username": self._username},
            errors=errors,
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle options flow for ChargePoint."""

    def __init__(self) -> None:
        self._nearby_stations: list[MapStation] = []
        self._nearby_station_details: dict[int, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show main menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["update_settings", "manage_chargers"],
        )

    async def async_step_update_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage poll interval."""
        if user_input is not None:
            poll_interval = int(user_input[OPTION_POLL_INTERVAL])
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={
                    **self.config_entry.options,
                    OPTION_POLL_INTERVAL: poll_interval,
                },
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_abort(reason="options_successful")

        return self.async_show_form(
            step_id="update_settings",
            data_schema=_poll_interval_schema(
                self.config_entry.options.get(
                    OPTION_POLL_INTERVAL, POLL_INTERVAL_DEFAULT
                )
            ),
        )

    async def async_step_manage_chargers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show charger management sub-menu."""
        chargers = self.config_entry.options.get(OPTION_PUBLIC_CHARGERS, [])
        menu_options = ["add_chargers"]
        if chargers:
            menu_options.append("remove_charger")
        return self.async_show_menu(
            step_id="manage_chargers", menu_options=menu_options
        )

    async def async_step_add_chargers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a search area on the map to find nearby stations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            loc = user_input.get("location")
            if not loc:
                errors["base"] = "location_required"
            else:
                lat = float(loc["latitude"])
                lon = float(loc["longitude"])
                radius_m = float(loc.get("radius", 200.0))
                bounds = _bounds_from_center(lat, lon, radius_m)
                client = self.hass.data[DOMAIN][self.config_entry.entry_id][DATA_CLIENT]
                try:
                    self._nearby_stations = await client.get_nearby_stations(bounds)
                except CommunicationError:
                    errors["base"] = "unknown_error"
                else:
                    if not self._nearby_stations:
                        errors["base"] = "no_stations_found"
                    else:
                        self._nearby_station_details = {}
                        results = await asyncio.gather(
                            *(
                                client.get_station(s.device_id)
                                for s in self._nearby_stations
                            ),
                            return_exceptions=True,
                        )
                        for station, result in zip(self._nearby_stations, results):
                            if not isinstance(result, Exception):
                                self._nearby_station_details[station.device_id] = result
                        return await self.async_step_select_chargers()

        return self.async_show_form(
            step_id="add_chargers",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "location",
                        description={
                            "suggested_value": {
                                "latitude": self.hass.config.latitude,
                                "longitude": self.hass.config.longitude,
                                "radius": 200,
                            }
                        },
                    ): selector({"location": {"radius": True}}),
                }
            ),
            errors=errors,
        )

    async def async_step_select_chargers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Multi-select which nearby stations to add."""
        chargers: list[dict[str, Any]] = self.config_entry.options.get(
            OPTION_PUBLIC_CHARGERS, []
        )
        existing_ids = {c["id"] for c in chargers}

        if user_input is not None:
            selected_ids = [int(v) for v in user_input.get("charger_ids", [])]
            station_lookup = {s.device_id: s for s in self._nearby_stations}
            new_chargers = list(chargers)
            for sid in selected_ids:
                if sid not in existing_ids:
                    station = station_lookup[sid]
                    addr = ", ".join(filter(None, [station.address1, station.city]))
                    entry: dict[str, Any] = {
                        "id": sid,
                        "name": station.name1,
                        "name2": station.name2 or None,
                        "address": addr,
                    }
                    detail = self._nearby_station_details.get(sid)
                    if detail:
                        entry["connectors"] = _connector_summary(detail)
                    new_chargers.append(entry)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={
                    **self.config_entry.options,
                    OPTION_PUBLIC_CHARGERS: new_chargers,
                },
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_abort(reason="options_successful")

        options = []
        for s in self._nearby_stations:
            detail = self._nearby_station_details.get(s.device_id)
            summary = _connector_summary(detail) if detail else ""
            combined_name = " ".join(filter(None, [s.name1, s.name2]))
            parts = filter(
                None, [combined_name, s.address1, s.city, f"ID: {s.device_id}", summary]
            )
            options.append({"value": str(s.device_id), "label": " · ".join(parts)})
        pre_selected = [
            str(s.device_id)
            for s in self._nearby_stations
            if s.device_id in existing_ids
        ]
        return self.async_show_form(
            step_id="select_chargers",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "charger_ids",
                        default=pre_selected,
                    ): selector(
                        {
                            "select": {
                                "multiple": True,
                                "mode": "list",
                                "options": options,
                            }
                        }
                    )
                }
            ),
        )

    async def async_step_remove_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more tracked public chargers via a multi-select checklist."""
        chargers: list[dict[str, Any]] = self.config_entry.options.get(
            OPTION_PUBLIC_CHARGERS, []
        )

        if user_input is not None:
            remove_ids = {int(v) for v in user_input.get("charger_ids", [])}
            new_chargers = [c for c in chargers if c["id"] not in remove_ids]
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={
                    **self.config_entry.options,
                    OPTION_PUBLIC_CHARGERS: new_chargers,
                },
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_abort(reason="options_successful")

        options = []
        for c in chargers:
            combined_name = " ".join(filter(None, [c["name"], c.get("name2")]))
            parts = filter(
                None,
                [
                    combined_name,
                    c.get("address"),
                    f"ID: {c['id']}",
                    c.get("connectors"),
                ],
            )
            options.append({"value": str(c["id"]), "label": " · ".join(parts)})
        # Pre-select all when there is only one so the user just hits Submit to confirm.
        default: list[str] = [str(chargers[0]["id"])] if len(chargers) == 1 else []
        return self.async_show_form(
            step_id="remove_charger",
            data_schema=vol.Schema(
                {
                    vol.Optional("charger_ids", default=default): selector(
                        {
                            "select": {
                                "multiple": True,
                                "mode": "list",
                                "options": options,
                            }
                        }
                    )
                }
            ),
        )
