"""Service actions for solcast_clearsky."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import DETAILED_FORECAST, DETAILED_HOURLY, DOMAIN, LOGGER, SERVICE_QUERY_CLEAR_SKY_DATA, SITE

if TYPE_CHECKING:
    from .coordinator import ClearSkyCoordinator


class ClearSkyServiceActions:
    """Service actions for Solcast Clear Sky."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service helper."""
        self._hass = hass

    def _coordinator(self) -> ClearSkyCoordinator:
        """Return the coordinator for the first loaded clear-sky entry."""
        entries = self._hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("Solcast Clear Sky is not loaded")

        runtime_data = getattr(entries[0], "runtime_data", None)
        if runtime_data is None:
            raise ServiceValidationError("Solcast Clear Sky is not ready")
        return runtime_data.coordinator

    @staticmethod
    def _normalize_site_id(site_id: str) -> str:
        """Normalize a site id using the solcast_solar convention."""
        return site_id.lower().replace("_", "-")

    async def async_query_clear_sky_data(self, call: ServiceCall) -> dict[str, Any]:
        """Return clear-sky values for all sites or a single site."""
        LOGGER.debug("Action: %s", SERVICE_QUERY_CLEAR_SKY_DATA)
        coordinator = self._coordinator()
        if coordinator.data is None:
            coordinator.async_request_refresh()

        site = call.data.get(SITE)
        if site is None:
            return {
                "data": {
                    "day_count": coordinator.day_count,
                    "combined": coordinator.combined,
                    DETAILED_FORECAST: {day: coordinator.day_halfhourly_breakdown(day) for day in range(coordinator.day_count)},
                    DETAILED_HOURLY: {day: coordinator.day_hourly_breakdown(day) for day in range(coordinator.day_count)},
                    "sites": {
                        site_data["site_id"]: {
                            "forecasts": site_data["forecasts"],
                            DETAILED_FORECAST: site_data.get(DETAILED_FORECAST, {}),
                            DETAILED_HOURLY: site_data.get(DETAILED_HOURLY, {}),
                        }
                        for site_data in coordinator.sites
                    },
                }
            }

        requested_site = self._normalize_site_id(site)
        for site_data in coordinator.sites:
            if site_data["resource_id"] == requested_site:
                return {
                    "data": {
                        "day_count": coordinator.day_count,
                        "site_id": site_data["site_id"],
                        "forecasts": site_data["forecasts"],
                        DETAILED_FORECAST: site_data.get(DETAILED_FORECAST, {}),
                        DETAILED_HOURLY: site_data.get(DETAILED_HOURLY, {}),
                    }
                }

        raise ServiceValidationError(f"Unknown site: {site}")
