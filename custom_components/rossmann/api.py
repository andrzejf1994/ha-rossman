"""REST client for the Rossmann private API."""

from __future__ import annotations

import logging
from typing import Any
import uuid

import aiohttp

from .auth import RossmannAuth
from .const import (
    ACCEPT_LANGUAGE,
    API_USER_AGENT,
    AVAILABILITY_URL,
    COUPON_CATALOG_URL,
    COUPONS_URL,
    EXTERNAL_TOKEN_URL,
    GO_SAVINGS_URL,
    LOYALTY_CARD_URL,
    OFFLINE_ORDER_URL,
    ONLINE_ORDER_URL,
    ORDERS_HISTORY_URL,
    ORDER_TYPES_URL,
    USER_URL,
)
from .exceptions import (
    RossmannAuthError,
    RossmannCannotConnect,
    RossmannError,
    RossmannInvalidResponse,
)

_LOGGER = logging.getLogger(__name__)


def _unwrap_value(payload: Any) -> Any:
    if isinstance(payload, dict) and "Value" in payload:
        return payload["Value"]
    return payload


class RossmannApi:
    """Authenticated Rossmann JSON API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth: RossmannAuth,
        *,
        user_id: int | None = None,
    ) -> None:
        self._session = session
        self.auth = auth
        self.user_id = user_id
        seed = f"rossmann:{user_id or 'unknown'}"
        self.client_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        retry_auth: bool = True,
    ) -> Any:
        """Perform an authenticated Rossmann request."""
        await self.auth.async_ensure_valid()
        return await self._request_once(
            method,
            url,
            params=params,
            json=json,
            retry_auth=retry_auth,
        )

    async def _request_once(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        json: Any,
        retry_auth: bool,
    ) -> Any:
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Accept-Language": ACCEPT_LANGUAGE,
            "User-Agent": API_USER_AGENT,
            "Authorization": f"Bearer {self.auth.token}",
        }

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401 and retry_auth:
                    await self.auth.async_refresh(force=True)
                    return await self._request_once(
                        method,
                        url,
                        params=params,
                        json=json,
                        retry_auth=False,
                    )

                if response.status in (401, 403):
                    raise RossmannAuthError(
                        "unauthorized",
                        status=response.status,
                    )

                if response.status == 204:
                    return None

                if response.status >= 400:
                    body = await response.text()
                    _LOGGER.warning(
                        "Rossmann API %s %s failed (%s): %s",
                        method,
                        url,
                        response.status,
                        body[:1000],
                    )
                    raise RossmannError(
                        f"http_{response.status}",
                        status=response.status,
                    )

                try:
                    text = await response.text()

                    if not text.strip():
                        return None

                    return await response.json(content_type=None)

                except (ValueError, TypeError) as err:
                    _LOGGER.error(
                        "Rossmann API %s %s returned invalid JSON: %s",
                        method,
                        url,
                        text[:1000],
                    )
                    raise RossmannInvalidResponse("invalid_json") from err

        except (RossmannAuthError, RossmannError):
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RossmannCannotConnect(str(err)) from err

    async def get_user(self) -> dict[str, Any]:
        payload = await self.request("GET", USER_URL)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RossmannInvalidResponse("missing_user_data")
        if data.get("id") is None:
            raise RossmannInvalidResponse("missing_user_id")
        if self.user_id is None and data.get("id") is not None:
            self.user_id = int(data["id"])
            self.client_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"rossmann:{self.user_id}")
            )
        return data

    async def get_external_token(self, token_type: str = "UniqueOne") -> dict[str, Any]:
        payload = await self.request(
            "GET",
            EXTERNAL_TOKEN_URL,
            params={"type": token_type},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    async def get_loyalty_card(self, user_id: int) -> dict[str, Any]:
        payload = await self.request(
            "GET",
            LOYALTY_CARD_URL.format(user_id=user_id),
        )
        value = _unwrap_value(payload)
        return value if isinstance(value, dict) else {}

    async def get_coupons(self) -> list[dict[str, Any]]:
        payload = await self.request("GET", COUPONS_URL)
        value = _unwrap_value(payload)
        return [item for item in value or [] if isinstance(item, dict)]

    async def get_coupon(self, coupon_id: int) -> dict[str, Any]:
        payload = await self.request("GET", f"{COUPONS_URL}/{coupon_id}")
        value = _unwrap_value(payload)
        return value if isinstance(value, dict) else {}

    async def activate_coupon(self, coupon_id: int) -> dict[str, Any]:
        payload = await self.request(
            "POST",
            f"{COUPONS_URL}/{coupon_id}/activate",
            json={},
        )
        return payload if isinstance(payload, dict) else {}

    async def get_go_savings(self) -> dict[str, Any]:
        payload = await self.request("GET", GO_SAVINGS_URL)
        return payload if isinstance(payload, dict) else {}

    async def get_order_types(self, user_id: int) -> list[dict[str, Any]]:
        payload = await self.request(
            "GET",
            ORDER_TYPES_URL.format(user_id=user_id),
            params={"showOfflineOrders": "true"},
        )
        value = _unwrap_value(payload)
        return [item for item in value or [] if isinstance(item, dict)]

    async def get_orders(
        self,
        user_id: int,
        *,
        rows_count: int = 15,
        start_index: int = 0,
        order_type: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "lastDate": "",
            "rowsCount": rows_count,
            "startIndex": start_index,
            "userId": user_id,
        }
        if order_type is not None:
            params["orderType"] = order_type

        payload = await self.request(
            "GET",
            ORDERS_HISTORY_URL,
            params=params,
        )
        if not isinstance(payload, dict):
            raise RossmannInvalidResponse("invalid_order_history")
        return payload

    async def get_online_order(self, order_id: int) -> dict[str, Any]:
        payload = await self.request(
            "GET",
            ONLINE_ORDER_URL.format(order_id=order_id),
        )
        if not isinstance(payload, dict):
            raise RossmannInvalidResponse("invalid_online_order")
        return payload

    async def get_offline_order(self, transaction_id: int) -> dict[str, Any]:
        payload = await self.request(
            "GET",
            OFFLINE_ORDER_URL.format(transaction_id=transaction_id),
        )
        if not isinstance(payload, dict):
            raise RossmannInvalidResponse("invalid_offline_order")
        return payload

    async def get_coupon_products(
        self,
        coupon_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        payload = await self.request(
            "GET",
            COUPON_CATALOG_URL,
            params={
                "CouponId": coupon_id,
                "PageSize": page_size,
                "Page": page,
                "ClientUUID": self.client_uuid,
            },
        )
        if not isinstance(payload, dict):
            raise RossmannInvalidResponse("invalid_coupon_catalog")
        return payload

    async def check_availability(
        self,
        shop_number: int,
        product_ids: list[int],
    ) -> dict[str, Any]:
        payload = await self.request(
            "POST",
            AVAILABILITY_URL.format(shop_number=shop_number),
            json={"productIds": product_ids},
        )
        if not isinstance(payload, dict):
            raise RossmannInvalidResponse("invalid_availability")
        return payload
