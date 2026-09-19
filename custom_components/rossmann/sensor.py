"""Sensors for the Rossmann integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RossmannConfigEntry
from .coordinator import RossmannCoordinator
from .entity import RossmannEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RossmannConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RossmannLastTransactionSensor(coordinator),
            RossmannTodaySpendSensor(coordinator),
            RossmannMonthSpendSensor(coordinator),
            RossmannYearSpendSensor(coordinator),
            RossmannSavingsSensor(coordinator),
            RossmannGoSavingsSensor(coordinator),
            RossmannLoyaltyPointsSensor(coordinator),
            RossmannCardSensor(coordinator),
            RossmannCouponsSensor(coordinator),
            RossmannCouponsAvailableSensor(coordinator),
        ]
    )


class RossmannBaseSensor(RossmannEntity, SensorEntity):
    """Base Rossmann sensor."""

    def __init__(
        self,
        coordinator: RossmannCoordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.user_id}_{key}"


class RossmannMoneySensor(RossmannBaseSensor):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"
    _attr_suggested_display_precision = 2


class RossmannLastTransactionSensor(RossmannMoneySensor):
    _attr_translation_key = "last_transaction"
    _unrecorded_attributes = frozenset({"transactions", "products", "discounts"})

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "last_transaction")

    @property
    def native_value(self) -> float | None:
        receipt = self.coordinator.data.latest_receipt
        if receipt and receipt.total is not None:
            return receipt.total

        orders = self.coordinator.data.orders
        if not orders:
            return None
        try:
            return float(orders[0].get("price"))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        receipt = data.latest_receipt
        transactions = [
            {
                "id": item.id,
                "type": item.purchase_type,
                "date": item.date,
                "total": item.total,
                "discount": item.discount_total,
                "shop_number": item.shop_number,
                "payment_method": item.payment_method,
            }
            for item in data.receipts[:5]
        ]

        attrs: dict[str, Any] = {"transactions": transactions}
        if receipt is None:
            return attrs

        attrs.update(
            {
                "id": receipt.id,
                "type": receipt.purchase_type,
                "date": receipt.date,
                "discount": receipt.discount_total,
                "payment_method": receipt.payment_method,
                "shop_number": receipt.shop_number,
                "ticket_number": receipt.ticket_number,
                "cash_register_number": receipt.cash_register_number,
                "cash_register_machine_number": receipt.cash_register_machine_number,
                "store": receipt.store.as_dict() if receipt.store else None,
                "products": [item.as_dict() for item in receipt.products],
                "discounts": [item.as_dict() for item in receipt.discounts],
            }
        )
        return attrs


class RossmannTodaySpendSensor(RossmannMoneySensor):
    _attr_translation_key = "today_spend"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "today_spend")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.today_spend


class RossmannMonthSpendSensor(RossmannMoneySensor):
    _attr_translation_key = "month_spend"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "month_spend")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.month_spend


class RossmannYearSpendSensor(RossmannMoneySensor):
    _attr_translation_key = "year_spend"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "year_spend")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.year_spend


class RossmannSavingsSensor(RossmannMoneySensor):
    _attr_translation_key = "savings"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "savings")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.customer_savings

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"period": self.coordinator.data.customer_savings_range}


class RossmannGoSavingsSensor(RossmannMoneySensor):
    _attr_translation_key = "go_savings"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "go_savings")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.go_savings


class RossmannLoyaltyPointsSensor(RossmannBaseSensor):
    _attr_translation_key = "loyalty_points"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pkt."

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "loyalty_points")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.loyalty_points


class RossmannCardSensor(RossmannBaseSensor):
    _attr_translation_key = "card"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "card")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.card_number


class RossmannCouponsSensor(RossmannBaseSensor):
    _attr_translation_key = "coupons"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"coupons"})

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "coupons")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.coupons)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coupons = self.coordinator.data.coupons
        return {
            "active": sum(1 for coupon in coupons if coupon.is_active),
            "coupons": [coupon.as_dict() for coupon in coupons],
        }


class RossmannCouponsAvailableSensor(RossmannBaseSensor):
    _attr_translation_key = "coupons_available"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "coupons_available")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.available_coupons)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "coupon_ids": [
                coupon.id for coupon in self.coordinator.data.available_coupons
            ]
        }
