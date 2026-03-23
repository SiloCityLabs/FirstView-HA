"""FirstView API client."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from pycognito import Cognito

from .const import (
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
    DASHBOARD_BASE,
    WS_BASE,
)


class FirstViewClient:
    """Client for FirstView auth + REST + websocket URL generation."""

    def __init__(self, hass: HomeAssistant, session: ClientSession, email: str, password: str) -> None:
        self._hass = hass
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None

    async def async_ensure_token(self) -> str:
        """Ensure valid access token is available."""
        if self._access_token and self._token_expiry:
            if datetime.now(timezone.utc) < self._token_expiry:
                return self._access_token

        if self._refresh_token:
            refreshed = await self._hass.async_add_executor_job(self._refresh_tokens_sync)
            if refreshed:
                return self._access_token or ""

        await self._hass.async_add_executor_job(self._login_sync)
        if not self._access_token:
            raise RuntimeError("Failed to obtain access token")
        return self._access_token

    def _base_cognito(self) -> Cognito:
        return Cognito(
            COGNITO_USER_POOL_ID,
            COGNITO_CLIENT_ID,
            user_pool_region=COGNITO_REGION,
            username=self._email,
            access_token=self._access_token,
            refresh_token=self._refresh_token,
        )

    def _login_sync(self) -> None:
        user = self._base_cognito()
        user.authenticate(password=self._password)
        self._apply_tokens(user)

    def _refresh_tokens_sync(self) -> bool:
        user = self._base_cognito()
        try:
            user.renew_access_token()
        except Exception:
            return False
        self._apply_tokens(user)
        return True

    def _apply_tokens(self, user: Cognito) -> None:
        self._access_token = user.access_token
        self._refresh_token = user.refresh_token or self._refresh_token
        exp = None
        if user.access_claims:
            exp = user.access_claims.get("exp")
        if exp:
            self._token_expiry = datetime.fromtimestamp(int(exp), tz=timezone.utc)

    async def async_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_401: bool = True,
    ) -> Any:
        """Perform authenticated REST request."""
        token = await self.async_ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/plain, */*",
        }
        url = f"{DASHBOARD_BASE}{path}"
        async with self._session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=60,
        ) as resp:
            if resp.status == 401 and retry_401:
                self._access_token = None
                await self.async_ensure_token()
                return await self.async_request(
                    method, path, params=params, json_body=json_body, retry_401=False
                )

            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"{method} {path} failed ({resp.status}): {text[:500]}")

            ctype = (resp.headers.get("content-type") or "").lower()
            if "application/json" in ctype:
                return await resp.json(content_type=None)
            text = await resp.text()
            return {"status_code": resp.status, "raw_text": text}

    async def async_get_students(self) -> dict[str, Any]:
        return await self.async_request("GET", "/api/v2/followed-students")

    async def async_get_trips(self, trip_date: date | None = None) -> dict[str, Any]:
        d = (trip_date or date.today()).isoformat()
        return await self.async_request("GET", "/api/v3/student-trips", params={"date": d})

    async def async_get_notifications(self, skip: int = 0, limit: int = 50) -> dict[str, Any]:
        return await self.async_request(
            "GET",
            "/api/v1/notifications",
            params={"skip": skip, "limit": limit},
        )

    async def async_get_notifications_counter(self) -> dict[str, Any]:
        return await self.async_request("GET", "/api/v1/notifications/counter")

    async def async_get_recent_location(self, vehicle_ids: list[str]) -> list[dict[str, Any]]:
        if not vehicle_ids:
            return []
        data = await self.async_request(
            "GET",
            "/api/v1/recent-location",
            params={"vehicleIds": ",".join(vehicle_ids)},
        )
        return data if isinstance(data, list) else []

    async def async_get_trips_progress(self, trip_ids: list[int]) -> dict[str, Any]:
        if not trip_ids:
            return {"items": []}
        return await self.async_request(
            "GET",
            "/api/v1/trips/progress",
            params={"ids": ",".join(str(x) for x in trip_ids)},
        )

    async def async_ws_url(self) -> str:
        token = await self.async_ensure_token()
        return f"{WS_BASE}/?{urlencode({'access_token': token})}"
