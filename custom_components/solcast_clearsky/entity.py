"""Base entity for solcast_clearsky."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClearSkyCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class ClearSkyEntity(CoordinatorEntity[ClearSkyCoordinator]):
    """Base class for Solcast Clear Sky entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ClearSkyCoordinator, entry: ConfigEntry) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Solcast Clear Sky",
            manufacturer="Bird Clear Sky Model",
            model="OpenWeatherMap atmospheric correction",
            entry_type=None,
        )
