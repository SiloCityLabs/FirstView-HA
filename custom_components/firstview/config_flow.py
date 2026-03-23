"""Config flow for FirstView."""

from __future__ import annotations

from datetime import datetime
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FirstViewClient
from .const import (
    CONF_AM_ENABLED,
    CONF_AM_END,
    CONF_AM_START,
    CONF_DAY_F,
    CONF_DAY_M,
    CONF_DAY_R,
    CONF_DAY_SA,
    CONF_DAY_SU,
    CONF_DAY_T,
    CONF_DAY_W,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PM_ENABLED,
    CONF_PM_END,
    CONF_PM_START,
    DEFAULT_AM_ENABLED,
    DEFAULT_AM_END,
    DEFAULT_AM_START,
    DEFAULT_DAY_F,
    DEFAULT_DAY_M,
    DEFAULT_DAY_R,
    DEFAULT_DAY_SA,
    DEFAULT_DAY_SU,
    DEFAULT_DAY_T,
    DEFAULT_DAY_W,
    DEFAULT_PM_ENABLED,
    DEFAULT_PM_END,
    DEFAULT_PM_START,
    DOMAIN,
    MAX_WINDOW_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _to_minutes(value: str) -> int:
    t = datetime.strptime(value, "%H:%M")
    return t.hour * 60 + t.minute


def _window_valid(start: str, end: str) -> bool:
    s = _to_minutes(start)
    e = _to_minutes(end)
    if e <= s:
        return False
    return (e - s) <= MAX_WINDOW_MINUTES


class FirstViewConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """FirstView config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return FirstViewOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_AM_ENABLED] and not _window_valid(
                user_input[CONF_AM_START], user_input[CONF_AM_END]
            ):
                errors["base"] = "am_window_invalid"
            elif user_input[CONF_PM_ENABLED] and not _window_valid(
                user_input[CONF_PM_START], user_input[CONF_PM_END]
            ):
                errors["base"] = "pm_window_invalid"
            elif not any(
                user_input[k]
                for k in (
                    CONF_DAY_M,
                    CONF_DAY_T,
                    CONF_DAY_W,
                    CONF_DAY_R,
                    CONF_DAY_F,
                    CONF_DAY_SA,
                    CONF_DAY_SU,
                )
            ):
                errors["base"] = "no_days_selected"
            else:
                try:
                    session = async_get_clientsession(self.hass)
                    client = FirstViewClient(
                        self.hass,
                        session,
                        email=user_input[CONF_EMAIL],
                        password=user_input[CONF_PASSWORD],
                    )
                    await client.async_ensure_token()
                except Exception as err:
                    _LOGGER.warning("FirstView login failed during setup: %s", err)
                    errors["base"] = "auth_failed"
                else:
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="FirstView", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_AM_ENABLED, default=DEFAULT_AM_ENABLED): bool,
                vol.Required(CONF_AM_START, default=DEFAULT_AM_START): str,
                vol.Required(CONF_AM_END, default=DEFAULT_AM_END): str,
                vol.Required(CONF_PM_ENABLED, default=DEFAULT_PM_ENABLED): bool,
                vol.Required(CONF_PM_START, default=DEFAULT_PM_START): str,
                vol.Required(CONF_PM_END, default=DEFAULT_PM_END): str,
                vol.Required(CONF_DAY_M, default=DEFAULT_DAY_M): bool,
                vol.Required(CONF_DAY_T, default=DEFAULT_DAY_T): bool,
                vol.Required(CONF_DAY_W, default=DEFAULT_DAY_W): bool,
                vol.Required(CONF_DAY_R, default=DEFAULT_DAY_R): bool,
                vol.Required(CONF_DAY_F, default=DEFAULT_DAY_F): bool,
                vol.Required(CONF_DAY_SA, default=DEFAULT_DAY_SA): bool,
                vol.Required(CONF_DAY_SU, default=DEFAULT_DAY_SU): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class FirstViewOptionsFlow(config_entries.OptionsFlow):
    """Options flow for window updates."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_AM_ENABLED] and not _window_valid(
                user_input[CONF_AM_START], user_input[CONF_AM_END]
            ):
                errors["base"] = "am_window_invalid"
            elif user_input[CONF_PM_ENABLED] and not _window_valid(
                user_input[CONF_PM_START], user_input[CONF_PM_END]
            ):
                errors["base"] = "pm_window_invalid"
            elif not any(
                user_input[k]
                for k in (
                    CONF_DAY_M,
                    CONF_DAY_T,
                    CONF_DAY_W,
                    CONF_DAY_R,
                    CONF_DAY_F,
                    CONF_DAY_SA,
                    CONF_DAY_SU,
                )
            ):
                errors["base"] = "no_days_selected"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_AM_ENABLED, default=current.get(CONF_AM_ENABLED, DEFAULT_AM_ENABLED)): bool,
                vol.Required(CONF_AM_START, default=current.get(CONF_AM_START, DEFAULT_AM_START)): str,
                vol.Required(CONF_AM_END, default=current.get(CONF_AM_END, DEFAULT_AM_END)): str,
                vol.Required(CONF_PM_ENABLED, default=current.get(CONF_PM_ENABLED, DEFAULT_PM_ENABLED)): bool,
                vol.Required(CONF_PM_START, default=current.get(CONF_PM_START, DEFAULT_PM_START)): str,
                vol.Required(CONF_PM_END, default=current.get(CONF_PM_END, DEFAULT_PM_END)): str,
                vol.Required(CONF_DAY_M, default=current.get(CONF_DAY_M, DEFAULT_DAY_M)): bool,
                vol.Required(CONF_DAY_T, default=current.get(CONF_DAY_T, DEFAULT_DAY_T)): bool,
                vol.Required(CONF_DAY_W, default=current.get(CONF_DAY_W, DEFAULT_DAY_W)): bool,
                vol.Required(CONF_DAY_R, default=current.get(CONF_DAY_R, DEFAULT_DAY_R)): bool,
                vol.Required(CONF_DAY_F, default=current.get(CONF_DAY_F, DEFAULT_DAY_F)): bool,
                vol.Required(CONF_DAY_SA, default=current.get(CONF_DAY_SA, DEFAULT_DAY_SA)): bool,
                vol.Required(CONF_DAY_SU, default=current.get(CONF_DAY_SU, DEFAULT_DAY_SU)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
