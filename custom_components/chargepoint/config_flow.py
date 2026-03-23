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

from .const import (
    CONF_COULOMB_TOKEN,
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
                (vol.Required(CONF_USERNAME, default=username), str),
                (vol.Required("password", default=""), str),
            ]
        )
    )


def _reauth_schema() -> vol.Schema:
    return vol.Schema({vol.Required("password", default=""): str})


def _captcha_token_schema() -> vol.Schema:
    return vol.Schema({vol.Required(CONF_COULOMB_TOKEN, default=""): str})


def _options_schema(poll_interval: int | str = POLL_INTERVAL_DEFAULT) -> vol.Schema:
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
            description_placeholders={"captcha_url": self._captcha_url or ""},
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
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
            step_id="init",
            data_schema=_options_schema(
                self.config_entry.options.get(
                    OPTION_POLL_INTERVAL, POLL_INTERVAL_DEFAULT
                )
            ),
        )
