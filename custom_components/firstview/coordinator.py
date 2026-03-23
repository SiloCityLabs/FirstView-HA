"""Coordinator for FirstView polling and live state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import FirstViewClient
from .ws import FirstViewWebsocketManager

_LOGGER = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":", 1)
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
        self._last_daily_date: str | None = None
        self._last_hourly: datetime | None = None
        self._last_ws_event: dict[str, Any] | None = None
        self._socket_manual_enabled: bool = True
        self._last_student_vehicle_map: dict[str, str] = {}
        self._last_vehicle_location: dict[str, dict[str, Any]] = {}
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
        return _collect_trip_ids(trips), _collect_vehicle_ids(trips)

    async def _async_update_data(self) -> dict[str, Any]:
        data = self.data or {}
        now = dt_util.now()
        today = now.date().isoformat()

        if self._last_daily_date != today:
            students_data = await self.client.async_get_students()
            trips_data = await self.client.async_get_trips()
            data["students"] = students_data.get("items", students_data if isinstance(students_data, list) else [])
            data["trips"] = trips_data.get("items", trips_data if isinstance(trips_data, list) else [])
            self._last_daily_date = today
            # On first daily pull, populate trip progress immediately to avoid empty startup entities.
            trip_ids = _collect_trip_ids(data["trips"])
            if trip_ids and not data.get("trips_progress"):
                data["trips_progress"] = (
                    await self.client.async_get_trips_progress(trip_ids)
                ).get("items", [])

        if not self._last_hourly or now - self._last_hourly >= timedelta(hours=1):
            trip_ids, vehicle_ids = self._subscriptions()
            data["trips_progress"] = (await self.client.async_get_trips_progress(trip_ids)).get("items", [])
            notifications = await self.client.async_get_notifications(skip=0, limit=50)
            data["notifications"] = notifications.get("items", notifications if isinstance(notifications, list) else [])
            data["notifications_counter"] = await self.client.async_get_notifications_counter()
            recent = await self.client.async_get_recent_location(vehicle_ids)
            data["recent_location"] = recent
            for event in recent:
                vid = event.get("vehicleId")
                if isinstance(vid, str) and vid:
                    self._last_vehicle_location[vid] = event
            self._last_hourly = now

        data["websocket_connected"] = self._ws.connected
        data["socket_enabled"] = self._socket_manual_enabled
        data["last_ws_event"] = self._last_ws_event
        current_map = _build_student_vehicle_map(data.get("trips", []))
        self._last_student_vehicle_map.update(current_map)
        data["student_vehicle_map"] = dict(self._last_student_vehicle_map)
        data["vehicle_location_map"] = dict(self._last_vehicle_location)
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


def _build_student_vehicle_map(trips: list[dict[str, Any]]) -> dict[str, str]:
    """Best-effort map student_id -> vehicle_id from trip payloads."""
    out: dict[str, str] = {}
    for trip in trips:
        vehicle = trip.get("vehicleId")
        if not vehicle:
            continue
        for f in trip.get("followedStudents", []) or []:
            sid = f.get("id")
            if sid is not None:
                out[str(sid)] = vehicle
    return out


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


def _collect_vehicle_ids(trips: list[dict[str, Any]]) -> list[str]:
    ids: set[str] = set()
    for trip in trips:
        for key in ("vehicleId", "originVehicleId", "previousVehicleId"):
            val = trip.get(key)
            if isinstance(val, str) and val:
                ids.add(val)
    return sorted(ids)
