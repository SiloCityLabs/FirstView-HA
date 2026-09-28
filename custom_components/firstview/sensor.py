"""Sensor platform for FirstView."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    known_students: set[str] = set()

    @callback
    def add_student_stop_sensors() -> None:
        data = coordinator.data or {}
        students_by_id: dict[str, dict[str, Any]] = {}
        for student in data.get("students") or []:
            if isinstance(student, dict) and student.get("id") is not None:
                students_by_id[str(student["id"])] = student
        for sid, stats in (data.get("student_stops") or {}).items():
            students_by_id.setdefault(sid, {"id": sid, "firstName": stats.get("student_name")})
        new_entities: list[SensorEntity] = []
        for sid, student in students_by_id.items():
            if sid in known_students:
                continue
            known_students.add(sid)
            for metric in ("current_stop", "stops_left", "total_stops"):
                new_entities.append(
                    FirstViewStudentStopSensor(coordinator, entry.entry_id, student, metric)
                )
        if new_entities:
            async_add_entities(new_entities)

    add_student_stop_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_student_stop_sensors))


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


_STOP_METRICS = {
    "current_stop": ("Current Stop", "mdi:bus-stop"),
    "stops_left": ("Stops Left", "mdi:bus-clock"),
    "total_stops": ("Total Stops", "mdi:format-list-numbered"),
}


class FirstViewStudentStopSensor(CoordinatorEntity[FirstViewCoordinator], SensorEntity):
    """Stop progress for one student until the bus reaches their house."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: FirstViewCoordinator,
        entry_id: str,
        student: dict[str, Any],
        metric: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._sid = str(student.get("id"))
        self._metric = metric
        name, icon = _STOP_METRICS[metric]
        self._attr_unique_id = f"{entry_id}_student_{self._sid}_{metric}"
        self._attr_name = name
        self._attr_icon = icon
        label = student.get("firstName") or student.get("name") or f"Student {self._sid}"
        self._device_name = f"{label} Bus"

    def _stats(self) -> dict[str, Any]:
        return ((self.coordinator.data or {}).get("student_stops") or {}).get(self._sid) or {}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_student_{self._sid}")},
            name=self._device_name,
            manufacturer="FirstView",
            model="Student Tracker",
        )

    @property
    def native_value(self):
        value = self._stats().get(self._metric)
        return value if isinstance(value, int) else None

    @property
    def extra_state_attributes(self):
        stats = self._stats()
        return {
            "student": stats.get("student_name") or self._device_name.removesuffix(" Bus"),
            "route": stats.get("route"),
            "direction": stats.get("direction"),
            "target_stop": stats.get("target_stop"),
            "target_kind": stats.get("target_kind"),
            "stop_name": stats.get("stop_name"),
            "trip_status": stats.get("trip_status"),
        }


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
    return max(0.0, (dt_util.utcnow().replace(tzinfo=dt.tzinfo) - dt).total_seconds())
