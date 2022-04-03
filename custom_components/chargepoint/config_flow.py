"""Adds config flow for ChargePoint."""
import logging
from collections import OrderedDict
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_ACCESS_TOKEN
from python_chargepoint import ChargePoint

from python_chargepoint.exceptions import (
    ChargePointLoginError,
    ChargePointCommunicationException,
)

from . import persist_session_token
from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


class ChargePointBaseFlowHandler(config_entries.ConfigFlow):
    async def _test_credentials(self, username, password) -> Optional[str]:
        """Return true if credentials is valid."""
        try:
            _LOGGER.error("Attempting to authenticate with chargepoint")
            client = await self.hass.async_add_executor_job(
                ChargePoint, username, password
            )
            _LOGGER.error("New session token: %s", client.session_token)
            persist_session_token()
            return client.session_token
        except ChargePointLoginError:
            return
        except ChargePointCommunicationException:
            _LOGGER.exception("Error testing provided credentials!")

    # Options Flow
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class ChargePointFlowHandler(ChargePointBaseFlowHandler, domain=DOMAIN):
    """Config flow for ChargePoint."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._data = {}
        self._errors = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            # self._data.update(user_input)
            session_token = await self._test_credentials(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if session_token:
                user_input[CONF_ACCESS_TOKEN] = session_token
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            else:
                self._errors["base"] = "invalid_credentials"

            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit creds."""
        if not user_input:
            user_input = {}

        data_schema = OrderedDict()
        data_schema[vol.Required("username", default="", description="Username")] = str
        data_schema[vol.Required("password", default="", description="Password")] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )


class OptionsFlowHandler(ChargePointBaseFlowHandler, config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self._errors = {}
        self._data = {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data = user_input
            return await self._update_options()

        data_schema = OrderedDict()
        data_schema[
            vol.Required("username", default=self.config_entry.data.get(CONF_USERNAME))
        ] = str
        data_schema[vol.Required("password", default="")] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

    async def _update_options(self):
        """Update config entry options."""
        session_token = await self._test_credentials(
            self._data[CONF_USERNAME],
            self._data[CONF_PASSWORD],
        )
        if session_token:
            self._data[CONF_ACCESS_TOKEN] = session_token
            return self.async_create_entry(
                title=self.config_entry.data.get(CONF_USERNAME), data=self._data
            )
        else:
            self._errors["base"] = "invalid_credentials"
            return await self.async_step_user()
