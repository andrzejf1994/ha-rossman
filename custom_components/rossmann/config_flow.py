"""Config flow for Rossmann."""

import logging

_LOGGER = logging.getLogger(__name__)

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import RossmannApi
from .auth import RossmannAuth
from .const import (
    CONF_AUTO_COUPONS,
    CONF_RECEIPT_DETAIL_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRY,
    CONF_USER_ID,
    CONF_USERNAME,
    DEFAULT_AUTO_COUPONS,
    DEFAULT_RECEIPT_DETAIL_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_RECEIPT_DETAIL_LIMIT,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_RECEIPT_DETAIL_LIMIT,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .exceptions import (
    RossmannAuthError,
    RossmannCannotConnect,
    RossmannError,
)


class RossmannConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure Rossmann."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data, title = await self._login(
                    str(user_input[CONF_USERNAME]),
                    str(user_input[CONF_PASSWORD]),
                )
            except RossmannAuthError:
                errors["base"] = "invalid_auth"
            except RossmannCannotConnect:
                errors["base"] = "cannot_connect"
            except RossmannError as err:
                _LOGGER.exception(
                    "Rossmann configuration failed: %s: %s",
                    type(err).__name__,
                    err,
                )
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(data[CONF_USER_ID]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data=data,
                    options={
                        CONF_SCAN_INTERVAL: int(
                            DEFAULT_SCAN_INTERVAL.total_seconds() // 60
                        ),
                        CONF_AUTO_COUPONS: DEFAULT_AUTO_COUPONS,
                        CONF_RECEIPT_DETAIL_LIMIT: DEFAULT_RECEIPT_DETAIL_LIMIT,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._reauth_entry or self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data, _ = await self._login(
                    str(user_input[CONF_USERNAME]),
                    str(user_input[CONF_PASSWORD]),
                )
            except RossmannAuthError:
                errors["base"] = "invalid_auth"
            except RossmannCannotConnect:
                errors["base"] = "cannot_connect"
            except RossmannError as err:
                _LOGGER.exception(
                    "Rossmann configuration failed: %s: %s",
                    type(err).__name__,
                    err,
                )
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(data[CONF_USER_ID]))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, **data},
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=str(entry.data.get(CONF_USERNAME, "")),
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def _login(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any], str]:
        session = async_get_clientsession(self.hass)
        auth = RossmannAuth(session)
        token, expiry = await auth.async_login(username, password)
        api = RossmannApi(session, auth)
        user = await api.get_user()

        user_id = int(user["id"])
        email = str(user.get("email") or username)
        first_name = str(user.get("firstName") or "").strip()

        data = {
            CONF_USERNAME: username,
            CONF_TOKEN: token,
            CONF_TOKEN_EXPIRY: expiry,
            CONF_USER_ID: user_id,
        }
        title = f"Rossmann {first_name or email}"
        return data, title

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return RossmannOptionsFlow()


class RossmannOptionsFlow(OptionsFlow):
    """Rossmann integration options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(
                        options.get(
                            CONF_SCAN_INTERVAL,
                            DEFAULT_SCAN_INTERVAL.total_seconds() // 60,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=5,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_RECEIPT_DETAIL_LIMIT,
                    default=int(
                        options.get(
                            CONF_RECEIPT_DETAIL_LIMIT,
                            DEFAULT_RECEIPT_DETAIL_LIMIT,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_RECEIPT_DETAIL_LIMIT,
                        max=MAX_RECEIPT_DETAIL_LIMIT,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_AUTO_COUPONS,
                    default=bool(
                        options.get(CONF_AUTO_COUPONS, DEFAULT_AUTO_COUPONS)
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
