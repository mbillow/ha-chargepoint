"""Constants for ChargePoint."""

from homeassistant.const import Platform

# Base component constants
NAME = "ChargePoint"
DOMAIN = "chargepoint"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.3.0"
ATTRIBUTION = "Data provided by https://www.chargepoint.com"
ISSUE_URL = "https://github.com/mbillow/ha-chargepoint/issues"

# Platforms
PLATFORMS = [Platform.SENSOR]


# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

TOKEN_FILE_NAME = "chargepoint_session.json"

# Account Data
ACCT_INFO = "account_information"
ACCT_CRG_STATUS = "charging_status"
ACCT_SESSION = "charging_session"
ACCT_HOME_CRGS = "home_chargers"

# Internal
DATA_CLIENT = "chargepoint_client"
DATA_COORDINATOR = "coordinator"
DATA_CHARGERS = "home_chargers"

# Defaults
DEFAULT_NAME = "chargepoint"
