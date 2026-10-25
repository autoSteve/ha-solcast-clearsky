"""Fixtures for solcast_clearsky tests."""

from collections.abc import Generator
import logging
from unittest.mock import AsyncMock, patch

from custom_components.solcast_clearsky import const
import pytest

from homeassistant import loader
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.fixture
def hass(hass: HomeAssistant) -> HomeAssistant:
    """Load from custom_components, as Home Assistant does for users.

    Same as Core's enable_custom_integrations fixture, which as an autouse fixture would set up hass before recorder_mock.
    """
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
    return hass


@pytest.fixture(autouse=True)
def fail_on_custom_integration_report() -> Generator[None]:
    """Fail a test when Core reports a wrong or deprecated call by this integration.

    For a built-in integration Core raises in many of these cases, for a custom integration it only logs
    "Detected that custom integration ...". This keeps such calls failing in the tests first.
    """
    reports: list[str] = []

    def collect(record: logging.LogRecord) -> bool:
        if record.getMessage().startswith(f"Detected that custom integration '{const.DOMAIN}'"):
            reports.append(record.getMessage())
        return True

    frame_logger = logging.getLogger("homeassistant.helpers.frame")
    level = frame_logger.level
    frame_logger.setLevel(logging.WARNING)  # Core reports at WARNING; a test that raises the root level must not hide it.
    frame_logger.addFilter(collect)
    yield
    frame_logger.removeFilter(collect)
    frame_logger.setLevel(level)
    if reports:
        pytest.fail("\n".join(reports))


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock async_setup_entry for config flow tests."""
    with patch(
        "custom_components.solcast_clearsky.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_solcast_solar_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a minimal solcast_solar config entry to hass."""
    entry = MockConfigEntry(domain=const.SOLCAST_SOLAR_DOMAIN, data={CONF_API_KEY: "dummy"})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_solcast_clearsky_entry() -> MockConfigEntry:
    """Return a minimal solcast_clearsky config entry."""
    return MockConfigEntry(domain=const.DOMAIN, data={"owm_api_key": "test-key"})
