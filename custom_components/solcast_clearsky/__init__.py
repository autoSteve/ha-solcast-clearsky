"""Solcast Clear Sky integration.

Companion integration for solcast_solar that computes weather-attenuated
clear-sky PV forecasts using the Bird Clear Sky Model and OpenWeatherMap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady

from .actions import ClearSkyServiceActions
from .const import DOMAIN, LOGGER, SERVICE_QUERY_CLEAR_SKY_DATA, SOLCAST_SOLAR_DOMAIN
from .coordinator import ClearSkyCoordinator
from .data import ClearSkyConfigEntry, ClearSkyData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClearSkyConfigEntry,
) -> bool:
    """Set up Solcast Clear Sky from a config entry."""
    if not hass.config_entries.async_entries(SOLCAST_SOLAR_DOMAIN):
        raise ConfigEntryNotReady("solcast_solar must be configured before solcast_clearsky can load")

    coordinator = ClearSkyCoordinator(hass, entry)
    entry.runtime_data = ClearSkyData(coordinator=coordinator)

    if not hass.services.has_service(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA):
        service_actions = ClearSkyServiceActions(hass)
        hass.services.async_register(
            DOMAIN,
            SERVICE_QUERY_CLEAR_SKY_DATA,
            service_actions.async_query_clear_sky_data,
            supports_response=SupportsResponse.ONLY,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    hass.async_create_task(coordinator.async_refresh())

    LOGGER.debug("Solcast Clear Sky integration loaded")
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ClearSkyConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not hass.config_entries.async_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA)
    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant,
    entry: ClearSkyConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
