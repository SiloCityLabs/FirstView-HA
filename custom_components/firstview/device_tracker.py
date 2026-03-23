"""Device tracker platform for FirstView student bus positions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
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
    known_students: set[str] = set()
    known_buses: set[str] = set()

    @callback
    def add_missing() -> None:
        data = coordinator.data or {}
        students = data.get("students", [])
        recent = data.get("recent_location", [])
        vehicle_map = data.get("vehicle_location_map", {})
        new_entities = []
        for student in students:
            sid = student.get("id")
            if sid is None:
                continue
            sid_str = str(sid)
            if sid_str in known_students:
                continue
            known_students.add(sid_str)
            new_entities.append(FirstViewStudentTracker(coordinator, entry.entry_id, student))
        for event in recent:
            vid = event.get("vehicleId")
            if isinstance(vid, str) and vid and vid not in known_buses:
                known_buses.add(vid)
                new_entities.append(FirstViewBusTracker(coordinator, entry.entry_id, vid))
        for vid in vehicle_map:
            if isinstance(vid, str) and vid and vid not in known_buses:
                known_buses.add(vid)
                new_entities.append(FirstViewBusTracker(coordinator, entry.entry_id, vid))
        if new_entities:
            async_add_entities(new_entities)

    add_missing()
    entry.async_on_unload(coordinator.async_add_listener(add_missing))


class FirstViewStudentTracker(CoordinatorEntity[FirstViewCoordinator], TrackerEntity):
    """Tracker entity per student that follows mapped vehicle location."""

    _attr_has_entity_name = True
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str, student: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._student = student
        self._sid = str(student.get("id"))
        self._attr_unique_id = f"{entry_id}_student_{self._sid}"
        name = student.get("name") or f"Student {self._sid}"
        self._attr_name = f"{name} Bus"

    def _vehicle_event(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        mapping: dict[str, str] = data.get("student_vehicle_map", {})
        vehicle = mapping.get(self._sid)
        if not vehicle:
            return None
        for event in data.get("recent_location", []):
            if event.get("vehicleId") == vehicle:
                return event
        fallback_map: dict[str, dict[str, Any]] = data.get("vehicle_location_map", {})
        return fallback_map.get(vehicle)

    @property
    def device_info(self) -> DeviceInfo:
        mapping: dict[str, str] = (self.coordinator.data or {}).get("student_vehicle_map", {})
        vehicle = mapping.get(self._sid)
        if vehicle:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{self._entry_id}_student_{self._sid}")},
                name=self._attr_name,
                manufacturer="FirstView",
                model="Student Tracker",
                via_device=(DOMAIN, f"{self._entry_id}_bus_{vehicle}"),
            )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_student_{self._sid}")},
            name=self._attr_name,
            manufacturer="FirstView",
            model="Student Tracker",
        )

    @property
    def latitude(self):
        event = self._vehicle_event()
        return event.get("latitude") if event else None

    @property
    def longitude(self):
        event = self._vehicle_event()
        return event.get("longitude") if event else None

    @property
    def extra_state_attributes(self):
        event = self._vehicle_event() or {}
        status = event.get("status") if isinstance(event.get("status"), dict) else {}
        confidence_map: dict[str, str] = (self.coordinator.data or {}).get(
            "student_vehicle_confidence", {}
        )
        return {
            "student_id": self._sid,
            "vehicle_id": event.get("vehicleId"),
            "mapping_confidence": confidence_map.get(self._sid, "low"),
            "device_id": event.get("deviceId"),
            "location_id": event.get("locationId"),
            "event_type": event.get("eventType"),
            "event_timestamp": event.get("eventTimestamp"),
            "speed": event.get("speed"),
            "heading": event.get("heading"),
            "odometer_reading": event.get("odometerReading"),
            "ignition": status.get("ignition"),
            "motion": status.get("motion"),
            "door": status.get("door"),
        }


class FirstViewBusTracker(CoordinatorEntity[FirstViewCoordinator], TrackerEntity):
    """Tracker entity per active vehicle for map + diagnostics."""

    _attr_has_entity_name = True
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str, vehicle_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vehicle_id = vehicle_id
        self._attr_unique_id = f"{entry_id}_bus_{vehicle_id}"
        self._attr_name = f"Bus {vehicle_id}"

    def _event(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        for event in data.get("recent_location", []):
            if event.get("vehicleId") == self._vehicle_id:
                return event
        return data.get("vehicle_location_map", {}).get(self._vehicle_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_bus_{self._vehicle_id}")},
            name=f"Bus {self._vehicle_id}",
            manufacturer="FirstView",
            model="Vehicle Tracker",
        )

    @property
    def latitude(self):
        return self._event().get("latitude")

    @property
    def longitude(self):
        return self._event().get("longitude")

    @property
    def extra_state_attributes(self):
        event = self._event()
        status = event.get("status") if isinstance(event.get("status"), dict) else {}
        ws_diag = (self.coordinator.data or {}).get("ws_diagnostics", {})
        event_age = _event_age_seconds(event.get("eventTimestamp"))
        return {
            "vehicle_id": self._vehicle_id,
            "event_timestamp": event.get("eventTimestamp"),
            "event_age_seconds": event_age,
            "event_type": event.get("eventType"),
            "speed": event.get("speed"),
            "heading": event.get("heading"),
            "odometer_reading": event.get("odometerReading"),
            "ignition": status.get("ignition"),
            "motion": status.get("motion"),
            "door": status.get("door"),
            "ws_reconnect_count": ws_diag.get("reconnect_count"),
            "ws_last_lag_seconds": ws_diag.get("last_lag_seconds"),
            "ws_last_error": ws_diag.get("last_error"),
        }


def _event_age_seconds(timestamp: str | None) -> float | None:
    if not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return None
    return max(0.0, (dt_util.utcnow().replace(tzinfo=parsed.tzinfo) - parsed).total_seconds())
