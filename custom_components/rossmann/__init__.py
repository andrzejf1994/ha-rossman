"""Rossmann integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RossmannApi
from .auth import RossmannAuth
from .const import (
    ATTR_COUPON_ID,
    ATTR_PAGE,
    ATTR_PAGE_SIZE,
    ATTR_PRODUCT_IDS,
    ATTR_SHOP_NUMBER,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRY,
    CONF_USER_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_ACTIVATE_COUPON,
    SERVICE_CHECK_AVAILABILITY,
    SERVICE_GET_COUPON_PRODUCTS,
    SERVICE_REFRESH,
)
from .coordinator import RossmannCoordinator
from .exceptions import RossmannError

type RossmannConfigEntry = ConfigEntry[RossmannCoordinator]

_ACTIVATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COUPON_ID): cv.positive_int,
    }
)

_COUPON_PRODUCTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COUPON_ID): cv.positive_int,
        vol.Optional(ATTR_PAGE, default=1): vol.All(
            vol.Coerce(int),
            vol.Range(min=1),
        ),
        vol.Optional(ATTR_PAGE_SIZE, default=20): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=100),
        ),
    }
)

_AVAILABILITY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SHOP_NUMBER): cv.positive_int,
        vol.Required(ATTR_PRODUCT_IDS): vol.All(
            cv.ensure_list,
            [cv.positive_int],
            vol.Length(min=1, max=100),
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration-wide service actions."""
    hass.data.setdefault(DOMAIN, {})

    def _coordinator() -> RossmannCoordinator:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        if len(coordinators) != 1:
            raise ServiceValidationError(
                "Rossmann integration must have exactly one loaded config entry"
            )
        coordinator = coordinators[0]
        if not isinstance(coordinator, RossmannCoordinator):
            raise ServiceValidationError("Rossmann coordinator is not available")
        return coordinator

    async def _refresh(call: ServiceCall) -> None:
        await _coordinator().async_request_refresh()

    async def _activate_coupon(call: ServiceCall) -> ServiceResponse | None:
        try:
            result = await _coordinator().async_activate_coupon(
                int(call.data[ATTR_COUPON_ID])
            )
        except RossmannError as err:
            raise HomeAssistantError(str(err)) from err
        return result if call.return_response else None

    async def _get_coupon_products(call: ServiceCall) -> ServiceResponse:
        try:
            return await _coordinator().async_get_coupon_products(
                int(call.data[ATTR_COUPON_ID]),
                page=int(call.data[ATTR_PAGE]),
                page_size=int(call.data[ATTR_PAGE_SIZE]),
            )
        except RossmannError as err:
            raise HomeAssistantError(str(err)) from err

    async def _check_availability(call: ServiceCall) -> ServiceResponse:
        try:
            return await _coordinator().async_check_availability(
                int(call.data[ATTR_SHOP_NUMBER]),
                [int(value) for value in call.data[ATTR_PRODUCT_IDS]],
            )
        except RossmannError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _refresh,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE_COUPON,
        _activate_coupon,
        schema=_ACTIVATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_COUPON_PRODUCTS,
        _get_coupon_products,
        schema=_COUPON_PRODUCTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_AVAILABILITY,
        _check_availability,
        schema=_AVAILABILITY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RossmannConfigEntry,
) -> bool:
    """Set up Rossmann from a config entry."""
    session = async_get_clientsession(hass)

    async def _save_token(token: str, expiry: int) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_TOKEN: token,
                CONF_TOKEN_EXPIRY: expiry,
            },
        )

    auth = RossmannAuth(
        session,
        token=str(entry.data[CONF_TOKEN]),
        expiry=int(entry.data[CONF_TOKEN_EXPIRY]),
        save_token=_save_token,
    )
    api = RossmannApi(
        session,
        auth,
        user_id=int(entry.data[CONF_USER_ID]),
    )

    coordinator = RossmannCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(_async_options_updated)
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: RossmannConfigEntry,
) -> bool:
    """Unload Rossmann."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_options_updated(
    hass: HomeAssistant,
    entry: RossmannConfigEntry,
) -> None:
    """Apply changed options."""
    coordinator = entry.runtime_data
    coordinator.update_options()
    await coordinator.async_request_refresh()
