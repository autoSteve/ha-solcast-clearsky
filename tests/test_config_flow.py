"""Test the solcast_clearsky config flow."""

from typing import Any, Self, cast
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from homeassistant.components.solcast_clearsky.config_flow import ClearSkyFlowHandler
from homeassistant.components.solcast_clearsky.const import (
    ATTR_BRK_HALFHOURY,
    ATTR_BRK_HOURLY,
    ATTR_BRK_SITE,
    CONF_OWM_API_KEY,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry


class _MockResponse:
    """Mock aiohttp response context manager."""

    def __init__(self) -> None:
        self.raise_for_status = Mock()

    async def __aenter__(self) -> Self:
        """Enter async context."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit async context."""


async def test_user_flow_aborts_without_solcast_solar(hass: HomeAssistant) -> None:
    """Test user flow aborts when solcast_solar is not configured."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.ABORT
    assert result_data["reason"] == "solcast_solar_not_configured"


async def test_user_flow_creates_entry(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_solcast_solar_entry: MockConfigEntry,
) -> None:
    """Test user flow creates an entry with a valid API key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.FORM

    with patch(
        "homeassistant.components.solcast_clearsky.config_flow.ClearSkyFlowHandler._test_owm_key",
        new=AsyncMock(),
    ) as mock_test_key:
        result = await hass.config_entries.flow.async_configure(
            result_data["flow_id"],
            user_input={CONF_OWM_API_KEY: "valid-key"},
        )
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.CREATE_ENTRY
    assert result_data["title"] == "Solcast Clear Sky"
    assert result_data["data"] == {CONF_OWM_API_KEY: "valid-key"}
    mock_test_key.assert_awaited_once_with("valid-key")
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.usefixtures("mock_setup_entry")
async def test_options_flow_updates_options(
    hass: HomeAssistant,
    mock_solcast_clearsky_entry: MockConfigEntry,
) -> None:
    """Test options flow stores selected breakdown options."""
    mock_solcast_clearsky_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_solcast_clearsky_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_solcast_clearsky_entry.entry_id)
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result_data["flow_id"],
        user_input={
            ATTR_BRK_HALFHOURY: True,
            ATTR_BRK_HOURLY: False,
            ATTR_BRK_SITE: True,
        },
    )
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.CREATE_ENTRY
    assert result_data["data"] == {
        ATTR_BRK_HALFHOURY: True,
        ATTR_BRK_HOURLY: False,
        ATTR_BRK_SITE: True,
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=401,
                message="auth",
                headers=None,
            ),
            "auth",
        ),
        (
            aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=500,
                message="server",
                headers=None,
            ),
            "connection",
        ),
        (aiohttp.ClientConnectionError(), "connection"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_validation_errors(
    hass: HomeAssistant,
    mock_solcast_solar_entry: MockConfigEntry,
    error: Exception,
    expected: str,
) -> None:
    """Test user-flow error mapping for API validation failures."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result_data = cast(dict[str, Any], result)

    with patch(
        "homeassistant.components.solcast_clearsky.config_flow.ClearSkyFlowHandler._test_owm_key",
        new=AsyncMock(side_effect=error),
    ):
        result = await hass.config_entries.flow.async_configure(
            result_data["flow_id"],
            user_input={CONF_OWM_API_KEY: "invalid"},
        )
    result_data = cast(dict[str, Any], result)

    assert result_data["type"] is FlowResultType.FORM
    assert cast(dict[str, Any], result_data["errors"])["base"] == expected


async def test_test_owm_key_calls_raise_for_status(
    hass: HomeAssistant,
    mock_solcast_solar_entry: MockConfigEntry,
) -> None:
    """Test _test_owm_key performs an HTTP request and checks status."""
    handler = ClearSkyFlowHandler()
    handler.hass = hass

    mock_response = _MockResponse()
    mock_session = Mock()
    mock_session.get.return_value = mock_response

    with patch(
        "homeassistant.components.solcast_clearsky.config_flow.async_create_clientsession",
        return_value=mock_session,
    ):
        await handler._test_owm_key("test-key")

    mock_session.get.assert_called_once()
    mock_response.raise_for_status.assert_called_once()
