"""WebSocket manager for FirstView live events."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, WSMessage, WSMsgType
from homeassistant.util import dt as dt_util

from .api import FirstViewClient
from .const import WS_BACKOFF_MAX_SECONDS, WS_BACKOFF_MIN_SECONDS, WS_WINDOW_SLEEP_SECONDS

_LOGGER = logging.getLogger(__name__)


class FirstViewWebsocketManager:
    """Manage websocket lifecycle with retries and window gating."""

    def __init__(
        self,
        session: ClientSession,
        client: FirstViewClient,
        in_window_cb: Callable[[], bool],
        get_subscriptions_cb: Callable[[], tuple[list[int], list[str]]],
        on_event_cb: Callable[[dict[str, Any]], None],
    ) -> None:
        self._session = session
        self._client = client
        self._in_window_cb = in_window_cb
        self._get_subscriptions_cb = get_subscriptions_cb
        self._on_event_cb = on_event_cb
        self._task: asyncio.Task | None = None
        self.connected = False
        self.reconnect_count = 0
        self.last_error: str | None = None
        self.last_reconnect_at: str | None = None
        self.last_message_at: str | None = None
        self.last_lag_seconds: float | None = None
        self._last_trip_ids: list[int] = []
        self._last_vehicle_ids: list[str] = []

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self.connected = False

    async def _run(self) -> None:
        backoff = WS_BACKOFF_MIN_SECONDS
        while True:
            try:
                if not self._in_window_cb():
                    self.connected = False
                    backoff = WS_BACKOFF_MIN_SECONDS
                    await asyncio.sleep(WS_WINDOW_SLEEP_SECONDS)
                    continue

                ws_url = await self._client.async_ws_url()
                async with self._session.ws_connect(ws_url, heartbeat=25) as ws:
                    self.connected = True
                    self.last_error = None
                    self.last_reconnect_at = dt_util.utcnow().isoformat()
                    self.reconnect_count += 1
                    backoff = WS_BACKOFF_MIN_SECONDS
                    await self._subscribe(ws)
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.connected = False
                self.last_error = str(err)
                wait_seconds = min(backoff + random.uniform(0, 0.8), WS_BACKOFF_MAX_SECONDS)
                _LOGGER.warning("Websocket reconnect in %.1fs: %s", wait_seconds, err)
                await asyncio.sleep(wait_seconds)
                backoff = min(backoff * 2, WS_BACKOFF_MAX_SECONDS)

    async def _subscribe(self, ws) -> None:
        trip_ids, vehicle_ids = self._get_subscriptions_cb()
        if not trip_ids and self._last_trip_ids:
            trip_ids = list(self._last_trip_ids)
        if not vehicle_ids and self._last_vehicle_ids:
            vehicle_ids = list(self._last_vehicle_ids)
        if trip_ids:
            await ws.send_str(
                json.dumps({"type": "live.update.request", "payload": {"tripIds": trip_ids}})
            )
            self._last_trip_ids = sorted(set(trip_ids))
        if vehicle_ids:
            await ws.send_str(
                json.dumps(
                    {"type": "live.tracking.request", "payload": {"vehicleIds": vehicle_ids}}
                )
            )
            self._last_vehicle_ids = sorted(set(vehicle_ids))

    async def _consume(self, ws) -> None:
        async for msg in ws:
            await self._refresh_subscriptions_if_changed(ws)
            if msg.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                payload = self._decode(msg)
                if payload is not None:
                    self.last_message_at = dt_util.utcnow().isoformat()
                    ts = self._extract_event_ts(payload)
                    if ts is not None:
                        self.last_lag_seconds = max(
                            0.0, (dt_util.utcnow().replace(tzinfo=None) - ts).total_seconds()
                        )
                    self._on_event_cb(payload)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                self.connected = False
                return

    async def _refresh_subscriptions_if_changed(self, ws) -> None:
        trip_ids, vehicle_ids = self._get_subscriptions_cb()
        next_trips = sorted(set(trip_ids))
        next_vehicles = sorted(set(vehicle_ids))
        if next_trips and next_trips != self._last_trip_ids:
            await ws.send_str(
                json.dumps({"type": "live.update.request", "payload": {"tripIds": next_trips}})
            )
            self._last_trip_ids = next_trips
        if next_vehicles and next_vehicles != self._last_vehicle_ids:
            await ws.send_str(
                json.dumps(
                    {"type": "live.tracking.request", "payload": {"vehicleIds": next_vehicles}}
                )
            )
            self._last_vehicle_ids = next_vehicles

    def _decode(self, msg: WSMessage) -> dict[str, Any] | None:
        if msg.type == WSMsgType.BINARY:
            return {"type": "binary", "size": len(msg.data)}
        try:
            data = json.loads(msg.data)
            return data if isinstance(data, dict) else {"raw": data}
        except Exception:
            return {"raw_text": msg.data}

    def _extract_event_ts(self, payload: dict[str, Any]) -> datetime | None:
        event = payload.get("payload")
        if not isinstance(event, dict):
            return None
        raw = event.get("eventTimestamp")
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "last_reconnect_at": self.last_reconnect_at,
            "last_message_at": self.last_message_at,
            "last_lag_seconds": self.last_lag_seconds,
            "last_trip_subscriptions": list(self._last_trip_ids),
            "last_vehicle_subscriptions": list(self._last_vehicle_ids),
        }
