"""Regression tests for sensitive WebSocket error details."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import RequestInfo, WSServerHandshakeError
from custom_components.firstview.ws import FirstViewWebsocketManager
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL


@pytest.mark.parametrize("handshake_error", [True, False])
async def test_websocket_errors_do_not_expose_credentials(
    monkeypatch, caplog, handshake_error
):
    """Neither published diagnostics nor logs may contain raw exception details."""
    token = "dummy-secret-access-token"
    url = URL(f"wss://wbsckt.myfirstview.com/?access_token={token}")
    if handshake_error:
        request = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
        error = WSServerHandshakeError(
            request, (), status=403, message=f"Rejected token {token}"
        )
        expected = "WSServerHandshakeError (HTTP 403)"
    else:
        error = RuntimeError(f"Failed connecting to {url}")
        expected = "RuntimeError"

    session = MagicMock()
    session.ws_connect.side_effect = error
    client = MagicMock()
    client.async_ws_url = AsyncMock(return_value=str(url))
    manager = FirstViewWebsocketManager(
        session, client, lambda: True, lambda: ([], []), MagicMock()
    )

    async def cancel_backoff(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", cancel_backoff)
    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await manager._run()

    assert manager.connected is False
    assert manager.diagnostics["last_error"] == expected
    assert expected in caplog.text
    for sensitive in (token, "access_token=", str(url), "Rejected token"):
        assert sensitive not in caplog.text
        assert sensitive not in str(manager.diagnostics)
