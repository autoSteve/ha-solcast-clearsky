"""DataUpdateCoordinator for solcast_clearsky."""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.sun import get_astral_observer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .clearsky import build_atmos_timeline, compute_site_clearsky
from .const import (
    ATTR_BRK_HALFHOURY,
    ATTR_BRK_HOURLY,
    ATTR_BRK_SITE,
    CONF_OWM_API_KEY,
    DEFAULT_ATTR_BRK_HALFHOURY,
    DEFAULT_ATTR_BRK_HOURLY,
    DEFAULT_ATTR_BRK_SITE,
    DEFAULT_SYSTEM_EFFICIENCY,
    DETAILED_FORECAST,
    DETAILED_HOURLY,
    DOMAIN,
    LOGGER,
    OWM_FORECAST_URL,
    RETRY_INTERVAL_NO_SITES_SECONDS,
    SOLCAST_SOLAR_DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

# Keys used from solcast_solar const — imported by string to avoid hard dependency
_RESOURCE_ID = "resource_id"
_NAME = "name"
_TILT = "tilt"
_AZIMUTH = "azimuth"
_CAPACITY = "capacity"
_LOSS_FACTOR = "loss_factor"
_SITE_ATTRIBUTE_LATITUDE = "latitude"

UPDATE_INTERVAL = timedelta(hours=1)
RETRY_INTERVAL_NO_SITES = timedelta(seconds=RETRY_INTERVAL_NO_SITES_SECONDS)


class ClearSkyCoordinator(DataUpdateCoordinator):
    """Fetch OWM data and compute clear-sky PV forecasts for all solcast_solar sites."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.config_entry = config_entry
        self._owm_api_key: str = config_entry.data[CONF_OWM_API_KEY]
        self._default_day_count = self._discover_day_count()

    # ------------------------------------------------------------------
    # Public helpers consumed by sensor.py
    # ------------------------------------------------------------------

    @property
    def day_count(self) -> int:
        """Number of forecast day entities to publish, sourced from solcast_solar."""
        return self.data.get("day_count", self._default_day_count) if self.data else self._default_day_count

    @property
    def sites(self) -> list[dict[str, Any]]:
        """Per-site forecast data."""
        return self.data.get("sites", []) if self.data else []

    @property
    def combined(self) -> dict[int, float]:
        """Combined (all-site) daily clear-sky kWh totals, keyed by day_index."""
        return self.data.get("combined", {}) if self.data else {}

    @property
    def attr_brk_halfhourly(self) -> bool:
        """Whether half-hourly breakdown attributes are enabled."""
        return bool(self.config_entry.options.get(ATTR_BRK_HALFHOURY, DEFAULT_ATTR_BRK_HALFHOURY))

    @property
    def attr_brk_site(self) -> bool:
        """Whether per-site breakdown attributes are enabled."""
        return bool(self.config_entry.options.get(ATTR_BRK_SITE, DEFAULT_ATTR_BRK_SITE))

    @property
    def attr_brk_hourly(self) -> bool:
        """Whether hourly breakdown attributes are enabled."""
        return bool(self.config_entry.options.get(ATTR_BRK_HOURLY, DEFAULT_ATTR_BRK_HOURLY))

    @staticmethod
    def normalize_site_id(site_id: str) -> str:
        """Normalize a Solcast site id for attribute and service lookups."""
        return site_id.replace("-", "_").lower()

    def site_forecasts(self, site_id: str | None = None) -> dict[int, float]:
        """Return forecasts for all sites or a single site."""
        if self.data is None:
            return {}

        if site_id is None:
            return self.combined

        normalized_site_id = self.normalize_site_id(site_id)
        for site in self.sites:
            if site["site_id"] == normalized_site_id:
                return site["forecasts"]
        return {}

    def day_site_breakdown(self, day_index: int) -> dict[str, float]:
        """Return a per-site breakdown for a specific day."""
        if self.data is None:
            return {}

        return {site["site_id"]: site["forecasts"].get(day_index) for site in self.sites}

    def day_halfhourly_breakdown(self, day_index: int) -> list[dict[str, str | float]]:
        """Return combined half-hourly breakdown for a specific day."""
        if self.data is None:
            return []
        return self.data.get(DETAILED_FORECAST, {}).get(day_index, [])

    def day_hourly_breakdown(self, day_index: int) -> list[dict[str, str | float]]:
        """Return combined hourly breakdown for a specific day."""
        if self.data is None:
            return []
        return self.data.get(DETAILED_HOURLY, {}).get(day_index, [])

    def _home_assistant_location(self) -> tuple[float, float]:
        """Return the Home Assistant configured latitude and longitude."""
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude
        if latitude is None or longitude is None:
            raise UpdateFailed("Home Assistant location is not configured")
        return float(latitude), float(longitude)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_day_count(self) -> int:
        """Determine default day count from loaded solcast_solar entries."""
        day_count = 2
        for entry in self.hass.config_entries.async_entries(SOLCAST_SOLAR_DOMAIN):
            if not hasattr(entry, "runtime_data") or entry.runtime_data is None:
                continue
            coordinator = entry.runtime_data.coordinator
            entry_days: int = getattr(coordinator, "advanced_day_entities", 2)
            day_count = max(day_count, entry_days)
        return day_count

    @staticmethod
    def _build_hourly_from_halfhourly(intervals: list[dict[str, str | float]]) -> list[dict[str, str | float]]:
        """Convert half-hourly average-kW data to hourly average-kW data."""
        hourly: list[dict[str, str | float]] = []
        for i in range(0, len(intervals), 2):
            pair = intervals[i : i + 2]
            avg_kw = round(sum(float(p["pv_clearsky"]) for p in pair) / len(pair), 3)
            hourly.append(
                {
                    "period_start": pair[0]["period_start"],
                    "pv_clearsky": avg_kw,
                }
            )
        return hourly

    def _collect_solcast_sites(self) -> tuple[list[dict[str, Any]], int]:
        """Return (sites_config, day_count) gathered from all solcast_solar config entries.

        Must be called from the event loop thread.
        """
        sites: list[dict[str, Any]] = []
        day_count = 2  # today + tomorrow minimum
        ha_latitude, _ = self._home_assistant_location()

        for entry in self.hass.config_entries.async_entries(SOLCAST_SOLAR_DOMAIN):
            if not hasattr(entry, "runtime_data") or entry.runtime_data is None:
                continue
            coordinator = entry.runtime_data.coordinator
            solcast = getattr(coordinator, "solcast", None)
            if solcast is None or not hasattr(solcast, "sites"):
                continue

            entry_days: int = getattr(coordinator, "advanced_day_entities", 2)
            day_count = max(day_count, entry_days)

            for site in solcast.sites:
                resource_id = site.get(_RESOURCE_ID, "")
                lat = None
                with contextlib.suppress(AttributeError):
                    lat = solcast.sites_cache._site_latitude.get(resource_id, {}).get(_SITE_ATTRIBUTE_LATITUDE)  # noqa: SLF001

                sites.append(
                    {
                        "resource_id": resource_id,
                        "site_id": self.normalize_site_id(resource_id),
                        "name": site.get(_NAME, resource_id),
                        "tilt": float(site.get(_TILT) or 0),
                        "azimuth": float(site.get(_AZIMUTH) or 180),
                        "capacity_kw": float(site.get(_CAPACITY) or 0),
                        "efficiency": float(site.get(_LOSS_FACTOR) or DEFAULT_SYSTEM_EFFICIENCY),
                        "lat": float(lat) if lat is not None else ha_latitude,
                    }
                )

        return sites, day_count

    async def _fetch_owm(self) -> dict[str, Any]:
        """Fetch 5-day/3-hour OWM forecast for the HA configured location."""
        lat, lon = self._home_assistant_location()
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self._owm_api_key,
            "units": "metric",
        }
        session = async_get_clientsession(self.hass)
        async with session.get(
            OWM_FORECAST_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status in (401, 403):
                raise UpdateFailed(f"OWM authentication failed (HTTP {resp.status})")
            resp.raise_for_status()
            return await resp.json()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator contract
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch OWM data and compute clear-sky forecasts for all sites."""
        # Collect site config on the event loop (HA state is not thread-safe)
        sites_config, day_count = self._collect_solcast_sites()

        if not sites_config:
            self.update_interval = RETRY_INTERVAL_NO_SITES
            LOGGER.debug(
                "No solcast_solar sites currently available; retrying in %s seconds",
                int(RETRY_INTERVAL_NO_SITES.total_seconds()),
            )
            return {
                "sites": [],
                "combined": dict.fromkeys(range(day_count), 0.0),
                DETAILED_FORECAST: {day: [] for day in range(day_count)},
                DETAILED_HOURLY: {day: [] for day in range(day_count)},
                "day_count": day_count,
            }

        self.update_interval = UPDATE_INTERVAL

        try:
            owm_data = await self._fetch_owm()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise UpdateFailed(f"Error fetching OWM data: {exc}") from exc

        atmos_timeline = build_atmos_timeline(owm_data)

        astral_observer = get_astral_observer(self.hass)

        now_local = dt_util.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        site_results: list[dict[str, Any]] = []
        combined: dict[int, float] = dict.fromkeys(range(day_count), 0.0)
        combined_halfhourly: dict[int, list[dict[str, str | float]]] = {d: [] for d in range(day_count)}

        for site in sites_config:
            if site["capacity_kw"] <= 0:
                continue

            daily, halfhourly = compute_site_clearsky(
                astral_observer=astral_observer,
                atmos_timeline=atmos_timeline,
                start_time=today_start,
                days=day_count,
                capacity_kw=site["capacity_kw"],
                efficiency=site["efficiency"],
                tilt=site["tilt"],
                azimuth=site["azimuth"],
                lat=site["lat"],
            )

            site_results.append(
                {
                    "resource_id": site["resource_id"],
                    "site_id": site["site_id"],
                    "name": site["name"],
                    "forecasts": daily,
                    DETAILED_FORECAST: halfhourly,
                    DETAILED_HOURLY: {day: self._build_hourly_from_halfhourly(intervals) for day, intervals in halfhourly.items()},
                }
            )

            for day_idx, kwh in daily.items():
                combined[day_idx] = combined[day_idx] + kwh

            for day_idx, intervals in halfhourly.items():
                if not combined_halfhourly[day_idx]:
                    combined_halfhourly[day_idx] = [
                        {
                            "period_start": interval["period_start"],
                            "pv_clearsky": float(interval["pv_clearsky"]),
                        }
                        for interval in intervals
                    ]
                    continue

                for i, interval in enumerate(intervals):
                    combined_halfhourly[day_idx][i]["pv_clearsky"] = round(
                        float(combined_halfhourly[day_idx][i]["pv_clearsky"]) + float(interval["pv_clearsky"]),
                        3,
                    )

        combined = {k: round(v, 3) for k, v in combined.items()}
        combined_hourly = {day: self._build_hourly_from_halfhourly(intervals) for day, intervals in combined_halfhourly.items()}

        return {
            "sites": site_results,
            "combined": combined,
            DETAILED_FORECAST: combined_halfhourly,
            DETAILED_HOURLY: combined_hourly,
            "day_count": day_count,
        }
