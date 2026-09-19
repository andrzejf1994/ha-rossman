"""Base entity for Rossmann."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RossmannCoordinator


class RossmannEntity(CoordinatorEntity[RossmannCoordinator]):
    """Base Rossmann coordinator entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RossmannCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.user_id))},
            name="Rossmann",
            manufacturer="Rossmann",
            model="Klub Rossmann",
        )
