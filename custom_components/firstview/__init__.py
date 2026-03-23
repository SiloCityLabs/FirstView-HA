"""FirstView integration setup."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
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
)
from .coordinator import FirstViewConfig, FirstViewCoordinator, _parse_hhmm

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from config entry."""
    merged = {**entry.data, **entry.options}
    data = {
        CONF_EMAIL: merged[CONF_EMAIL],
        CONF_PASSWORD: merged[CONF_PASSWORD],
        CONF_AM_ENABLED: merged.get(CONF_AM_ENABLED, DEFAULT_AM_ENABLED),
        CONF_AM_START: merged.get(CONF_AM_START, DEFAULT_AM_START),
        CONF_AM_END: merged.get(CONF_AM_END, DEFAULT_AM_END),
        CONF_PM_ENABLED: merged.get(CONF_PM_ENABLED, DEFAULT_PM_ENABLED),
        CONF_PM_START: merged.get(CONF_PM_START, DEFAULT_PM_START),
        CONF_PM_END: merged.get(CONF_PM_END, DEFAULT_PM_END),
        CONF_DAY_M: merged.get(CONF_DAY_M, DEFAULT_DAY_M),
        CONF_DAY_T: merged.get(CONF_DAY_T, DEFAULT_DAY_T),
        CONF_DAY_W: merged.get(CONF_DAY_W, DEFAULT_DAY_W),
        CONF_DAY_R: merged.get(CONF_DAY_R, DEFAULT_DAY_R),
        CONF_DAY_F: merged.get(CONF_DAY_F, DEFAULT_DAY_F),
        CONF_DAY_SA: merged.get(CONF_DAY_SA, DEFAULT_DAY_SA),
        CONF_DAY_SU: merged.get(CONF_DAY_SU, DEFAULT_DAY_SU),
    }
    session = async_get_clientsession(hass)
    client = FirstViewClient(
        hass,
        session,
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
    )
    cfg = FirstViewConfig(
        am_enabled=bool(data[CONF_AM_ENABLED]),
        am_start=_parse_hhmm(data[CONF_AM_START]),
        am_end=_parse_hhmm(data[CONF_AM_END]),
        pm_enabled=bool(data[CONF_PM_ENABLED]),
        pm_start=_parse_hhmm(data[CONF_PM_START]),
        pm_end=_parse_hhmm(data[CONF_PM_END]),
        day_m=bool(data[CONF_DAY_M]),
        day_t=bool(data[CONF_DAY_T]),
        day_w=bool(data[CONF_DAY_W]),
        day_r=bool(data[CONF_DAY_R]),
        day_f=bool(data[CONF_DAY_F]),
        day_sa=bool(data[CONF_DAY_SA]),
        day_su=bool(data[CONF_DAY_SU]),
    )
    coordinator = FirstViewCoordinator(hass, client, cfg)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start()

    entry.async_on_unload(entry.add_update_listener(async_update_options_listener))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: FirstViewCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def async_update_options_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
