"""Fixtures for solcast_clearsky tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.solcast_clearsky.const import DOMAIN, SOLCAST_SOLAR_DOMAIN
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock async_setup_entry for config flow tests."""
    with patch(
        "homeassistant.components.solcast_clearsky.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_solcast_solar_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a minimal solcast_solar config entry to hass."""
    entry = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={CONF_API_KEY: "dummy"})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_solcast_clearsky_entry() -> MockConfigEntry:
    """Return a minimal solcast_clearsky config entry."""
    return MockConfigEntry(domain=DOMAIN, data={"owm_api_key": "test-key"})
