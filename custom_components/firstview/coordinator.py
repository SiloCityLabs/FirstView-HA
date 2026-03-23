"""Coordinator for FirstView polling and live state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import FirstViewAuthError, FirstViewClient
from .ws import FirstViewWebsocketManager

_LOGGER = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time:
    parts = value.split(":")
    hh, mm = parts[0], parts[1]
    return time(hour=int(hh), minute=int(mm))


@dataclass
class FirstViewConfig:
    am_enabled: bool
    am_start: time
    am_end: time
    pm_enabled: bool
    pm_start: time
    pm_end: time
    day_m: bool
    day_t: bool
    day_w: bool
    day_r: bool
    day_f: bool
    day_sa: bool
    day_su: bool
    daily_interval_hours: int
    hourly_interval_minutes: int


class FirstViewCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage periodic API pulls + websocket state."""

    def __init__(self, hass, client: FirstViewClient, cfg: FirstViewConfig) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="FirstView",
            update_interval=timedelta(minutes=5),
        )
        self.client = client
        self.cfg = cfg
        self._last_daily: datetime | None = None
        self._last_hourly: datetime | None = None
        self._last_ws_event: dict[str, Any] | None = None
        self._socket_manual_enabled: bool = True
        self._last_student_vehicle_map: dict[str, str] = {}
        self._last_vehicle_location: dict[str, dict[str, Any]] = {}
        self._last_student_vehicle_confidence: dict[str, str] = {}
        self._last_good_data: dict[str, Any] = {}
        self._auth_notification_id = "firstview_auth_issue"
        self._selected_notification_id: str | None = None
        self._selected_notification_status: str = "READ"
        self._ws = FirstViewWebsocketManager(
            client._session,  # intentional internal access inside integration package
            client,
            self.in_live_window,
            self._subscriptions,
            self._on_ws_event,
        )

    async def async_start(self) -> None:
        self._ws.start()

    async def async_stop(self) -> None:
        await self._ws.stop()

    def in_live_window(self) -> bool:
        if not self._socket_manual_enabled:
            return False
        now_dt = dt_util.now()
        now = now_dt.time()
        wd = now_dt.weekday()  # Mon=0..Sun=6
        enabled_by_day = {
            0: self.cfg.day_m,
            1: self.cfg.day_t,
            2: self.cfg.day_w,
            3: self.cfg.day_r,  # R = Thursday
            4: self.cfg.day_f,
            5: self.cfg.day_sa,
            6: self.cfg.day_su,
        }
        if not enabled_by_day.get(wd, False):
            return False
        am_ok = self.cfg.am_enabled and (self.cfg.am_start <= now <= self.cfg.am_end)
        pm_ok = self.cfg.pm_enabled and (self.cfg.pm_start <= now <= self.cfg.pm_end)
        return am_ok or pm_ok

    def _on_ws_event(self, payload: dict[str, Any]) -> None:
        self._last_ws_event = payload
        pld = payload.get("payload") if isinstance(payload, dict) else None
        if isinstance(pld, dict):
            vid = pld.get("vehicleId")
            if isinstance(vid, str) and vid:
                self._last_vehicle_location[vid] = pld
        self.hass.bus.async_fire("firstview_live_event", {"payload": payload})

    def _subscriptions(self) -> tuple[list[int], list[str]]:
        trips = self.data.get("trips", []) if self.data else []
        recent = self.data.get("recent_location", []) if self.data else []
        progress = self.data.get("trips_progress", []) if self.data else []
        return _collect_trip_ids(trips), _collect_vehicle_ids(trips, recent, progress)

    async def _notify_auth_issue(self, message: str) -> None:
        persistent_notification.async_create(
            self.hass,
            message=message,
            title="FirstView Authentication Issue",
            notification_id=self._auth_notification_id,
        )

    async def _clear_auth_issue(self) -> None:
        persistent_notification.async_dismiss(self.hass, self._auth_notification_id)

    async def _async_update_data(self) -> dict[str, Any]:
        data = dict(self.data or self._last_good_data or {})
        now = dt_util.now()
        try:
            if (
                not self._last_daily
                or now - self._last_daily >= timedelta(hours=self.cfg.daily_interval_hours)
                or not data.get("students")
                or not data.get("trips")
            ):
                students_data = await self.client.async_get_students()
                trips_data = await self.client.async_get_trips()
                data["students"] = students_data.get(
                    "items", students_data if isinstance(students_data, list) else []
                )
                data["trips"] = trips_data.get(
                    "items", trips_data if isinstance(trips_data, list) else []
                )
                self._last_daily = now
                # On first daily pull, populate trip progress immediately to avoid empty startup entities.
                trip_ids = _collect_trip_ids(data["trips"])
                if trip_ids and not data.get("trips_progress"):
                    data["trips_progress"] = (
                        await self.client.async_get_trips_progress(trip_ids)
                    ).get("items", [])

            if not self._last_hourly or now - self._last_hourly >= timedelta(
                minutes=self.cfg.hourly_interval_minutes
            ):
                trip_ids, vehicle_ids = self._subscriptions()
                data["trips_progress"] = (
                    await self.client.async_get_trips_progress(trip_ids)
                ).get("items", [])
                notifications = await self.client.async_get_notifications(skip=0, limit=50)
                data["notifications"] = notifications.get(
                    "items", notifications if isinstance(notifications, list) else []
                )
                data["notifications_counter"] = await self.client.async_get_notifications_counter()
                recent = await self.client.async_get_recent_location(vehicle_ids)
                data["recent_location"] = recent
                for event in recent:
                    vid = event.get("vehicleId")
                    if isinstance(vid, str) and vid:
                        self._last_vehicle_location[vid] = event
                self._last_hourly = now
            await self._clear_auth_issue()
        except FirstViewAuthError as err:
            _LOGGER.warning("FirstView auth error, using last-good data: %s", err)
            await self._notify_auth_issue(
                "FirstView authentication failed repeatedly. Integration is serving "
                "last known data and will retry automatically."
            )
            data = dict(self._last_good_data or data)
        except Exception as err:
            _LOGGER.warning("FirstView transient update failure, using cache: %s", err)
            data = dict(self._last_good_data or data)

        data["websocket_connected"] = self._ws.connected
        data["socket_enabled"] = self._socket_manual_enabled
        data["last_ws_event"] = self._last_ws_event
        data["ws_diagnostics"] = self._ws.diagnostics
        current_map, current_conf = _build_student_vehicle_map(
            data.get("trips", []), data.get("trips_progress", [])
        )
        self._last_student_vehicle_map.update(current_map)
        self._last_student_vehicle_confidence.update(current_conf)
        data["student_vehicle_map"] = dict(self._last_student_vehicle_map)
        data["student_vehicle_confidence"] = dict(self._last_student_vehicle_confidence)
        data["vehicle_location_map"] = dict(self._last_vehicle_location)
        notification_ids = [
            str(item.get("id"))
            for item in data.get("notifications", [])
            if isinstance(item, dict) and item.get("id") is not None
        ]
        if not self._selected_notification_id and notification_ids:
            self._selected_notification_id = notification_ids[0]
        if self._selected_notification_id and self._selected_notification_id not in notification_ids:
            self._selected_notification_id = notification_ids[0] if notification_ids else None
        data["notification_ids"] = notification_ids
        data["selected_notification_id"] = self._selected_notification_id
        data["selected_notification_status"] = self._selected_notification_status
        self._last_good_data = dict(data)
        return data

    async def async_set_socket_enabled(self, enabled: bool) -> None:
        """Enable/disable websocket regardless of schedule windows."""
        self._socket_manual_enabled = bool(enabled)
        if not self._socket_manual_enabled:
            await self._ws.stop()
        else:
            self._ws.start()
        self.async_set_updated_data(dict(self.data or {}, socket_enabled=self._socket_manual_enabled))

    async def async_toggle_socket_enabled(self) -> None:
        await self.async_set_socket_enabled(not self._socket_manual_enabled)

    async def async_set_selected_notification_id(self, notification_id: str | None) -> None:
        self._selected_notification_id = notification_id
        self.async_set_updated_data(dict(self.data or {}))

    async def async_set_selected_notification_status(self, status: str) -> None:
        self._selected_notification_status = status
        self.async_set_updated_data(dict(self.data or {}))

    async def async_mark_all_notifications_read(self) -> None:
        await self.client.async_mark_all_notifications_read()
        await self.async_request_refresh()

    async def async_update_selected_notification_status(self) -> None:
        if not self._selected_notification_id:
            raise RuntimeError("No notification selected")
        await self.client.async_set_notification_status(
            self._selected_notification_id, self._selected_notification_status
        )
        await self.async_request_refresh()

    async def async_delete_selected_notification(self) -> None:
        if not self._selected_notification_id:
            raise RuntimeError("No notification selected")
        await self.client.async_delete_notification(self._selected_notification_id)
        await self.async_request_refresh()

    async def async_delete_all_notifications(self) -> None:
        await self.client.async_delete_all_notifications()
        await self.async_request_refresh()


def _build_student_vehicle_map(
    trips: list[dict[str, Any]], trips_progress: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, str]]:
    """Best-effort map student_id -> vehicle_id from trip payloads."""
    out: dict[str, str] = {}
    confidence: dict[str, str] = {}
    trip_vehicle_map: dict[int, str] = {}
    for trip in trips:
        vehicle = trip.get("vehicleId") or trip.get("originVehicleId")
        trip_id = trip.get("id")
        if isinstance(trip_id, int) and isinstance(vehicle, str) and vehicle:
            trip_vehicle_map[trip_id] = vehicle
        for f in trip.get("followedStudents", []) or []:
            sid = f.get("id")
            if sid is not None and isinstance(vehicle, str) and vehicle:
                out[str(sid)] = vehicle
                confidence[str(sid)] = "high"
    for progress in trips_progress or []:
        tid = progress.get("tripId") or progress.get("id")
        if not isinstance(tid, int):
            continue
        vehicle = progress.get("vehicleId") or trip_vehicle_map.get(tid)
        if not isinstance(vehicle, str) or not vehicle:
            continue
        students = progress.get("followedStudents", []) or []
        for student in students:
            sid = student.get("id")
            sid_str = str(sid) if sid is not None else None
            if not sid_str or sid_str in out:
                continue
            out[sid_str] = vehicle
            confidence[sid_str] = "medium"
    return out, confidence


def _collect_trip_ids(trips: list[dict[str, Any]]) -> list[int]:
    ids: set[int] = set()
    for trip in trips:
        for key in ("id", "tripId", "originTripId"):
            val = trip.get(key)
            if isinstance(val, int):
                ids.add(val)
        for run in trip.get("runs", []) or []:
            for key in ("tripId", "originTripId", "id"):
                val = run.get(key)
                if isinstance(val, int):
                    ids.add(val)
    return sorted(ids)


def _collect_vehicle_ids(
    trips: list[dict[str, Any]],
    recent_location: list[dict[str, Any]] | None = None,
    trips_progress: list[dict[str, Any]] | None = None,
) -> list[str]:
    ids: set[str] = set()
    for trip in trips:
        for key in ("vehicleId", "originVehicleId", "previousVehicleId"):
            val = trip.get(key)
            if isinstance(val, str) and val:
                ids.add(val)
    for event in recent_location or []:
        val = event.get("vehicleId")
        if isinstance(val, str) and val:
            ids.add(val)
    for progress in trips_progress or []:
        val = progress.get("vehicleId")
        if isinstance(val, str) and val:
            ids.add(val)
    return sorted(ids)
