"""Test solcast_clearsky service actions."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.solcast_clearsky.actions import ClearSkyServiceActions
from homeassistant.components.solcast_clearsky.const import (
    CONF_OWM_API_KEY,
    DETAILED_FORECAST,
    DETAILED_HOURLY,
    DOMAIN,
    END_DATE_TIME,
    SERVICE_QUERY_CLEAR_SKY_DATA,
    SITE,
    SOLCAST_SOLAR_DOMAIN,
    START_DATE_TIME,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from tests.common import MockConfigEntry


async def _setup_loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a loaded clear-sky entry with solcast_solar present."""
    solcast_entry = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    solcast_entry.add_to_hass(hass)

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.solcast_clearsky.coordinator.ClearSkyCoordinator.async_refresh",
        new=AsyncMock(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_service_query_returns_combined_data_without_site_blocks(
    hass: HomeAssistant,
) -> None:
    """Test query service returns aggregate payload without per-site blocks."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    halfhourly = [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.1}]
    hourly = [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.1}]

    coordinator.data = {
        "day_count": 2,
        "combined": {0: 10.5, 1: 11.2},
        DETAILED_FORECAST: {0: halfhourly, 1: []},
        DETAILED_HOURLY: {0: hourly, 1: []},
        "sites": [
            {
                "resource_id": "site-1",
                "site_id": "site_1",
                "name": "Site 1",
                "forecasts": {0: 4.2, 1: 4.6},
                DETAILED_FORECAST: {0: halfhourly, 1: []},
                DETAILED_HOURLY: {0: hourly, 1: []},
            }
        ],
    }

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_QUERY_CLEAR_SKY_DATA,
        {},
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    response_data = cast(dict[str, Any], response["data"])

    assert response_data["combined"] == {0: 10.5, 1: 11.2}
    assert response_data[DETAILED_FORECAST] == halfhourly
    assert response_data[DETAILED_HOURLY] == hourly
    assert response_data["start_date_time"] == "2026-06-15T00:00:00+00:00"
    assert response_data["end_date_time"] == "2026-06-15T00:00:00+00:00"
    assert "sites" not in response_data


async def test_service_query_single_site(
    hass: HomeAssistant,
) -> None:
    """Test query service for a specific site id."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    coordinator.data = {
        "day_count": 1,
        "combined": {0: 5.0},
        DETAILED_FORECAST: {0: []},
        DETAILED_HOURLY: {0: []},
        "sites": [
            {
                "resource_id": "site-1",
                "site_id": "site_1",
                "name": "Site 1",
                "forecasts": {0: 5.0},
                DETAILED_FORECAST: {0: []},
                DETAILED_HOURLY: {0: []},
            }
        ],
    }

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_QUERY_CLEAR_SKY_DATA,
        {SITE: "site_1"},
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    response_data = cast(dict[str, Any], response["data"])

    assert response_data["site_id"] == "site_1"
    assert response_data["forecasts"] == {0: 5.0}
    assert response_data[DETAILED_FORECAST] == []
    assert response_data[DETAILED_HOURLY] == []
    assert response_data["start_date_time"] is None
    assert response_data["end_date_time"] is None


async def test_service_query_unknown_site_raises(
    hass: HomeAssistant,
) -> None:
    """Test query service raises on an unknown site."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    coordinator.data = {
        "day_count": 1,
        "combined": {0: 5.0},
        DETAILED_FORECAST: {0: []},
        DETAILED_HOURLY: {0: []},
        "sites": [],
    }

    with pytest.raises(ServiceValidationError, match="Unknown site"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_QUERY_CLEAR_SKY_DATA,
            {SITE: "missing_site"},
            blocking=True,
            return_response=True,
        )


async def test_service_query_filters_with_start_end_datetime(
    hass: HomeAssistant,
) -> None:
    """Test query service filters interval details with start/end datetime."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    halfhourly = [
        {"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 0.4},
        {"period_start": "2026-06-15T00:30:00+00:00", "pv_clearsky": 0.5},
        {"period_start": "2026-06-15T01:00:00+00:00", "pv_clearsky": 0.6},
    ]

    coordinator.data = {
        "day_count": 1,
        "combined": {0: 5.0},
        DETAILED_FORECAST: {0: halfhourly},
        DETAILED_HOURLY: {0: halfhourly},
        "sites": [],
    }

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_QUERY_CLEAR_SKY_DATA,
        {
            START_DATE_TIME: "2026-06-15T00:30:00+00:00",
            END_DATE_TIME: "2026-06-15T01:00:00+00:00",
        },
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    response_data = cast(dict[str, Any], response["data"])

    assert response_data[DETAILED_FORECAST] == halfhourly[1:]
    assert response_data["start_date_time"] == "2026-06-15T00:30:00+00:00"
    assert response_data["end_date_time"] == "2026-06-15T01:00:00+00:00"


async def test_service_query_falls_back_to_full_details_when_range_has_no_match(
    hass: HomeAssistant,
) -> None:
    """Test query returns full details when requested range has no overlap."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    halfhourly = [
        {"period_start": "2026-06-16T00:00:00+10:00", "pv_clearsky": 0.4},
        {"period_start": "2026-06-16T00:30:00+10:00", "pv_clearsky": 0.5},
    ]

    coordinator.data = {
        "day_count": 1,
        "combined": {0: 5.0},
        DETAILED_FORECAST: {0: halfhourly},
        DETAILED_HOURLY: {0: halfhourly},
        "sites": [],
    }

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_QUERY_CLEAR_SKY_DATA,
        {
            START_DATE_TIME: "2026-06-15T00:00:00Z",
            END_DATE_TIME: "2026-06-15T10:00:00Z",
        },
        blocking=True,
        return_response=True,
    )
    assert isinstance(response, dict)
    response_data = cast(dict[str, Any], response["data"])

    assert response_data[DETAILED_FORECAST] == halfhourly
    assert response_data[DETAILED_HOURLY] == halfhourly
    assert response_data["start_date_time"] == "2026-06-16T00:00:00+10:00"
    assert response_data["end_date_time"] == "2026-06-16T00:30:00+10:00"


async def test_service_query_invalid_start_end_range_raises(hass: HomeAssistant) -> None:
    """Test query service raises when end datetime is before start datetime."""
    await _setup_loaded_entry(hass)

    with pytest.raises(ServiceValidationError, match="end_date_time"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_QUERY_CLEAR_SKY_DATA,
            {
                START_DATE_TIME: "2026-06-15T01:00:00+00:00",
                END_DATE_TIME: "2026-06-15T00:30:00+00:00",
            },
            blocking=True,
            return_response=True,
        )


async def test_service_errors_when_integration_not_loaded(hass: HomeAssistant) -> None:
    """Test service raises when no clear-sky entry exists."""
    actions = ClearSkyServiceActions(hass)

    with pytest.raises(ServiceValidationError, match="not loaded"):
        actions._coordinator()


async def test_service_errors_when_runtime_data_missing(hass: HomeAssistant) -> None:
    """Test service raises when entry runtime data is not ready."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})
    entry.add_to_hass(hass)

    actions = ClearSkyServiceActions(hass)
    service_call = cast(ServiceCall, SimpleNamespace(data={}))

    with pytest.raises(ServiceValidationError, match="not ready"):
        await actions.async_query_clear_sky_data(service_call)


async def test_service_requests_refresh_when_data_missing(
    hass: HomeAssistant,
) -> None:
    """Test service triggers coordinator refresh when no cached data exists."""
    entry = await _setup_loaded_entry(hass)
    coordinator = entry.runtime_data.coordinator

    coordinator.data = None
    coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_QUERY_CLEAR_SKY_DATA,
        {},
        blocking=True,
        return_response=True,
    )

    coordinator.async_refresh.assert_awaited_once()
