"""Shared data coordinator: one API call per day (werksessie 2026-10-04).

/api/v1/prices/today returns the ENTIRE day in a single response, so a
healthy installation needs exactly one call per day. The previous design
fetched per sensor, per hour: 30+ identical calls per tick, 24 ticks per
day - roughly 750 calls/day for data that changes once.

New state != new data: the current-hour switch and the percentage sensors
re-render on the local hour rollover (a timestamp change, no fetch). Only
the day boundary needs a refresh, scheduled by async_setup_entry at 00:05
local time (day-ahead prices are published the previous afternoon, so
the new day is guaranteed available).

No fixed update_interval: refreshes are triggered by the daily schedule
plus a retry timer while the last refresh failed.
"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import List

from homeassistant.core import HomeAssistant
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
