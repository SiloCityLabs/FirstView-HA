"""Device tracker platform for FirstView student bus positions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FirstViewCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FirstViewCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def add_missing() -> None:
        data = coordinator.data or {}
        students = data.get("students", [])
        new_entities = []
        for student in students:
            sid = student.get("id")
            if sid is None:
                continue
            sid_str = str(sid)
            if sid_str in known:
                continue
            known.add(sid_str)
            new_entities.append(FirstViewStudentTracker(coordinator, entry.entry_id, student))
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
        return {
            "student_id": self._sid,
            "vehicle_id": event.get("vehicleId"),
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
