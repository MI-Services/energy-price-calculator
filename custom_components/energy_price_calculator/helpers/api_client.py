"""Thin API client for the Dynamic Energy Pricing server (ADR-0005, ADR-0006).

This component performs NO price calculations: market prices, consumer prices
and ranks all come from the server API. The client only fetches, parses and
converts (UTC -> local happens in sensor.py via HA's dt utility).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List

import aiohttp

_LOGGER = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when the server API cannot be reached or returns an error."""


@dataclass
class HourData:
    """One hour of prices as served by the API (timestamps in UTC)."""

    hour_utc: int
    starts_at: datetime  # tz-aware UTC
    market_price: float
    consumer_price: float
    rank: int  # 1 = cheapest hour of the day, 24 = most expensive


class DynamicEnergyPricingClient:
    """Minimal client for /api/v1 (ADR-0006)."""

    def __init__(self, session: aiohttp.ClientSession, server_url: str, api_key: str) -> None:
        self._session = session
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._server_url}{path}"
        try:
            async with self._session.get(
                url, headers={"Authorization": f"Bearer {self._api_key}"}
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200:
                    detail = body.get("detail") if isinstance(body, dict) else body
                    raise APIError(f"{path} returned {response.status}: {detail}")
                return body
        except aiohttp.ClientError as exc:
            raise APIError(f"Cannot reach {url}: {exc}") from exc
        except TimeoutError as exc:
            raise APIError(f"Timeout calling {url}") from exc

    async def get_me(self) -> dict[str, Any]:
        """Fetch /api/v1/me (used by the config flow to validate the key)."""
        return await self._get("/api/v1/me")

    async def get_prices_today(self) -> List[HourData]:
        """Fetch today's prices (24 hours; API returns 503 if unavailable)."""
        return self._parse_day(await self._get("/api/v1/prices/today"))

    async def get_prices_tomorrow(self) -> List[HourData]:
        """Fetch tomorrow's prices; raises APIError (404) until published."""
        return self._parse_day(await self._get("/api/v1/prices/tomorrow"))

    async def get_current_price(self) -> HourData:
        """Fetch the current hour's price."""
        body = await self._get("/api/v1/prices/current")
        return self._parse_hour(body["current"])

    @staticmethod
    def _parse_hour(data: dict[str, Any]) -> HourData:
        starts_at = datetime.fromisoformat(str(data["starts_at"]).replace("Z", "+00:00"))
        if starts_at.tzinfo is None:
            raise APIError(f"API returned naive timestamp: {data['starts_at']}")
        return HourData(
            hour_utc=int(data["hour"]),
            starts_at=starts_at,
            market_price=float(data["market_price"]),
            consumer_price=float(data["consumer_price"]),
            rank=int(data["rank"]),
        )

    @classmethod
    def _parse_day(cls, body: dict[str, Any]) -> List[HourData]:
        hours = [cls._parse_hour(h) for h in body.get("hours", [])]
        if len(hours) != 24:
            raise APIError(f"Expected 24 hours, got {len(hours)}")
        return hours
