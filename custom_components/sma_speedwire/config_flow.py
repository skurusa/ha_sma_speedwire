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
    CONF_FAST_DIAGNOSTIC_INTERVAL,
    CONF_MEDIUM_DIAGNOSTIC_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_FAST_DIAGNOSTIC_INTERVAL,
    DEFAULT_MEDIUM_DIAGNOSTIC_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_FAST_DIAGNOSTIC_INTERVAL,
    MAX_MEDIUM_DIAGNOSTIC_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_FAST_DIAGNOSTIC_INTERVAL,
    MIN_MEDIUM_DIAGNOSTIC_INTERVAL,
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
        ),
        vol.Required(
            CONF_FAST_DIAGNOSTIC_INTERVAL,
            default=DEFAULT_FAST_DIAGNOSTIC_INTERVAL,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_FAST_DIAGNOSTIC_INTERVAL,
                max=MAX_FAST_DIAGNOSTIC_INTERVAL,
            ),
        ),
        vol.Required(
            CONF_MEDIUM_DIAGNOSTIC_INTERVAL,
            default=DEFAULT_MEDIUM_DIAGNOSTIC_INTERVAL,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=MIN_MEDIUM_DIAGNOSTIC_INTERVAL,
                max=MAX_MEDIUM_DIAGNOSTIC_INTERVAL,
            ),
        ),
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
            api = None
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
            finally:
                if api is not None:
                    await self.hass.async_add_executor_job(api.close)

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
            if (
                user_input[CONF_FAST_DIAGNOSTIC_INTERVAL]
                < user_input[CONF_SCAN_INTERVAL]
                or user_input[CONF_MEDIUM_DIAGNOSTIC_INTERVAL]
                < user_input[CONF_FAST_DIAGNOSTIC_INTERVAL]
            ):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(
                        OPTIONS_SCHEMA,
                        user_input,
                    ),
                    errors={"base": "invalid_diagnostic_intervals"},
                )
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                self.config_entry.options,
            ),
        )
