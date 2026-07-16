"""Test clear-sky math helpers."""

from datetime import datetime
from typing import Any, cast

from homeassistant.components.solcast_clearsky.clearsky import (
    _calculate_ozone,
    _get_interpolated_atmos,
    build_atmos_timeline,
    compute_site_clearsky,
)


from unittest.mock import patch


async def test_calculate_ozone_clamped() -> None:
    """Test ozone approximation lower clamp behavior."""
    assert _calculate_ozone(0.0, 1) >= 0.2


async def test_get_interpolated_atmos_defaults_and_bounds() -> None:
    """Test atmospheric interpolation empty and boundary paths."""
    target = datetime(2026, 6, 15, 1, 0, 0)
    assert _get_interpolated_atmos(target, {}) == {"temp": 20.0, "rh": 50.0, "aod": 0.1}

    timeline = {
        datetime(2026, 6, 15, 0, 0, 0): {"temp": 10.0, "rh": 40.0, "aod": 0.1},
        datetime(2026, 6, 15, 3, 0, 0): {"temp": 16.0, "rh": 52.0, "aod": 0.2},
    }

    interpolated = _get_interpolated_atmos(target, timeline)
    assert round(interpolated["temp"], 3) == 12.0
    assert round(interpolated["rh"], 3) == 44.0
    assert round(interpolated["aod"], 3) == 0.133

    assert _get_interpolated_atmos(datetime(2026, 6, 14, 23, 0, 0), timeline) == timeline[datetime(2026, 6, 15, 0, 0, 0)]
    assert _get_interpolated_atmos(datetime(2026, 6, 15, 5, 0, 0), timeline) == timeline[datetime(2026, 6, 15, 3, 0, 0)]


async def test_build_atmos_timeline_parses_weather_id() -> None:
    """Test OWM parsing and weather-id to AOD mapping."""
    result = build_atmos_timeline(
        {
            "list": [
                {
                    "dt": 1718419200,
                    "main": {"temp": 21.5, "humidity": 65},
                    "weather": [{"id": 741}],
                },
                {
                    "dt": 1718430000,
                    "main": {"temp": 19.0, "humidity": 55},
                    "weather": [{"id": 800}],
                },
            ]
        }
    )

    values = list(result.values())
    assert values[0]["aod"] == 0.35
    assert values[1]["aod"] == 0.1


@patch("homeassistant.components.solcast_clearsky.clearsky.astral_elevation", return_value=-5.0)
@patch("homeassistant.components.solcast_clearsky.clearsky.astral_azimuth", return_value=120.0)
async def test_compute_site_clearsky_night_path(mock_az, mock_el) -> None:
    """Test clear-sky computation when sun is below horizon."""
    daily, halfhourly = compute_site_clearsky(
        astral_observer=cast(Any, object()),
        atmos_timeline={},
        start_time=datetime(2026, 6, 15, 0, 0, 0),
        days=1,
        capacity_kw=5.0,
        efficiency=0.9,
        tilt=30.0,
        azimuth=180.0,
        lat=-33.8,
    )

    assert daily == {0: 0.0}
    assert len(halfhourly[0]) == 48
    assert all(interval["pv_clearsky"] == 0.0 for interval in halfhourly[0])


@patch("homeassistant.components.solcast_clearsky.clearsky.astral_elevation", return_value=45.0)
@patch("homeassistant.components.solcast_clearsky.clearsky.astral_azimuth", return_value=180.0)
async def test_compute_site_clearsky_day_path(mock_az, mock_el) -> None:
    """Test clear-sky computation when sun is above horizon."""
    timeline = {
        datetime(2026, 6, 15, 0, 0, 0): {"temp": 20.0, "rh": 0.0, "aod": 0.1},
        datetime(2026, 6, 15, 3, 0, 0): {"temp": 20.0, "rh": 0.0, "aod": 0.1},
    }

    daily, halfhourly = compute_site_clearsky(
        astral_observer=cast(Any, object()),
        atmos_timeline=timeline,
        start_time=datetime(2026, 6, 15, 0, 0, 0),
        days=1,
        capacity_kw=5.0,
        efficiency=0.9,
        tilt=30.0,
        azimuth=180.0,
        lat=-33.8,
    )

    assert daily[0] > 0
    assert len(halfhourly[0]) == 48
    assert cast(float, halfhourly[0][0]["pv_clearsky"]) >= 0


@patch("homeassistant.components.solcast_clearsky.clearsky.astral_elevation", return_value=45.0)
@patch("homeassistant.components.solcast_clearsky.clearsky.astral_azimuth", return_value=180.0)
async def test_compute_site_clearsky_late_start_skips_out_of_range_day(mock_az, mock_el) -> None:
    """Test intervals beyond requested day window are skipped."""
    daily, halfhourly = compute_site_clearsky(
        astral_observer=cast(Any, object()),
        atmos_timeline={},
        start_time=datetime(2026, 6, 15, 23, 30, 0),
        days=1,
        capacity_kw=5.0,
        efficiency=0.9,
        tilt=30.0,
        azimuth=180.0,
        lat=-33.8,
    )

    assert daily[0] >= 0
    assert len(halfhourly[0]) == 1
