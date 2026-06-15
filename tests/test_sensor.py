"""Test solcast_clearsky sensor entities."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.solcast_clearsky.const import (
    ATTR_BRK_HALFHOURY,
    ATTR_BRK_HOURLY,
    ATTR_BRK_SITE,
    CONF_OWM_API_KEY,
    DETAILED_FORECAST,
    DETAILED_HOURLY,
    DOMAIN,
    SOLCAST_SOLAR_DOMAIN,
)
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


async def test_sensor_dynamic_day_entities_and_attributes(hass: HomeAssistant) -> None:
    """Test dynamic D3 entity creation and attribute exposure."""
    solcast_entry = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    solcast_entry.add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_OWM_API_KEY: "test-key"},
        options={
            ATTR_BRK_HALFHOURY: True,
            ATTR_BRK_HOURLY: True,
            ATTR_BRK_SITE: True,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.solcast_clearsky.coordinator.ClearSkyCoordinator.async_refresh",
        new=AsyncMock(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    coordinator.async_set_updated_data(
        {
            "day_count": 3,
            "combined": {0: 1.0, 1: 2.0, 2: 3.0},
            DETAILED_FORECAST: {
                0: [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.0}],
                1: [],
                2: [],
            },
            DETAILED_HOURLY: {
                0: [{"period_start": "2026-06-15T00:00:00+00:00", "pv_clearsky": 1.0}],
                1: [],
                2: [],
            },
            "sites": [{"site_id": "site_1", "forecasts": {0: 0.5, 1: 1.0, 2: 1.5}}],
        }
    )
    await hass.async_block_till_done()

    state_today = hass.states.get("sensor.solcast_clear_sky_today")
    state_tomorrow = hass.states.get("sensor.solcast_clear_sky_tomorrow")
    state_d3 = hass.states.get("sensor.solcast_clear_sky_d3")

    assert state_today is not None
    assert state_tomorrow is not None
    assert state_d3 is not None
    assert state_d3.state == "3.0"
    assert DETAILED_FORECAST in state_today.attributes
    assert DETAILED_HOURLY in state_today.attributes
    assert "site_1" in state_today.attributes
