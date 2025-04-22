"""Constants for ChargePoint."""

from homeassistant.const import Platform

# Base component constants
NAME = "ChargePoint"
DOMAIN = "chargepoint"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.9.0"
ATTRIBUTION = "Data provided by https://www.chargepoint.com"
ISSUE_URL = "https://github.com/mbillow/ha-chargepoint/issues"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.BUTTON]


# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

TOKEN_FILE_NAME = "chargepoint_session.json"
CHARGER_SESSION_STATE_IN_USE = "IN_USE"

# Account Data
ACCT_INFO = "account_information"
ACCT_CRG_STATUS = "charging_status"
ACCT_SESSION = "charging_session"
ACCT_HOME_CRGS = "home_chargers"

# Internal
DATA_CLIENT = "chargepoint_client"
DATA_COORDINATOR = "coordinator"
DATA_CHARGERS = "home_chargers"
EXCEPTION_WARNING_MSG = "ChargePoint returned an exception, you might want to " + \
                        "double check the charging status in the app."

# Defaults
DEFAULT_NAME = "chargepoint"


def getVersion() -> str:
    