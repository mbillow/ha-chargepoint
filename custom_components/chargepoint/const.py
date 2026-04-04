"""Constants for ChargePoint."""

from homeassistant.const import Platform

# Base component constants
NAME = "ChargePoint"
DOMAIN = "chargepoint"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.4.0"
ATTRIBUTION = "Data provided by https://www.chargepoint.com"
ISSUE_URL = "https://github.com/mbillow/ha-chargepoint/issues"

# Platforms
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


# Configuration and options
CONF_USERNAME = "username"
CONF_COULOMB_TOKEN = "coulomb_token"
OPTION_POLL_INTERVAL = "poll_interval"
OPTION_PUBLIC_CHARGERS = "public_chargers"

POLL_INTERVAL_OPTIONS = {
    "30 seconds": 30,
    "1 minute": 60,
    "3 minutes": 180,
    "5 minutes": 300,
    "10 minutes": 600,
}
POLL_INTERVAL_DEFAULT = 180


TOKEN_FILE_NAME = "chargepoint_session.json"
CHARGER_SESSION_STATE_IN_USE = "IN_USE"

# Account Data
ACCT_INFO = "account_information"
ACCT_CRG_STATUS = "charging_status"
ACCT_SESSION = "charging_session"
ACCT_HOME_CRGS = "home_chargers"
ACCT_PUBLIC_STATIONS = "public_stations"

# Per-charger data sub-keys
ACCT_CHARGER_STATUS = "status"
ACCT_CHARGER_TECH_INFO = "tech_info"
ACCT_CHARGER_CONFIG = "config"
ACCT_CHARGER_SCHEDULE = "schedule"

# Public station entity/device identifier prefix
PUBLIC_STATION_ID_PREFIX = "public_"

# Internal
DATA_CLIENT = "chargepoint_client"
DATA_COORDINATOR = "coordinator"
EXCEPTION_WARNING_MSG = (
    "ChargePoint returned an exception, you might want to "
    + "double check the charging status in the app."
)

# Defaults
DEFAULT_NAME = "chargepoint"
