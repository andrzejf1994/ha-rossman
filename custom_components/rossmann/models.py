"""Models and payload normalization for Rossmann."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def parse_local_datetime(value: Any) -> datetime | None:
    """Parse Rossmann's local ISO-like timestamps without forcing a timezone."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except ValueError:
        return None


def strip_html(value: str | None) -> str | None:
    """Return a simple text version of small HTML fragments."""
    if not value:
        return value
    cleaned = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def order_key(order: dict[str, Any]) -> str | None:
    """Return stable ID for an order summary."""
    order_type = _as_int(order.get("orderType"))

    if order_type == 5:
        order_id = _as_int(order.get("orderId"))
        if order_id:
            return f"online_{order_id}"

    if order_type == 7:
        transaction_id = _as_int(order.get("transactionId"))
        if transaction_id:
            return f"offline_{transaction_id}"

    order_id = _as_int(order.get("orderId"))
    transaction_id = _as_int(order.get("transactionId"))
    date = _text(order.get("orderDate")) or "unknown"
    if order_id or transaction_id:
        return f"order_{order_type}_{order_id or transaction_id}_{date}"
    return None


@dataclass(slots=True)
class RossmannProduct:
    """One product line from a receipt."""

    id: int | None
    brand: str | None
    name: str | None
    caption: str | None
    unit: str | None
    unit_price: float | None
    quantity: float | None
    total_price: float | None
    picture: str | None
    product_url: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RossmannProduct":
        return cls(
            id=_as_int(payload.get("id") or payload.get("evoId")),
            brand=_text(payload.get("brand")),
            name=_text(payload.get("name")),
            caption=_text(payload.get("caption")),
            unit=_text(payload.get("unit")),
            unit_price=_as_float(payload.get("unitPrice")),
            quantity=_as_float(payload.get("quantity")),
            total_price=_as_float(payload.get("totalPrice")),
            picture=_text(payload.get("picture") or payload.get("pictureUrl")),
            product_url=_text(payload.get("navigateUrl")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "brand": self.brand,
            "name": self.name,
            "caption": self.caption,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "quantity": self.quantity,
            "total_price": self.total_price,
            "picture": self.picture,
            "product_url": self.product_url,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RossmannProduct":
        return cls(
            id=_as_int(value.get("id")),
            brand=_text(value.get("brand")),
            name=_text(value.get("name")),
            caption=_text(value.get("caption")),
            unit=_text(value.get("unit")),
            unit_price=_as_float(value.get("unit_price")),
            quantity=_as_float(value.get("quantity")),
            total_price=_as_float(value.get("total_price")),
            picture=_text(value.get("picture")),
            product_url=_text(value.get("product_url")),
        )


@dataclass(slots=True)
class RossmannDiscount:
    """Receipt discount."""

    name: str | None
    value: float | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RossmannDiscount":
        return cls(
            name=_text(payload.get("name")),
            value=_as_float(payload.get("value")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RossmannDiscount":
        return cls(
            name=_text(value.get("name")),
            value=_as_float(value.get("value")),
        )


@dataclass(slots=True)
class RossmannStore:
    """Store metadata safe to persist."""

    shop_number: int | None
    street: str | None
    city: str | None
    zip_code: str | None
    latitude: float | None = None
    longitude: float | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
        *,
        shop_number: int | None = None,
    ) -> "RossmannStore | None":
        if not isinstance(payload, dict) and shop_number is None:
            return None

        payload = payload or {}
        location = payload.get("storeLocation")
        if not isinstance(location, dict):
            location = {}

        resolved_shop = (
            _as_int(payload.get("shopId"))
            or _as_int(payload.get("shippingDestination"))
            or shop_number
        )

        return cls(
            shop_number=resolved_shop,
            street=_text(payload.get("street")),
            city=_text(payload.get("city")),
            zip_code=_text(payload.get("zipCode")),
            latitude=_as_float(location.get("latitude")),
            longitude=_as_float(location.get("longitude")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "shop_number": self.shop_number,
            "street": self.street,
            "city": self.city,
            "zip_code": self.zip_code,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RossmannStore":
        return cls(
            shop_number=_as_int(value.get("shop_number")),
            street=_text(value.get("street")),
            city=_text(value.get("city")),
            zip_code=_text(value.get("zip_code")),
            latitude=_as_float(value.get("latitude")),
            longitude=_as_float(value.get("longitude")),
        )


@dataclass(slots=True)
class RossmannReceipt:
    """Normalized receipt for both Rossmann GO and stationary purchases."""

    id: str
    purchase_type: str
    date: str | None
    total: float | None
    products_cost: float | None
    discount_total: float | None
    payment_method: str | None
    shop_number: int | None
    store: RossmannStore | None
    ticket_number: int | None
    cash_register_number: int | None
    cash_register_machine_number: int | None
    products: list[RossmannProduct] = field(default_factory=list)
    discounts: list[RossmannDiscount] = field(default_factory=list)

    @classmethod
    def from_online(
        cls,
        order_id: int,
        payload: dict[str, Any],
    ) -> "RossmannReceipt":
        products_summary = payload.get("productsSummary")
        if not isinstance(products_summary, dict):
            products_summary = {}

        payment = payload.get("paymentSummary")
        if not isinstance(payment, dict):
            payment = {}

        details = payload.get("orderDetails")
        if not isinstance(details, dict):
            details = {}

        delivery = payload.get("deliveryAddress")
        if not isinstance(delivery, dict):
            delivery = {}
        store_payload = delivery.get("storeAddress")
        if not isinstance(store_payload, dict):
            store_payload = None

        payments = payment.get("payments")
        payment_method = None
        if isinstance(payments, list):
            for item in payments:
                if isinstance(item, dict) and item.get("isSuccessPayment", True):
                    payment_method = _text(item.get("name"))
                    if payment_method:
                        break

        products = [
            RossmannProduct.from_payload(item)
            for item in products_summary.get("products", [])
            if isinstance(item, dict)
        ]
        discounts = [
            RossmannDiscount.from_payload(item)
            for item in payment.get("discounts", [])
            if isinstance(item, dict)
        ]

        store = RossmannStore.from_payload(store_payload)
        return cls(
            id=f"online_{order_id}",
            purchase_type="Rossmann GO",
            date=_text(details.get("dateAdd")),
            total=_as_float(payment.get("totalPrice") or details.get("onlinePaymentAmount")),
            products_cost=_as_float(payment.get("productsCost")),
            discount_total=_as_float(payment.get("sumOfDiscount")),
            payment_method=payment_method,
            shop_number=store.shop_number if store else None,
            store=store,
            ticket_number=None,
            cash_register_number=None,
            cash_register_machine_number=None,
            products=products,
            discounts=discounts,
        )

    @classmethod
    def from_offline(
        cls,
        transaction_id: int,
        payload: dict[str, Any],
    ) -> "RossmannReceipt":
        products_summary = payload.get("productsSummary")
        if not isinstance(products_summary, dict):
            products_summary = {}

        payment = payload.get("paymentSummary")
        if not isinstance(payment, dict):
            payment = {}

        payments = payment.get("payments")
        payment_method = None
        if isinstance(payments, list):
            for item in payments:
                if isinstance(item, dict) and item.get("isSuccessPayment", True):
                    payment_method = _text(item.get("name"))
                    if payment_method:
                        break

        products = [
            RossmannProduct.from_payload(item)
            for item in products_summary.get("products", [])
            if isinstance(item, dict)
        ]
        discounts = [
            RossmannDiscount.from_payload(item)
            for item in payment.get("discounts", [])
            if isinstance(item, dict)
        ]

        shop_number = _as_int(payload.get("shopNumber"))
        store = RossmannStore.from_payload(
            payload.get("storeAddress")
            if isinstance(payload.get("storeAddress"), dict)
            else None,
            shop_number=shop_number,
        )

        return cls(
            id=f"offline_{transaction_id}",
            purchase_type="Stacjonarne",
            date=_text(payload.get("dateAdd")),
            total=_as_float(payment.get("totalPrice")),
            products_cost=_as_float(payment.get("productsCost")),
            discount_total=_as_float(payment.get("sumOfDiscount")),
            payment_method=payment_method,
            shop_number=shop_number,
            store=store,
            ticket_number=_as_int(payload.get("ticketNumber")),
            cash_register_number=_as_int(payload.get("cashRegisterNumber")),
            cash_register_machine_number=_as_int(
                payload.get("cashRegisterMachineNumber")
            ),
            products=products,
            discounts=discounts,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "purchase_type": self.purchase_type,
            "date": self.date,
            "total": self.total,
            "products_cost": self.products_cost,
            "discount_total": self.discount_total,
            "payment_method": self.payment_method,
            "shop_number": self.shop_number,
            "store": self.store.as_dict() if self.store else None,
            "ticket_number": self.ticket_number,
            "cash_register_number": self.cash_register_number,
            "cash_register_machine_number": self.cash_register_machine_number,
            "products": [item.as_dict() for item in self.products],
            "discounts": [item.as_dict() for item in self.discounts],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RossmannReceipt | None":
        receipt_id = _text(value.get("id"))
        if not receipt_id:
            return None

        store = value.get("store")
        return cls(
            id=receipt_id,
            purchase_type=_text(value.get("purchase_type")) or "Nieznany",
            date=_text(value.get("date")),
            total=_as_float(value.get("total")),
            products_cost=_as_float(value.get("products_cost")),
            discount_total=_as_float(value.get("discount_total")),
            payment_method=_text(value.get("payment_method")),
            shop_number=_as_int(value.get("shop_number")),
            store=RossmannStore.from_dict(store) if isinstance(store, dict) else None,
            ticket_number=_as_int(value.get("ticket_number")),
            cash_register_number=_as_int(value.get("cash_register_number")),
            cash_register_machine_number=_as_int(
                value.get("cash_register_machine_number")
            ),
            products=[
                RossmannProduct.from_dict(item)
                for item in value.get("products", [])
                if isinstance(item, dict)
            ],
            discounts=[
                RossmannDiscount.from_dict(item)
                for item in value.get("discounts", [])
                if isinstance(item, dict)
            ],
        )


@dataclass(slots=True)
class RossmannCoupon:
    """Coupon summary."""

    id: int
    status_id: int | None
    headline: str | None
    campaign_name: str | None
    valid_from: str | None
    valid_to: str | None
    validity_text: str | None
    image_url: str | None
    is_activable: bool
    is_linked_to_user: bool
    channel_text: str | None = None
    terms: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RossmannCoupon | None":
        coupon_id = _as_int(payload.get("Id") or payload.get("id"))
        if not coupon_id:
            return None

        status_id = _as_int(payload.get("StatusId"))
        linked = bool(payload.get("IsLinkedToUser", False))
        explicit_activable = payload.get("IsActivable")
        if isinstance(explicit_activable, bool):
            activable = explicit_activable
        else:
            activable = status_id in (None, 0) and not linked

        return cls(
            id=coupon_id,
            status_id=status_id,
            headline=_text(payload.get("Headline")),
            campaign_name=_text(payload.get("CmpName")),
            valid_from=_text(payload.get("StartShopDate")),
            valid_to=_text(payload.get("ValidTo")),
            validity_text=_text(payload.get("ValidityText")),
            image_url=_text(payload.get("BackgroundImageUrl")),
            is_activable=activable,
            is_linked_to_user=linked,
            channel_text=_text(payload.get("CmpChannelText")),
            terms=_text(payload.get("TermsAndConditions")),
        )

    @property
    def is_active(self) -> bool:
        return self.status_id == 1 or self.is_linked_to_user

    def can_activate(self, now: datetime) -> bool:
        if self.is_active or not self.is_activable:
            return False

        starts = parse_local_datetime(self.valid_from)
        ends = parse_local_datetime(self.valid_to)

        if starts and now < starts:
            return False
        if ends and now > ends:
            return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status_id": self.status_id,
            "headline": self.headline,
            "campaign_name": self.campaign_name,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "validity_text": self.validity_text,
            "image_url": self.image_url,
            "is_activable": self.is_activable,
            "is_active": self.is_active,
            "channel_text": self.channel_text,
        }


@dataclass(slots=True)
class RossmannData:
    """Coordinator snapshot."""

    user_id: int
    card_number: str | None
    loyalty_points: int
    coupons: list[RossmannCoupon]
    available_coupons: list[RossmannCoupon]
    receipts: list[RossmannReceipt]
    orders: list[dict[str, Any]]
    today_spend: float
    month_spend: float
    year_spend: float
    customer_savings: float
    customer_savings_range: str | None
    go_savings: float
    currency: str = "PLN"

    @property
    def latest_receipt(self) -> RossmannReceipt | None:
        return self.receipts[0] if self.receipts else None
