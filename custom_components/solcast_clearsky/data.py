"""Custom types for solcast_clearsky."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import ClearSkyCoordinator


type ClearSkyConfigEntry = ConfigEntry[ClearSkyData]


@dataclass
class ClearSkyData:
    """Runtime data for the Solcast Clear Sky integration."""

    coordinator: ClearSkyCoordinator
