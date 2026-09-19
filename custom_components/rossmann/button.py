"""Buttons for Rossmann."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
            RossmannRefreshButton(coordinator),
            RossmannActivateCouponsButton(coordinator),
        ]
    )


class RossmannButton(RossmannEntity, ButtonEntity):
    def __init__(
        self,
        coordinator: RossmannCoordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.user_id}_{key}"


class RossmannRefreshButton(RossmannButton):
    _attr_translation_key = "refresh"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class RossmannActivateCouponsButton(RossmannButton):
    _attr_translation_key = "activate_coupons"

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator, "activate_coupons")

    async def async_press(self) -> None:
        await self.coordinator.async_activate_all()
