"""Config flow for sma_speedwire integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from .sma_speedwire import SMA_SPEEDWIRE, smaError
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        )
    }
)


class SMASpeedWireConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for sma_speedwire."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SMASpeedWireOptionsFlow:
        """Create the options flow."""
        return SMASpeedWireOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                api = SMA_SPEEDWIRE(
                    user_input[CONF_HOST],
                    user_input[CONF_PASSWORD],
                    _LOGGER,
                )
                await self.hass.async_add_executor_job(api.init)
            except smaError:
                _LOGGER.exception("Cannot connect to inverter")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=api.inv_class,
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )


class SMASpeedWireOptionsFlow(OptionsFlowWithReload):
    """Handle sma_speedwire options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                self.config_entry.options,
            ),
        )
