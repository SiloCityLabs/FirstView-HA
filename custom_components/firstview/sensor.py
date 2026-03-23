"""Sensor platform for FirstView."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FirstViewCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FirstViewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FirstViewMetricSensor(coordinator, entry.entry_id, "students_count", "Students", "students"),
            FirstViewMetricSensor(coordinator, entry.entry_id, "trips_count", "Trips", "trips"),
            FirstViewMetricSensor(
                coordinator, entry.entry_id, "notifications_count", "Notifications", "notifications"
            ),
            FirstViewMetricSensor(
                coordinator, entry.entry_id, "recent_locations_count", "Recent Locations", "recent_location"
            ),
            FirstViewWsStatusSensor(coordinator, entry.entry_id),
        ]
    )


class FirstViewMetricSensor(CoordinatorEntity[FirstViewCoordinator], SensorEntity):
    """Simple list-length sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str, key: str, name: str, data_key: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._data_key = data_key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="FirstView",
            manufacturer="FirstView",
            model="Cloud Integration",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self._data_key, [])
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict) and "items" in value and isinstance(value["items"], list):
            return len(value["items"])
        return 0


class FirstViewWsStatusSensor(CoordinatorEntity[FirstViewCoordinator], SensorEntity):
    """Websocket connection status sensor."""

    _attr_has_entity_name = True
    _attr_name = "Websocket Status"

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_ws_status"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="FirstView",
            manufacturer="FirstView",
            model="Cloud Integration",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return "connected" if data.get("websocket_connected") else "disconnected"

    @property
    def extra_state_attributes(self):
        last = (self.coordinator.data or {}).get("last_ws_event")
        data = self.coordinator.data or {}
        ws_diag = data.get("ws_diagnostics", {})
        last_age = _age_seconds(ws_diag.get("last_message_at"))
        return {
            "last_event_type": last.get("type") if isinstance(last, dict) else None,
            "socket_enabled": data.get("socket_enabled", True),
            "last_event_age_seconds": last_age,
            "ws_reconnect_count": ws_diag.get("reconnect_count"),
            "ws_last_lag_seconds": ws_diag.get("last_lag_seconds"),
            "ws_last_error": ws_diag.get("last_error"),
            "ws_last_reconnect_at": ws_diag.get("last_reconnect_at"),
        }


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
    return max(0.0, (dt_util.utcnow().replace(tzinfo=dt.tzinfo) - dt).total_seconds())
