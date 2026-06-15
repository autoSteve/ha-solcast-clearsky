"""Config flow for Solcast Clear Sky."""

from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    ATTR_BRK_HALFHOURY,
    ATTR_BRK_HOURLY,
    ATTR_BRK_SITE,
    CONF_OWM_API_KEY,
    DEFAULT_ATTR_BRK_HALFHOURY,
    DEFAULT_ATTR_BRK_HOURLY,
    DEFAULT_ATTR_BRK_SITE,
    DOMAIN,
    LOGGER,
    OWM_FORECAST_URL,
    SOLCAST_SOLAR_DOMAIN,
)


class ClearSkyFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Solcast Clear Sky."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> ClearSkyOptionsFlow:
        """Get the options flow for this handler."""
        return ClearSkyOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if not self.hass.config_entries.async_entries(SOLCAST_SOLAR_DOMAIN):
            return self.async_abort(reason="solcast_solar_not_configured")

        _errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._test_owm_key(user_input[CONF_OWM_API_KEY])
            except aiohttp.ClientResponseError as exc:
                if exc.status in (401, 403):
                    _errors["base"] = "auth"
                else:
                    LOGGER.error("OWM API error: %s", exc)
                    _errors["base"] = "connection"
            except (aiohttp.ClientError, TimeoutError) as exc:
                LOGGER.error("OWM connection error: %s", exc)
                _errors["base"] = "connection"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error validating OWM API key")
                _errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Solcast Clear Sky",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OWM_API_KEY,
                        default=(user_input or {}).get(CONF_OWM_API_KEY, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                }
            ),
            errors=_errors,
        )

    async def _test_owm_key(self, api_key: str) -> None:
        """Validate the OWM API key by making a test forecast request."""
        session = async_create_clientsession(self.hass)
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric", "cnt": 1}
        async with session.get(OWM_FORECAST_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()


class ClearSkyOptionsFlow(config_entries.OptionsFlow):
    """Handle Solcast Clear Sky options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, bool] | None = None) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        ATTR_BRK_HALFHOURY,
                        default=self._config_entry.options.get(ATTR_BRK_HALFHOURY, DEFAULT_ATTR_BRK_HALFHOURY),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        ATTR_BRK_HOURLY,
                        default=self._config_entry.options.get(ATTR_BRK_HOURLY, DEFAULT_ATTR_BRK_HOURLY),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        ATTR_BRK_SITE,
                        default=self._config_entry.options.get(ATTR_BRK_SITE, DEFAULT_ATTR_BRK_SITE),
                    ): selector.BooleanSelector(),
                }
            ),
        )
