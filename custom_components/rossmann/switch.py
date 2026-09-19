"""Switches for Rossmann."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RossmannConfigEntry
from .const import CONF_AUTO_COUPONS
from .coordinator import RossmannCoordinator
from .entity import RossmannEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RossmannConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RossmannAutoCouponsSwitch(entry.runtime_data, entry)])


class RossmannAutoCouponsSwitch(RossmannEntity, SwitchEntity):
    _attr_translation_key = "auto_coupons"

    def __init__(
        self,
        coordinator: RossmannCoordinator,
        entry: RossmannConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.user_id}_auto_coupons"

    @property
    def is_on(self) -> bool:
        return self.coordinator.auto_coupons

    async def async_turn_on(self, **kwargs) -> None:
        self._set_option(True)

    async def async_turn_off(self, **kwargs) -> None:
        self._set_option(False)

    def _set_option(self, value: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                **self._entry.options,
                CONF_AUTO_COUPONS: value,
            },
        )
        self.async_write_ha_state()
