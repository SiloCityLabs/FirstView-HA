"""WebSocket manager for FirstView live events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from aiohttp import ClientSession, WSMessage, WSMsgType
from homeassistant.util import dt as dt_util

from .api import FirstViewClient

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
        backoff = 1
        while True:
            try:
                if not self._in_window_cb():
                    self.connected = False
                    backoff = 1
                    await asyncio.sleep(15)
                    continue

                ws_url = await self._client.async_ws_url()
                async with self._session.ws_connect(ws_url, heartbeat=25) as ws:
                    self.connected = True
                    backoff = 1
                    await self._subscribe(ws)
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.connected = False
                _LOGGER.warning("Websocket reconnect in %ss: %s", backoff, err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _subscribe(self, ws) -> None:
        trip_ids, vehicle_ids = self._get_subscriptions_cb()
        if trip_ids:
            await ws.send_str(
                json.dumps({"type": "live.update.request", "payload": {"tripIds": trip_ids}})
            )
        if vehicle_ids:
            await ws.send_str(
                json.dumps(
                    {"type": "live.tracking.request", "payload": {"vehicleIds": vehicle_ids}}
                )
            )

    async def _consume(self, ws) -> None:
        async for msg in ws:
            if msg.type in (WSMsgType.TEXT, WSMsgType.BINARY):
                payload = self._decode(msg)
                if payload is not None:
                    self._on_event_cb(payload)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                self.connected = False
                return

    def _decode(self, msg: WSMessage) -> dict[str, Any] | None:
        if msg.type == WSMsgType.BINARY:
            return {"type": "binary", "size": len(msg.data)}
        try:
            data = json.loads(msg.data)
            return data if isinstance(data, dict) else {"raw": data}
        except Exception:
            return {"raw_text": msg.data}
