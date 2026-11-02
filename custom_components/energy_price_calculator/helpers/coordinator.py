"""Shared data coordinators: one API call per dataset per day.

/api/v1/prices/today returns the ENTIRE day in a single response, so a
healthy installation needs exactly one call per day per dataset. Every
entity reads the shared coordinators; nothing fetches on its own.

New state != new data: the current-hour switch and the percentage sensors
re-render on the local hour rollover (a timestamp change, no fetch). Only
the day boundaries need a refresh, scheduled by async_setup_entry:
- today at 00:05 local (the new day is guaranteed available),
- tomorrow at 14:30 local (the day-ahead market publishes around 14:00;
  until then the fetch answers 404 and the retry timer keeps trying).

Two coordinators, one per dataset: today's behaviour stays identical for
existing consumers, while tomorrow's prices become available the same
afternoon for evening planning.

No fixed update_interval: refreshes are triggered by the daily schedules
plus a retry timer while the last refresh failed.
"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import List

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import APIError, DynamicEnergyPricingClient, HourData

_LOGGER = logging.getLogger(__name__)

RETRY_INTERVAL = timedelta(minutes=30)


class PriceDataCoordinator(DataUpdateCoordinator):
    """Fetches today's prices once; data is the List[HourData] (None on failure)."""

    def __init__(self, hass: HomeAssistant, client: DynamicEnergyPricingClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="energy_price_calculator",
            update_interval=None,  # refreshes are schedule-driven, not interval-driven
        )
        self._client = client

    async def _async_update_data(self) -> List[HourData]:
        try:
            return await self._client.get_prices_today()
        except APIError as exc:
            raise UpdateFailed(str(exc)) from exc


class TomorrowPriceCoordinator(DataUpdateCoordinator):
    """Fetches tomorrow's day-ahead prices once they are published.

    The day-ahead market publishes around 14:00 local time, so the daily
    schedule (see async_setup_entry) refreshes this coordinator at 14:30
    with the same 30-minute retry while the prices are not available yet
    (the server answers 404 until publication). The fetch is idempotent:
    the server serves a cache, re-fetching the same day simply overwrites
    the same data.

    Day boundary: the 00:05 today-refresh also calls async_reset(), so the
    previous day-ahead set - which describes the day that just started -
    is dropped instead of lingering as stale "tomorrow" data.
    """

    def __init__(self, hass: HomeAssistant, client: DynamicEnergyPricingClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="energy_price_calculator_tomorrow",
            update_interval=None,  # refreshes are schedule-driven, not interval-driven
        )
        self._client = client

    async def _async_update_data(self) -> List[HourData]:
        try:
            return await self._client.get_prices_tomorrow()
        except APIError as exc:
            if "404" in str(exc):
                raise UpdateFailed(
                    "Tomorrow's prices are not published yet "
                    "(the day-ahead market publishes around 14:00)"
                ) from exc
            raise UpdateFailed(str(exc)) from exc

    @callback
    def async_reset(self) -> None:
        """Drop the day-ahead set at the day boundary (new day != new data)."""
        self.data = None
        self.async_update_listeners()
