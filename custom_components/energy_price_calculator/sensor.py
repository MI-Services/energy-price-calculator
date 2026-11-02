"""Sensors for the energy price calculator (thin client, ADR-0005).

No price calculation happens here: consumer prices and ranks come from the
server API (ADR-0006). The component converts UTC -> local time and compares
ranks against thresholds for display purposes only.

One API call per day per dataset serves every entity (see
helpers/coordinator.py): today's prices refresh at 00:05 local, tomorrow's
day-ahead prices at 14:30 local. All sensors read the shared coordinators
and compute their state as properties. The current-hour state and the
percentage sensors change on the local hour rollover - a timestamp
change, not a data change - so they re-render on the hour boundary
without touching the API.

Tomorrow's prices get their own entities instead of attributes on the
today sensors: automations (EV charge planning) and dashboards address
them directly, while today's sensor semantics stay identical for
existing consumers.

All price sensors carry state_class MEASUREMENT so Home Assistant records
long-term statistics for them (up to 2 years of price history). The hourly
sensors change state once per day (new prices at 00:05 / 14:30), the
current-hour sensor every local hour.
"""
from __future__ import annotations

from typing import List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CONSUMER_PRICE,
    ATTR_HOURS,
    ATTR_MARKET_PRICE,
    ATTR_PCT,
    ATTR_RANK,
    ATTR_STARTS_AT,
    COORD_TODAY,
    COORD_TOMORROW,
    DOMAIN,
    PERCENT_THRESHOLDS,
)
from .helpers.api_client import HourData
from .helpers.coordinator import PriceDataCoordinator
from .helpers.percentage_window import get_cheapest_window


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinators = hass.data[DOMAIN][entry.entry_id]
    sensors: list = [CurrentHourPriceSensor(coordinators[COORD_TODAY])]
    for hour in range(24):
        sensors.append(HourlyPriceSensor(coordinators[COORD_TODAY], hour))
        sensors.append(HourlyPriceTomorrowSensor(coordinators[COORD_TOMORROW], hour))
    for pct in PERCENT_THRESHOLDS:
        sensors.append(CheapestHoursTomorrowSensor(coordinators[COORD_TOMORROW], pct))
    async_add_entities(sensors)


def _local_hour(data: HourData) -> int:
    """Local hour of an API hour entry (API timestamps are UTC)."""
    return dt_util.as_local(data.starts_at).hour


class _BasePriceSensor(CoordinatorEntity):
    """Reads a shared coordinator; state is computed, never fetched.

    Entities stay visible (state unknown/off) with the error in their
    attributes when the coordinator has no data: "unavailable" would hide
    the diagnosis from the user.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)

    @property
    def _hours(self) -> Optional[List[HourData]]:
        return self.coordinator.data

    def _hour_for(self, local_hour: int) -> Optional[HourData]:
        if self._hours is None:
            return None
        for hour in self._hours:
            if _local_hour(hour) == local_hour:
                return hour
        return None

    def _current_hour_data(self) -> Optional[HourData]:
        return self._hour_for(dt_util.now().hour)

    @property
    def available(self) -> bool:
        return True

    @property
    def _error(self) -> Optional[str]:
        if self.coordinator.last_update_success or self.coordinator.data is not None:
            return None
        if self.coordinator.last_exception is not None:
            return str(self.coordinator.last_exception)
        return "No price data available yet"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

    @callback
    def _track_hour_rollover(self):
        """Re-render at every local hour boundary (state changes, data does not)."""
        self.async_on_remove(
            async_track_time_change(self.hass, self._hour_rolled, hour=None, minute=0, second=0)
        )

    @callback
    def _hour_rolled(self, _now):
        self.async_write_ha_state()


class CurrentHourPriceSensor(_BasePriceSensor, SensorEntity):
    """Current hour consumer price, straight from the today coordinator."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = f"{CURRENCY_EURO}/kWh"

    def __init__(self, coordinator: PriceDataCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def name(self):
        return "Huidige uurprijs"

    @property
    def unique_id(self):
        return f"{DOMAIN}_current_hour"

    @property
    def native_value(self):
        data = self._current_hour_data()
        if data is None:
            return None
        return data.consumer_price

    @property
    def extra_state_attributes(self):
        error = self._error
        if error is not None:
            return {"error": error}
        data = self._current_hour_data()
        if data is None:
            return {}
        return {
            ATTR_MARKET_PRICE: data.market_price,
            ATTR_CONSUMER_PRICE: data.consumer_price,
            ATTR_RANK: data.rank,
            ATTR_STARTS_AT: data.starts_at.isoformat(),
            "hour": _local_hour(data),
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # The current hour changes every local hour without new data.
        self._track_hour_rollover()


class HourlyPriceSensor(_BasePriceSensor, SensorEntity):
    """Consumer price for a specific local hour of today."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = f"{CURRENCY_EURO}/kWh"

    def __init__(self, coordinator: PriceDataCoordinator, hour: int) -> None:
        super().__init__(coordinator)
        self._hour = hour

    @property
    def name(self):
        return f"Uurprijs {self._hour:02d}:00"

    @property
    def unique_id(self):
        return f"{DOMAIN}_hour_{self._hour:02d}"

    @property
    def native_value(self):
        data = self._hour_for(self._hour)
        if data is None:
            return None
        return data.consumer_price

    @property
    def extra_state_attributes(self):
        error = self._error
        if error is not None:
            return {"error": error}
        data = self._hour_for(self._hour)
        if data is None:
            return {}
        return {
            ATTR_MARKET_PRICE: data.market_price,
            ATTR_CONSUMER_PRICE: data.consumer_price,
            ATTR_RANK: data.rank,
            ATTR_STARTS_AT: data.starts_at.isoformat(),
        }


class HourlyPriceTomorrowSensor(_BasePriceSensor, SensorEntity):
    """Consumer price for a specific local hour of tomorrow (day-ahead).

    Separate entities instead of attributes on the today sensors:
    automations and dashboards address tomorrow's prices directly, and
    today's sensor semantics stay identical for existing consumers. No
    data (unknown) means the day-ahead market has not published yet; the
    error attribute says so explicitly.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = f"{CURRENCY_EURO}/kWh"

    def __init__(self, coordinator, hour: int) -> None:
        super().__init__(coordinator)
        self._hour = hour

    @property
    def name(self):
        return f"Uurprijs morgen {self._hour:02d}:00"

    @property
    def unique_id(self):
        return f"{DOMAIN}_hour_tomorrow_{self._hour:02d}"

    @property
    def native_value(self):
        data = self._hour_for(self._hour)
        if data is None:
            return None
        return data.consumer_price

    @property
    def extra_state_attributes(self):
        error = self._error
        if error is not None:
            return {"error": error}
        data = self._hour_for(self._hour)
        if data is None:
            return {}
        return {
            ATTR_MARKET_PRICE: data.market_price,
            ATTR_CONSUMER_PRICE: data.consumer_price,
            ATTR_RANK: data.rank,
            ATTR_STARTS_AT: data.starts_at.isoformat(),
        }


class CheapestHoursTomorrowSensor(_BasePriceSensor, SensorEntity):
    """Lists the local hours of tomorrow inside the cheapest X% window.

    Evening planning needs the coming night before midnight: the
    current-hour percentage binary sensors only describe today, whose
    cheap window has usually already passed by evening. This sensor lists
    which hours of tomorrow fall in the cheapest X% window - same floor
    semantics as the percentage sensors (never more than X% of the day's
    intervals), computed purely from the server-provided ranks - so
    automations can plan the coming night the moment the day-ahead market
    publishes. State is a comma-separated list of zero-padded local
    hours; the attributes carry the hours and start timestamps as lists.
    """

    def __init__(self, coordinator, pct: int) -> None:
        super().__init__(coordinator)
        self._pct = pct

    @property
    def name(self):
        return f"Goedkoopste uren morgen ({self._pct}%)"

    @property
    def unique_id(self):
        return f"{DOMAIN}_top_tomorrow_{self._pct}pct"

    def _window(self) -> List[HourData]:
        """Tomorrow hours within the cheapest X%, ordered by start time."""
        return get_cheapest_window(self._hours, self._pct)

    @property
    def native_value(self):
        if self._hours is None:
            return None
        return ", ".join(f"{_local_hour(h):02d}" for h in self._window())

    @property
    def extra_state_attributes(self):
        error = self._error
        if error is not None:
            return {"error": error}
        if self._hours is None:
            return {}
        window = self._window()
        return {
            ATTR_HOURS: [_local_hour(h) for h in window],
            ATTR_STARTS_AT: [h.starts_at.isoformat() for h in window],
            ATTR_PCT: self._pct,
        }
