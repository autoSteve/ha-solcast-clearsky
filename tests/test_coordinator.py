"""Test the solcast_clearsky coordinator."""

from datetime import datetime
from types import SimpleNamespace
from typing import Self
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from homeassistant.components.solcast_clearsky.const import (
    CONF_OWM_API_KEY,
    DETAILED_FORECAST,
    DETAILED_HOURLY,
    SOLCAST_SOLAR_DOMAIN,
)
from homeassistant.components.solcast_clearsky.coordinator import (
    RETRY_INTERVAL_NO_SITES,
    UPDATE_INTERVAL,
    ClearSkyCoordinator,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from tests.common import MockConfigEntry


async def test_build_hourly_from_halfhourly() -> None:
    """Test half-hourly conversion into hourly averages."""
    intervals = [
        {"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 2.0},
        {"period_start": "2026-06-15T00:30:00+00:00", "pv_clearsky": 4.0},
        {"period_start": "2026-06-15T01:00:00+00:00", "pv_clearsky": 3.0},
    ]

    hourly = ClearSkyCoordinator._build_hourly_from_halfhourly(intervals)

    assert hourly == [
        {"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 3.0},
        {"period_start": "2026-06-15T01:00:00+00:00", "pv_clearsky": 3.0},
    ]


async def test_async_update_data_no_sites(hass: HomeAssistant) -> None:
    """Test update returns empty payload and retry interval when no sites exist."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    result = await coordinator._async_update_data()

    assert coordinator.update_interval == RETRY_INTERVAL_NO_SITES
    assert result["sites"] == []
    assert result["day_count"] == 2
    assert result["combined"] == {0: 0.0, 1: 0.0}
    assert result[DETAILED_FORECAST] == {0: [], 1: []}
    assert result[DETAILED_HOURLY] == {0: [], 1: []}


async def test_async_update_data_with_sites(hass: HomeAssistant) -> None:
    """Test update builds combined/site forecast payload when sites are available."""
    solcast_entry = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    solcast_entry.add_to_hass(hass)

    solcast_entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            advanced_day_entities=3,
            solcast=SimpleNamespace(
                sites=[
                    {
                        "resource_id": "site-1",
                        "name": "Site 1",
                        "tilt": 20,
                        "azimuth": 180,
                        "capacity": 5.0,
                        "loss_factor": 0.9,
                    }
                ],
                sites_cache=SimpleNamespace(_site_latitude={"site-1": {"latitude": -33.8}}),
            ),
        )
    )

    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    daily = {0: 3.5, 1: 4.0, 2: 2.0}
    halfhourly = {
        0: [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.0}],
        1: [{"period_start": "2026-06-16T00:00:00+00:00", "pv_clearsky": 2.0}],
        2: [{"period_start": "2026-06-17T00:00:00+00:00", "pv_clearsky": 3.0}],
    }

    with (
        patch.object(coordinator, "_fetch_owm", AsyncMock(return_value={"list": []})),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.build_atmos_timeline",
            return_value={},
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.get_astral_location",
            return_value=(SimpleNamespace(), None),
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.compute_site_clearsky",
            return_value=(daily, halfhourly),
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.dt_util.now",
            return_value=datetime(2026, 6, 15, 12, 0, 0),
        ),
    ):
        result = await coordinator._async_update_data()

    assert coordinator.update_interval == UPDATE_INTERVAL
    assert result["combined"] == daily
    assert result["day_count"] == 3
    assert result["sites"][0]["site_id"] == "site_1"
    assert DETAILED_FORECAST in result
    assert DETAILED_HOURLY in result


async def test_site_forecasts_and_breakdowns(hass: HomeAssistant) -> None:
    """Test coordinator helper methods for forecast lookups."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    assert coordinator.site_forecasts("site-1") == {}

    coordinator.data = {
        "day_count": 2,
        "combined": {0: 1.0, 1: 2.0},
        DETAILED_FORECAST: {0: [{"period_start": "x", "pv_clearsky": 1.0}], 1: []},
        DETAILED_HOURLY: {0: [{"period_start": "x", "pv_clearsky": 1.0}], 1: []},
        "sites": [{"site_id": "site_1", "forecasts": {0: 0.6, 1: 0.7}}],
    }

    assert coordinator.site_forecasts() == {0: 1.0, 1: 2.0}
    assert coordinator.site_forecasts("site-1") == {0: 0.6, 1: 0.7}
    assert coordinator.site_forecasts("missing") == {}
    assert coordinator.day_site_breakdown(0) == {"site_1": 0.6}
    assert coordinator.day_halfhourly_breakdown(0) == [{"period_start": "x", "pv_clearsky": 1.0}]
    assert coordinator.day_hourly_breakdown(0) == [{"period_start": "x", "pv_clearsky": 1.0}]


async def test_home_assistant_location_requires_coordinates(hass: HomeAssistant) -> None:
    """Test coordinator raises when HA location is unavailable."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    with (
        patch.object(hass.config, "latitude", None),
        patch.object(hass.config, "longitude", None),
        pytest.raises(UpdateFailed, match="location is not configured"),
    ):
        coordinator._home_assistant_location()


async def test_collect_solcast_sites_skips_unready_entries(hass: HomeAssistant) -> None:
    """Test site collection skips entries without runtime data or solcast object."""
    entry_without_runtime = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    entry_without_runtime.add_to_hass(hass)

    entry_without_solcast = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    entry_without_solcast.add_to_hass(hass)
    entry_without_solcast.runtime_data = SimpleNamespace(coordinator=SimpleNamespace())

    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    sites, day_count = coordinator._collect_solcast_sites()

    assert sites == []
    assert day_count == 2


async def test_fetch_owm_auth_failure(hass: HomeAssistant) -> None:
    """Test OWM fetch raises UpdateFailed on auth status."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    class _Resp:
        status = 401

        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    class _Session:
        def get(self, *args: object, **kwargs: object) -> _Resp:
            return _Resp()

    with (
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.async_get_clientsession",
            return_value=_Session(),
        ),
        pytest.raises(UpdateFailed, match="authentication failed"),
    ):
        await coordinator._fetch_owm()


async def test_async_update_data_owm_error(hass: HomeAssistant) -> None:
    """Test update failure wraps OWM client errors."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    with (
        patch.object(
            coordinator,
            "_collect_solcast_sites",
            return_value=(
                [
                    {
                        "resource_id": "site-1",
                        "site_id": "site_1",
                        "name": "Site 1",
                        "tilt": 20.0,
                        "azimuth": 180.0,
                        "capacity_kw": 5.0,
                        "efficiency": 0.9,
                        "lat": -33.8,
                    }
                ],
                2,
            ),
        ),
        patch.object(
            coordinator,
            "_fetch_owm",
            AsyncMock(side_effect=aiohttp.ClientError("boom")),
        ),
        pytest.raises(UpdateFailed, match="Error fetching OWM data"),
    ):
        await coordinator._async_update_data()


async def test_fetch_owm_success(hass: HomeAssistant) -> None:
    """Test OWM fetch success path returns parsed JSON payload."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    class _Resp:
        status = 200

        def raise_for_status(self) -> None:
            return None

        async def json(self) -> dict[str, list[dict[str, int]]]:
            return {"list": [{"dt": 1}]}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    class _Session:
        def get(self, *args: object, **kwargs: object) -> _Resp:
            return _Resp()

    with patch(
        "homeassistant.components.solcast_clearsky.coordinator.async_get_clientsession",
        return_value=_Session(),
    ):
        result = await coordinator._fetch_owm()

    assert result == {"list": [{"dt": 1}]}


async def test_async_update_data_skips_zero_capacity_and_merges_sites(
    hass: HomeAssistant,
) -> None:
    """Test update skips zero-capacity sites and merges interval values."""
    entry = MockConfigEntry(domain="solcast_clearsky", data={CONF_OWM_API_KEY: "test-key"})
    coordinator = ClearSkyCoordinator(hass, entry)

    sites_config = [
        {
            "resource_id": "site-1",
            "site_id": "site_1",
            "name": "Site 1",
            "tilt": 20.0,
            "azimuth": 180.0,
            "capacity_kw": 0.0,
            "efficiency": 0.9,
            "lat": -33.8,
        },
        {
            "resource_id": "site-2",
            "site_id": "site_2",
            "name": "Site 2",
            "tilt": 20.0,
            "azimuth": 180.0,
            "capacity_kw": 5.0,
            "efficiency": 0.9,
            "lat": -33.8,
        },
        {
            "resource_id": "site-3",
            "site_id": "site_3",
            "name": "Site 3",
            "tilt": 20.0,
            "azimuth": 180.0,
            "capacity_kw": 5.0,
            "efficiency": 0.9,
            "lat": -33.8,
        },
    ]

    results = [
        (
            {0: 1.0},
            {0: [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.0}]},
        ),
        (
            {0: 2.0},
            {0: [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 2.0}]},
        ),
    ]

    with (
        patch.object(coordinator, "_collect_solcast_sites", return_value=(sites_config, 1)),
        patch.object(coordinator, "_fetch_owm", AsyncMock(return_value={"list": []})),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.build_atmos_timeline",
            return_value={},
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.get_astral_location",
            return_value=(SimpleNamespace(), None),
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.compute_site_clearsky",
            side_effect=results,
        ),
        patch(
            "homeassistant.components.solcast_clearsky.coordinator.dt_util.now",
            return_value=datetime(2026, 6, 15, 12, 0, 0),
        ),
    ):
        result = await coordinator._async_update_data()

    assert result["combined"][0] == 3.0
    assert result[DETAILED_FORECAST][0][0]["pv_clearsky"] == 3.0
    assert len(result["sites"]) == 2
