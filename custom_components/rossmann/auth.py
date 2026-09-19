"""Authentication helper for the Rossmann private API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import time
from typing import Any

import aiohttp

from .const import (
    ACCEPT_LANGUAGE,
    API_USER_AGENT,
    AUTH_REFRESH_URL,
    AUTH_TOKEN_URL,
)
from .exceptions import (
    RossmannAuthError,
    RossmannCannotConnect,
    RossmannInvalidResponse,
)

_LOGGER = logging.getLogger(__name__)

SaveTokenCallback = Callable[[str, int], Awaitable[None]]


class RossmannAuth:
    """Manage Rossmann JWT login and refresh."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        token: str | None = None,
        expiry: int = 0,
        save_token: SaveTokenCallback | None = None,
    ) -> None:
        self._session = session
        self._token = token or ""
        self._expiry = int(expiry or 0)
        self._save_token = save_token
        self._refresh_lock = __import__("asyncio").Lock()

    @property
    def token(self) -> str:
        """Return current JWT."""
        return self._token

    @property
    def expiry(self) -> int:
        """Return token expiry as Unix timestamp."""
        return self._expiry

    async def async_login(self, username: str, password: str) -> tuple[str, int]:
        """Authenticate with username/password and return token + expiry."""
        payload = {"userName": username, "password": password}
        token, expiry = await self._token_request(AUTH_TOKEN_URL, payload)
        self._token = token
        self._expiry = expiry
        return token, expiry

    async def async_ensure_valid(self) -> None:
        """Refresh the JWT shortly before it expires."""
        if not self._token:
            raise RossmannAuthError("missing_token")

        if self._expiry > int(time.time()) + 60:
            return

        await self.async_refresh()

    async def async_refresh(self, *, force: bool = False) -> tuple[str, int]:
        """Refresh the current JWT.

        Rossmann's refresh endpoint accepts the current JWT in a JSON body and
        returns a replacement JWT plus a new expiry timestamp.
        """
        async with self._refresh_lock:
            if not force and self._expiry > int(time.time()) + 60:
                return self._token, self._expiry

            if not self._token:
                raise RossmannAuthError("missing_token")

            token, expiry = await self._token_request(
                AUTH_REFRESH_URL,
                {"token": self._token},
            )
            self._token = token
            self._expiry = expiry

            if self._save_token is not None:
                await self._save_token(token, expiry)

            return token, expiry

    async def _token_request(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> tuple[str, int]:
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Accept-Language": ACCEPT_LANGUAGE,
            "User-Agent": API_USER_AGENT,
        }

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status in (400, 401, 403):
                    raise RossmannAuthError(
                        "invalid_auth",
                        status=response.status,
                    )

                if response.status >= 400:
                    body = await response.text()
                    _LOGGER.debug(
                        "Rossmann auth request %s failed (%s): %s",
                        url,
                        response.status,
                        body[:500],
                    )
                    raise RossmannCannotConnect(
                        f"http_{response.status}",
                        status=response.status,
                    )

                try:
                    data = await response.json(content_type=None)
                except (ValueError, TypeError) as err:
                    raise RossmannInvalidResponse("invalid_auth_json") from err

        except RossmannAuthError:
            raise
        except RossmannCannotConnect:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RossmannCannotConnect(str(err)) from err

        envelope = data.get("data") if isinstance(data, dict) else None
        if not isinstance(envelope, dict):
            raise RossmannInvalidResponse("missing_auth_data")

        token = envelope.get("token")
        expiry = envelope.get("expiry")

        if not isinstance(token, str) or not token:
            raise RossmannInvalidResponse("missing_token")

        try:
            expiry_int = int(expiry)
        except (TypeError, ValueError) as err:
            raise RossmannInvalidResponse("invalid_expiry") from err

        return token, expiry_int
