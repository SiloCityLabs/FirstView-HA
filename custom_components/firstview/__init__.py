"""FirstView integration setup."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FirstViewClient
from .const import (
    CONF_AM_END,
    CONF_AM_START,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PM_END,
    CONF_PM_START,
    DOMAIN,
)
from .coordinator import FirstViewConfig, FirstViewCoordinator, _parse_hhmm

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from config entry."""
    data = {**entry.data, **entry.options}
    session = async_get_clientsession(hass)
    client = FirstViewClient(
        hass,
        session,
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
    )
    cfg = FirstViewConfig(
        am_start=_parse_hhmm(data[CONF_AM_START]),
        am_end=_parse_hhmm(data[CONF_AM_END]),
        pm_start=_parse_hhmm(data[CONF_PM_START]),
        pm_end=_parse_hhmm(data[CONF_PM_END]),
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
