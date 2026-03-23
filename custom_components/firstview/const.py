"""Constants for FirstView integration."""

DOMAIN = "firstview"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_AM_START = "am_start"
CONF_AM_END = "am_end"
CONF_PM_START = "pm_start"
CONF_PM_END = "pm_end"

DEFAULT_AM_START = "06:00"
DEFAULT_AM_END = "08:00"
DEFAULT_PM_START = "13:00"
DEFAULT_PM_END = "15:00"

MAX_WINDOW_MINUTES = 120

COGNITO_USER_POOL_ID = "us-east-1_rGFbOE8vH"
COGNITO_CLIENT_ID = "7n0v07n3eja2au8qhkbbnc009r"
COGNITO_REGION = "us-east-1"

DASHBOARD_BASE = "https://dashboard.myfirstview.com"
WS_BASE = "wss://wbsckt.myfirstview.com"

PLATFORMS = ["sensor", "device_tracker"]
