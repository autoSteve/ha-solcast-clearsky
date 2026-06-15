"""Service actions for solcast_clearsky."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    DETAILED_FORECAST,
    DETAILED_HOURLY,
    DOMAIN,
    END_DATE_TIME,
    LOGGER,
    SERVICE_QUERY_CLEAR_SKY_DATA,
    SITE,
    START_DATE_TIME,
)

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

    @staticmethod
    def _collapse_daily_breakdown(breakdown: dict[Any, Any]) -> list[dict[str, str | float]]:
        """Collapse per-day interval maps into a single ordered list."""
        collapsed: list[dict[str, str | float]] = []
        for intervals in breakdown.values():
            if isinstance(intervals, list):
                collapsed.extend(intervals)
        return collapsed

    @staticmethod
    def _interval_range(intervals: list[dict[str, str | float]]) -> tuple[str | None, str | None]:
        """Return first/last period_start from an interval list."""
        if not intervals:
            return None, None

        start = intervals[0].get("period_start")
        end = intervals[-1].get("period_start")
        return (start if isinstance(start, str) else None, end if isinstance(end, str) else None)

    @staticmethod
    def _normalize_datetime_value(value: datetime | str | None, field_name: str) -> datetime | None:
        """Return a UTC datetime for service query bounds."""
        if value is None:
            return None
        if isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
            if parsed is None:
                raise ServiceValidationError(f"Invalid datetime for {field_name}: {value}")
            return dt_util.as_utc(parsed)
        return dt_util.as_utc(value)

    @staticmethod
    def _filter_intervals(
        intervals: list[dict[str, str | float]],
        start_date_time: datetime | None,
        end_date_time: datetime | None,
    ) -> list[dict[str, str | float]]:
        """Filter intervals by optional start/end datetime bounds."""
        filtered: list[dict[str, str | float]] = []
        for interval in intervals:
            period_start = interval.get("period_start")
            if not isinstance(period_start, str):
                continue

            period_start_dt = dt_util.parse_datetime(period_start)
            if period_start_dt is None:
                continue

            period_start_utc = dt_util.as_utc(period_start_dt)
            if start_date_time is not None and period_start_utc < start_date_time:
                continue
            if end_date_time is not None and period_start_utc > end_date_time:
                continue
            filtered.append(interval)

        return filtered

    async def async_query_clear_sky_data(self, call: ServiceCall) -> dict[str, Any]:
        """Return clear-sky values for all sites or a single site."""
        LOGGER.debug("Action: %s", SERVICE_QUERY_CLEAR_SKY_DATA)
        coordinator = self._coordinator()
        if coordinator.data is None:
            await cast(Awaitable[None], coordinator.async_refresh())

        query_start_date_time = self._normalize_datetime_value(call.data.get(START_DATE_TIME), START_DATE_TIME)
        query_end_date_time = self._normalize_datetime_value(call.data.get(END_DATE_TIME), END_DATE_TIME)
        if query_start_date_time is not None and query_end_date_time is not None and query_end_date_time < query_start_date_time:
            raise ServiceValidationError(f"{END_DATE_TIME} must be on or after {START_DATE_TIME}")

        site = call.data.get(SITE)
        if site is None:
            full_detailed_forecast = self._collapse_daily_breakdown(
                {day: coordinator.day_halfhourly_breakdown(day) for day in range(coordinator.day_count)}
            )
            full_detailed_hourly = self._collapse_daily_breakdown(
                {day: coordinator.day_hourly_breakdown(day) for day in range(coordinator.day_count)}
            )
            detailed_forecast = self._filter_intervals(
                full_detailed_forecast,
                query_start_date_time,
                query_end_date_time,
            )
            detailed_hourly = self._filter_intervals(
                full_detailed_hourly,
                query_start_date_time,
                query_end_date_time,
            )
            if (query_start_date_time is not None or query_end_date_time is not None) and not detailed_forecast and full_detailed_forecast:
                detailed_forecast = full_detailed_forecast
                detailed_hourly = full_detailed_hourly
            start_date_time, end_date_time = self._interval_range(detailed_forecast)

            return {
                "data": {
                    "day_count": coordinator.day_count,
                    "combined": coordinator.combined,
                    DETAILED_FORECAST: detailed_forecast,
                    DETAILED_HOURLY: detailed_hourly,
                    "start_date_time": start_date_time,
                    "end_date_time": end_date_time,
                }
            }

        requested_site = self._normalize_site_id(site)
        for site_data in coordinator.sites:
            if site_data["resource_id"] == requested_site:
                full_detailed_forecast = self._collapse_daily_breakdown(site_data.get(DETAILED_FORECAST, {}))
                full_detailed_hourly = self._collapse_daily_breakdown(site_data.get(DETAILED_HOURLY, {}))
                detailed_forecast = self._filter_intervals(
                    full_detailed_forecast,
                    query_start_date_time,
                    query_end_date_time,
                )
                detailed_hourly = self._filter_intervals(
                    full_detailed_hourly,
                    query_start_date_time,
                    query_end_date_time,
                )
                if (
                    (query_start_date_time is not None or query_end_date_time is not None)
                    and not detailed_forecast
                    and full_detailed_forecast
                ):
                    detailed_forecast = full_detailed_forecast
                    detailed_hourly = full_detailed_hourly
                start_date_time, end_date_time = self._interval_range(detailed_forecast)
                return {
                    "data": {
                        "day_count": coordinator.day_count,
                        "site_id": site_data["site_id"],
                        "forecasts": site_data["forecasts"],
                        DETAILED_FORECAST: detailed_forecast,
                        DETAILED_HOURLY: detailed_hourly,
                        "start_date_time": start_date_time,
                        "end_date_time": end_date_time,
                    }
                }

        raise ServiceValidationError(f"Unknown site: {site}")
