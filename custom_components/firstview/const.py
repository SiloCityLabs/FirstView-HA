"""Constants for FirstView integration."""

DOMAIN = "firstview"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_AM_ENABLED = "am_enabled"
CONF_AM_START = "am_start"
CONF_AM_END = "am_end"
CONF_PM_ENABLED = "pm_enabled"
CONF_PM_START = "pm_start"
CONF_PM_END = "pm_end"
CONF_DAY_M = "day_m"
CONF_DAY_T = "day_t"
CONF_DAY_W = "day_w"
CONF_DAY_R = "day_r"
CONF_DAY_F = "day_f"
CONF_DAY_SA = "day_sa"
CONF_DAY_SU = "day_su"

DEFAULT_AM_ENABLED = True
DEFAULT_AM_START = "06:00"
DEFAULT_AM_END = "08:00"
DEFAULT_PM_ENABLED = True
DEFAULT_PM_START = "13:00"
DEFAULT_PM_END = "15:00"
DEFAULT_DAY_M = True
DEFAULT_DAY_T = True
DEFAULT_DAY_W = True
DEFAULT_DAY_R = True
DEFAULT_DAY_F = True
DEFAULT_DAY_SA = False
DEFAULT_DAY_SU = False

MAX_WINDOW_MINUTES = 120

COGNITO_USER_POOL_ID = "us-east-1_rGFbOE8vH"
COGNITO_CLIENT_ID = "7n0v07n3eja2au8qhkbbnc009r"
COGNITO_REGION = "us-east-1"

DASHBOARD_BASE = "https://dashboard.myfirstview.com"
WS_BASE = "wss://wbsckt.myfirstview.com"

PLATFORMS = ["sensor", "device_tracker"]
