"""Adds config flow for ChargePoint."""

import logging
from collections import OrderedDict
from typing import Any, Mapping, Tuple

import voluptuous as vol
from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    FlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import selector
from python_chargepoint import ChargePoint
from python_chargepoint.exceptions import (
    ChargePointCommunicationException,
    ChargePointLoginError,
)

from .const import (
    DOMAIN,
    OPTION_POLL_INTERVAL,
    POLL_INTERVAL_DEFAULT,
    POLL_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


def _login_schema(username: str = "") -> vol.Schema:
    return vol.Schema(
        OrderedDict(
            [
                (
                    vol.Required(CONF_USERNAME, default=username),
                    str,
                ),
                (vol.Required(CONF_PASSWORD, default=""), str),
            ]
        )
    )


def _options_schema(poll_interval: int | str = POLL_INTERVAL_DEFAULT) -> vol.Schema:
    return vol.Schema(
        OrderedDict(
            [
                (
                    vol.Required(OPTION_POLL_INTERVAL, default=str(poll_interval)),
                    selector(
                        {
                            "select": {
                                "mode": "dropdown",
                                "options": [
                                    {"label": k, "value": str(v)}
                                    for k, v in POLL_INTERVAL_OPTIONS.items()
                                ],
                            }
                        }
                    ),
                ),
            ]
        )
    )


class ChargePointFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for ChargePoint."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self):
        self._reauth_entry: ConfigEntry | None = None

    async def _login(
        self, username: str, password: str
    ) -> Tuple[str | None, str | None]:
        """Return true if credentials is valid."""
        try:
            _LOGGER.info("Attempting to authenticate with chargepoint")
            client = await self.hass.async_add_executor_job(
                ChargePoint, username, password
            )
            return client.session_token, None
        except ChargePointLoginError as exc:
            error_id = exc.response.json().get("errorId")
            if error_id == 9:
                _LOGGER.exception("Invalid credentials for ChargePoint")
                return None, "invalid_credentials"
            elif error_id == 241:
                _LOGGER.exception("ChargePoint Account is locked")
                return None, "account_locked"
            return None, str(exc)
        except ChargePointCommunicationException as exc:
            _LOGGER.exception("Failed to communicate with ChargePoint")
            return None, str(exc)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        username = ""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()

            session_token, error = await self._login(username, password)
            if error is not None:
                errors["base"] = error
            if session_token:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_ACCESS_TOKEN: session_token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_login_schema(username),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Triggered when reauth is needed."""
        entry_id = self.context["entry_id"]
        self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        username = self._reauth_entry.data[CONF_USERNAME]
        errors = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            session_token, error = await self._login(username, password)
            if error is not None:
                errors["base"] = error
            if session_token:
                # Update the existing config entry
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_ACCESS_TOKEN: session_token,
                    },
                )
                # Reload the config entry
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD, default=""): str}),
            description_placeholders={"username": username},
            errors=errors,
        )


class OptionsFlowHandler(OptionsFlow):
    """Handle options flow for ChargePoint."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            poll_interval = int(user_input[OPTION_POLL_INTERVAL])
            if poll_interval not in POLL_INTERVAL_OPTIONS.values():
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(poll_interval),
                    errors={"base": "invalid_poll_interval"},
                )

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={
                    **self.config_entry.options,
                    OPTION_POLL_INTERVAL: poll_interval,
                },
            )
            # Reload the config entry
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_abort(reason="options_successful")

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                self.config_entry.options.get(
                    OPTION_POLL_INTERVAL, POLL_INTERVAL_DEFAULT
                )
            ),
        )
