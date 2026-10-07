"""Binary sensors for the energy price calculator (thin client, ADR-0005).

ON when the current hour's rank (1 = cheapest, 24 = most expensive) is
among the cheapest X% of the day. Pure comparison, no calculation
(ADR-0005): the rank is computed server-side. Registered via the
binary_sensor platform so the entities get the binary_sensor.* prefix.

State comes from the shared coordinator (one API call per day, see
helpers/coordinator.py); the hour rollover re-renders without a fetch.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback

from .const import (
    ATTR_RANK,
    DOMAIN,
    PERCENT_THRESHOLDS,
)
from .helpers.coordinator import PriceDataCoordinator
from .sensor import _BasePriceSensor, _local_hour


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator: PriceDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TopCheapestSensor(coordinator, pct) for pct in PERCENT_THRESHOLDS])


class TopCheapestSensor(_BasePriceSensor, BinarySensorEntity):
    """ON when the current interval is among the cheapest X% of the day.

    Percentage-based so the semantics stay identical whether the provider
    serves hourly or quarter-hourly prices: 10% of 24 hours = rank 1-2,
    10% of 96 quarter-hours = rank 1-9. The interval count of the day is
    taken from the API response, not assumed. Floor semantics: the sensor
    is never ON for more than X% of the day's intervals.
    """

    def __init__(self, coordinator: PriceDataCoordinator, pct: int) -> None:
        super().__init__(coordinator)
        self._pct = pct

    @property
    def name(self):
        return f"Goedkoopste {self._pct}% (van de dag)"

    @property
    def unique_id(self):
        return f"{DOMAIN}_top_{self._pct}pct"

    @property
    def is_on(self):
        data = self._current_hour_data()
        if data is None:
            return False
        # Rank is 1-based over the day's intervals; _hours holds the
        # full day (the client enforces the interval count).
        intervals = len(self._hours) if self._hours else 0
        return intervals > 0 and (data.rank * 100) <= self._pct * intervals

    @property
    def extra_state_attributes(self):
        error = self._error
        if error is not None:
            return {"error": error}
        data = self._current_hour_data()
        if data is None:
            return {}
        return {
            ATTR_RANK: data.rank,
            "hour": _local_hour(data),
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # The current hour changes every local hour without new data.
        self._track_hour_rollover()
