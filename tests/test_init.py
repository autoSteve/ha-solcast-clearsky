"""Test the solcast_clearsky integration setup lifecycle."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.solcast_clearsky import (
    async_reload_entry,
    async_unload_entry,
)
from homeassistant.components.solcast_clearsky.const import (
    CONF_OWM_API_KEY,
    DOMAIN,
    SERVICE_QUERY_CLEAR_SKY_DATA,
    SOLCAST_SOLAR_DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


async def test_setup_entry_retries_without_solcast_solar(hass: HomeAssistant) -> None:
    """Test setup enters retry state when solcast_solar is missing."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_registers_service_and_unload_removes_it(
    hass: HomeAssistant,
) -> None:
    """Test setup registers query service and unload succeeds."""
    solcast_entry = MockConfigEntry(domain=SOLCAST_SOLAR_DOMAIN, data={})
    solcast_entry.add_to_hass(hass)

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.solcast_clearsky.coordinator.ClearSkyCoordinator.async_refresh",
        new=AsyncMock(),
    ) as mock_refresh:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA)
    mock_refresh.assert_awaited_once()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA)


async def test_async_unload_entry_removes_service_when_no_entries(
    hass: HomeAssistant,
) -> None:
    """Test async_unload_entry removes service when domain has no remaining entries."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})

    hass.services.async_register(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA, lambda call: None)

    with (
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            AsyncMock(return_value=True),
        ),
        patch.object(hass.config_entries, "async_entries", return_value=[]),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    assert not hass.services.has_service(DOMAIN, SERVICE_QUERY_CLEAR_SKY_DATA)


async def test_async_reload_entry_calls_reload(hass: HomeAssistant) -> None:
    """Test async_reload_entry delegates to config entry reload."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_OWM_API_KEY: "test-key"})

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await async_reload_entry(hass, entry)

    mock_reload.assert_awaited_once_with(entry.entry_id)
