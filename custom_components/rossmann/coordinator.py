"""DataUpdateCoordinator for Rossmann."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RossmannApi
from .const import (
    CONF_AUTO_COUPONS,
    CONF_RECEIPT_DETAIL_LIMIT,
    CONF_SCAN_INTERVAL,
    DEFAULT_AUTO_COUPONS,
    DEFAULT_RECEIPT_DETAIL_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_PURCHASE,
    MAX_BOOTSTRAP_PAGES,
    MAX_ORDER_CACHE,
    MAX_RECEIPT_CACHE,
    MAX_RECENT_SYNC_PAGES,
    ORDER_PAGE_SIZE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)
from .exceptions import RossmannAuthError, RossmannCannotConnect, RossmannError
from .models import (
    RossmannCoupon,
    RossmannData,
    RossmannReceipt,
    order_key,
    parse_local_datetime,
    strip_html,
)

_LOGGER = logging.getLogger(__name__)


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _order_date(order: dict[str, Any]) -> datetime | None:
    return parse_local_datetime(order.get("orderDate"))


def _order_sort_key(order: dict[str, Any]) -> datetime:
    return _order_date(order) or datetime.min


def _is_completed_order(order: dict[str, Any]) -> bool:
    """Best-effort filter for finalized purchases.

    Stationary history entries observed in the official app have no status.
    Rossmann GO finalized orders use status "Zrealizowane" / status id 420.
    """
    order_type = _as_int(order.get("orderType"))
    if order_type == 7:
        return True
    if order_type == 5:
        status = str(order.get("status") or "").strip().casefold()
        status_id = _as_int(order.get("orderStatusId"))
        return status == "zrealizowane" or status_id == 420
    return False


class RossmannCoordinator(DataUpdateCoordinator[RossmannData]):
    """Poll Rossmann account data and cache receipt details."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: RossmannApi,
    ) -> None:
        self.entry = entry
        self.api = api
        self.user_id = int(entry.data["user_id"])

        interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL.total_seconds() // 60,
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )

        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry.entry_id}",
            private=True,
            atomic_writes=True,
        )

        self._orders: dict[str, dict[str, Any]] = {}
        self._receipts: dict[str, RossmannReceipt] = {}
        self._customer_savings: dict[str, Any] = {}
        self._had_persisted_orders = False
        self._first_update_done = False

    @property
    def auto_coupons(self) -> bool:
        return bool(
            self.entry.options.get(CONF_AUTO_COUPONS, DEFAULT_AUTO_COUPONS)
        )

    @property
    def receipt_detail_limit(self) -> int:
        return int(
            self.entry.options.get(
                CONF_RECEIPT_DETAIL_LIMIT,
                DEFAULT_RECEIPT_DETAIL_LIMIT,
            )
        )

    def update_options(self) -> None:
        """Apply options without reloading the config entry."""
        minutes = int(
            self.entry.options.get(
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL.total_seconds() // 60,
            )
        )
        self.update_interval = timedelta(minutes=minutes)

    async def _async_setup(self) -> None:
        """Load private cache and validate the current account."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            raw_orders = stored.get("orders")
            if isinstance(raw_orders, dict):
                self._orders = {
                    key: value
                    for key, value in raw_orders.items()
                    if isinstance(key, str) and isinstance(value, dict)
                }

            raw_receipts = stored.get("receipts")
            if isinstance(raw_receipts, dict):
                for key, value in raw_receipts.items():
                    if not isinstance(key, str) or not isinstance(value, dict):
                        continue
                    receipt = RossmannReceipt.from_dict(value)
                    if receipt is not None:
                        self._receipts[key] = receipt

            savings = stored.get("customer_savings")
            if isinstance(savings, dict):
                self._customer_savings = savings

        self._had_persisted_orders = bool(self._orders)

        try:
            user = await self.api.get_user()
        except RossmannAuthError as err:
            raise ConfigEntryAuthFailed from err
        except RossmannCannotConnect as err:
            raise UpdateFailed(str(err)) from err
        except RossmannError as err:
            raise UpdateFailed(str(err)) from err

        api_user_id = _as_int(user.get("id"))
        if api_user_id is None:
            raise UpdateFailed("Rossmann user response has no id")

        if api_user_id != self.user_id:
            raise ConfigEntryAuthFailed("Rossmann account changed")

    async def _async_update_data(self) -> RossmannData:
        previous_keys = set(self._orders)

        try:
            await self._sync_history()

            loyalty_task = self.api.get_loyalty_card(self.user_id)
            coupons_task = self.api.get_coupons()
            go_savings_task = self.api.get_go_savings()

            loyalty, coupon_payloads, go_savings = await asyncio.gather(
                loyalty_task,
                coupons_task,
                go_savings_task,
            )

            coupons = [
                coupon
                for payload in coupon_payloads
                if (coupon := RossmannCoupon.from_payload(payload)) is not None
            ]

            if self.auto_coupons:
                activated = await self._activate_ready_coupons(coupons)
                if activated:
                    coupon_payloads = await self.api.get_coupons()
                    coupons = [
                        coupon
                        for payload in coupon_payloads
                        if (coupon := RossmannCoupon.from_payload(payload))
                        is not None
                    ]

            latest_orders = sorted(
                self._orders.values(),
                key=_order_sort_key,
                reverse=True,
            )[: self.receipt_detail_limit]

            await self._ensure_receipt_details(latest_orders)
            self._prune_caches()

            now = dt_util.now().replace(tzinfo=None)
            available_coupons = [
                coupon for coupon in coupons if coupon.can_activate(now)
            ]

            orders = sorted(
                self._orders.values(),
                key=_order_sort_key,
                reverse=True,
            )

            card_number = loyalty.get("Number")
            card_number = str(card_number) if card_number else None
            loyalty_points = _as_int(loyalty.get("LoyaltyPointsAmount")) or 0

            customer_savings_value = _as_float(
                self._customer_savings.get("savingsValue")
            )
            customer_savings_range = strip_html(
                str(self._customer_savings.get("timeRangeText") or "")
            )

            data = RossmannData(
                user_id=self.user_id,
                card_number=card_number,
                loyalty_points=loyalty_points,
                coupons=coupons,
                available_coupons=available_coupons,
                receipts=self._ordered_receipts(),
                orders=orders,
                today_spend=self._sum_spend(now, "day"),
                month_spend=self._sum_spend(now, "month"),
                year_spend=self._sum_spend(now, "year"),
                customer_savings=round(customer_savings_value, 2),
                customer_savings_range=customer_savings_range,
                go_savings=round(_as_float(go_savings.get("value")), 2),
            )

            await self._save_cache()

        except RossmannAuthError as err:
            raise ConfigEntryAuthFailed from err
        except RossmannCannotConnect as err:
            raise UpdateFailed(str(err)) from err
        except RossmannError as err:
            raise UpdateFailed(str(err)) from err

        new_keys = set(self._orders) - previous_keys
        should_fire = self._first_update_done or self._had_persisted_orders
        if should_fire and new_keys:
            for key in sorted(
                new_keys,
                key=lambda item: _order_sort_key(self._orders[item]),
            ):
                self._fire_new_purchase(key)

        self._first_update_done = True
        self._had_persisted_orders = True

        return data

    async def _sync_history(self) -> None:
        if not self._orders:
            await self._bootstrap_current_year()
            return

        await self._sync_recent_pages()

    async def _bootstrap_current_year(self) -> None:
        """Load enough history to calculate current-year spend correctly."""
        current_year = dt_util.now().year
        start_index = 0

        for _ in range(MAX_BOOTSTRAP_PAGES):
            payload = await self.api.get_orders(
                self.user_id,
                rows_count=ORDER_PAGE_SIZE,
                start_index=start_index,
            )
            rows = [
                item
                for item in payload.get("orders", [])
                if isinstance(item, dict)
            ]

            if start_index == 0:
                savings = payload.get("customerSavings")
                if isinstance(savings, dict):
                    self._customer_savings = savings

            if not rows:
                break

            keys_before = set(self._orders)
            self._merge_orders(rows)
            if start_index > 0 and set(self._orders) == keys_before:
                _LOGGER.debug(
                    "Rossmann history pagination returned no new orders at startIndex=%s",
                    start_index,
                )
                break

            dates = [date for row in rows if (date := _order_date(row))]
            oldest = min(dates) if dates else None

            if oldest is not None and oldest.year < current_year:
                break

            if len(rows) < ORDER_PAGE_SIZE:
                break

            start_index += len(rows)

    async def _sync_recent_pages(self) -> None:
        """Fetch new history pages until we hit already known purchases."""
        known_before = set(self._orders)
        start_index = 0

        for page in range(MAX_RECENT_SYNC_PAGES):
            payload = await self.api.get_orders(
                self.user_id,
                rows_count=ORDER_PAGE_SIZE,
                start_index=start_index,
            )
            rows = [
                item
                for item in payload.get("orders", [])
                if isinstance(item, dict)
            ]

            if page == 0:
                savings = payload.get("customerSavings")
                if isinstance(savings, dict):
                    self._customer_savings = savings

            if not rows:
                break

            page_keys = {key for row in rows if (key := order_key(row))}
            self._merge_orders(rows)

            if page_keys & known_before:
                break

            if len(rows) < ORDER_PAGE_SIZE:
                break

            start_index += len(rows)

    def _merge_orders(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            key = order_key(row)
            if key:
                self._orders[key] = row

    async def _ensure_receipt_details(
        self,
        orders: list[dict[str, Any]],
    ) -> None:
        missing = [
            order
            for order in orders
            if (key := order_key(order)) and key not in self._receipts
        ]
        if not missing:
            return

        semaphore = asyncio.Semaphore(4)

        async def _fetch(order: dict[str, Any]) -> RossmannReceipt | None:
            async with semaphore:
                return await self._fetch_receipt(order)

        results = await asyncio.gather(
            *(_fetch(order) for order in missing),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, RossmannAuthError):
                raise result
            if isinstance(result, Exception):
                _LOGGER.debug("Receipt detail fetch failed: %s", result)
                continue
            if isinstance(result, RossmannReceipt):
                self._receipts[result.id] = result

    async def _fetch_receipt(
        self,
        order: dict[str, Any],
    ) -> RossmannReceipt | None:
        order_type = _as_int(order.get("orderType"))

        if order_type == 5:
            order_id = _as_int(order.get("orderId"))
            if not order_id:
                return None
            payload = await self.api.get_online_order(order_id)
            return RossmannReceipt.from_online(order_id, payload)

        if order_type == 7:
            transaction_id = _as_int(order.get("transactionId"))
            if not transaction_id:
                return None
            payload = await self.api.get_offline_order(transaction_id)
            return RossmannReceipt.from_offline(transaction_id, payload)

        return None

    async def _activate_ready_coupons(
        self,
        coupons: list[RossmannCoupon],
    ) -> bool:
        now = dt_util.now().replace(tzinfo=None)
        activated = False

        for coupon in coupons:
            if not coupon.can_activate(now):
                continue
            try:
                await self.api.activate_coupon(coupon.id)
            except RossmannError as err:
                _LOGGER.warning(
                    "Could not activate Rossmann coupon %s: %s",
                    coupon.id,
                    err,
                )
                continue
            activated = True

        return activated

    async def async_activate_coupon(self, coupon_id: int) -> dict[str, Any]:
        """Activate one coupon and refresh coordinator data."""
        result = await self.api.activate_coupon(coupon_id)
        details = await self.api.get_coupon(coupon_id)
        await self.async_request_refresh()
        return {
            "coupon_id": coupon_id,
            "activation": result,
            "coupon": details,
        }

    async def async_activate_all(self) -> list[dict[str, Any]]:
        """Activate all currently activable coupons."""
        coupons = (
            list(self.data.available_coupons)
            if self.data
            else [
                coupon
                for payload in await self.api.get_coupons()
                if (coupon := RossmannCoupon.from_payload(payload)) is not None
                and coupon.can_activate(dt_util.now().replace(tzinfo=None))
            ]
        )

        results: list[dict[str, Any]] = []
        for coupon in coupons:
            try:
                activation = await self.api.activate_coupon(coupon.id)
                results.append(
                    {
                        "coupon_id": coupon.id,
                        "success": bool(activation.get("IsSuccess", True)),
                    }
                )
            except RossmannError as err:
                results.append(
                    {
                        "coupon_id": coupon.id,
                        "success": False,
                        "error": str(err),
                    }
                )

        await self.async_request_refresh()
        return results

    async def async_get_coupon_products(
        self,
        coupon_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return await self.api.get_coupon_products(
            coupon_id,
            page=page,
            page_size=page_size,
        )

    async def async_check_availability(
        self,
        shop_number: int,
        product_ids: list[int],
    ) -> dict[str, Any]:
        return await self.api.check_availability(
            shop_number,
            product_ids,
        )

    def _sum_spend(self, now: datetime, period: str) -> float:
        total = 0.0
        for order in self._orders.values():
            if not _is_completed_order(order):
                continue

            date = _order_date(order)
            if date is None:
                continue

            if period == "day":
                matches = date.date() == now.date()
            elif period == "month":
                matches = date.year == now.year and date.month == now.month
            elif period == "year":
                matches = date.year == now.year
            else:
                matches = False

            if matches:
                total += _as_float(order.get("price"))

        return round(total, 2)

    def _ordered_receipts(self) -> list[RossmannReceipt]:
        def _key(receipt: RossmannReceipt) -> datetime:
            return parse_local_datetime(receipt.date) or datetime.min

        return sorted(
            self._receipts.values(),
            key=_key,
            reverse=True,
        )[: self.receipt_detail_limit]

    def _prune_caches(self) -> None:
        ordered_orders = sorted(
            self._orders.items(),
            key=lambda item: _order_sort_key(item[1]),
            reverse=True,
        )[:MAX_ORDER_CACHE]
        self._orders = dict(ordered_orders)

        ordered_receipts = sorted(
            self._receipts.items(),
            key=lambda item: parse_local_datetime(item[1].date) or datetime.min,
            reverse=True,
        )[:MAX_RECEIPT_CACHE]
        self._receipts = dict(ordered_receipts)

    async def _save_cache(self) -> None:
        await self._store.async_save(
            {
                "orders": self._orders,
                "receipts": {
                    key: receipt.as_dict()
                    for key, receipt in self._receipts.items()
                },
                "customer_savings": self._customer_savings,
            }
        )

    def _fire_new_purchase(self, key: str) -> None:
        order = self._orders.get(key)
        if not order:
            return

        receipt = self._receipts.get(key)
        payload: dict[str, Any] = {
            "id": key,
            "order_type": order.get("orderTypeName"),
            "date": order.get("orderDate"),
            "total": _as_float(order.get("price")),
            "shop_number": order.get("shopNumber"),
        }

        if receipt:
            payload.update(
                {
                    "discount": receipt.discount_total,
                    "payment_method": receipt.payment_method,
                    "products_count": sum(
                        product.quantity or 0 for product in receipt.products
                    ),
                }
            )

        self.hass.bus.async_fire(EVENT_NEW_PURCHASE, payload)
