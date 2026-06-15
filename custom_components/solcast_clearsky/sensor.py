"""Sensor platform for solcast_clearsky.

Publishes combined clear-sky daily kWh sensors: today, tomorrow, D3…Dn.
Per-site values are exposed as attributes keyed by normalized site id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy

from .const import ATTRIBUTION, DETAILED_FORECAST, DETAILED_HOURLY, DOMAIN
from .coordinator import ClearSkyCoordinator
from .entity import ClearSkyEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


_DAY_NAMES = {
    0: "Today",
    1: "Tomorrow",
}


def _day_label(day_index: int) -> str:
    return _DAY_NAMES.get(day_index, f"D{day_index + 1}")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up clear-sky sensors."""
    coordinator: ClearSkyCoordinator = entry.runtime_data.coordinator
    created_day_indexes: set[int] = set()

    def _async_add_missing_day_entities() -> None:
        """Add additional day entities if day_count grows after startup."""
        day_count = coordinator.day_count
        entities: list[ClearSkyCombinedSensor] = []

        for day_index in range(day_count):
            if day_index in created_day_indexes:
                continue
            entities.append(
                ClearSkyCombinedSensor(
                    coordinator=coordinator,
                    entry=entry,
                    day_index=day_index,
                )
            )
            created_day_indexes.add(day_index)

        if entities:
            async_add_entities(entities)

    _async_add_missing_day_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_day_entities))


# ---------------------------------------------------------------------------
# Combined sensor
# ---------------------------------------------------------------------------


class ClearSkyCombinedSensor(ClearSkyEntity, SensorEntity):
    """Clear-sky combined daily forecast sensor (sum of all sites)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: ClearSkyCoordinator,
        entry: ConfigEntry,
        day_index: int,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self._day_index = day_index
        label = _day_label(day_index)
        self._attr_name = label
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_combined_d{day_index + 1}"

    @property
    def native_value(self) -> float | None:
        """Return the total clear-sky kWh for this day."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.combined.get(self._day_index)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose breakdown attributes according to selected options."""
        attributes: dict[str, Any] = {}

        if self.coordinator.attr_brk_halfhourly:
            attributes[DETAILED_FORECAST] = self.coordinator.day_halfhourly_breakdown(self._day_index)

        if self.coordinator.attr_brk_hourly:
            attributes[DETAILED_HOURLY] = self.coordinator.day_hourly_breakdown(self._day_index)

        if self.coordinator.attr_brk_site:
            attributes.update(self.coordinator.day_site_breakdown(self._day_index))

        return attributes
