"""Tests for the thin API client (ADR-0005/0006)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.energy_price_calculator.helpers.api_client import (
    APIError,
    DynamicEnergyPricingClient,
)


def _hour_json(h):
    return {
        "hour": h,
        "starts_at": f"2026-10-02T{h:02d}:00:00Z",
        "market_price": 0.05 + h * 0.001,
        "consumer_price": 0.21 + h * 0.001,
        "rank": h + 1,
    }


def _day_json():
    return {
        "price_date": "2026-10-02",
        "provider": "frank_energie",
        "currency": "EUR",
        "market": "NL",
        "hours": [_hour_json(h) for h in range(24)],
    }


def _mock_session(response_json, status=200):
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=response_json)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session, mock_response


class TestClient:
    def _client(self, session):
        return DynamicEnergyPricingClient(session, "https://api.example.nl", "test-key")

    @pytest.mark.asyncio
    async def test_bearer_header_set(self):
        session, _ = _mock_session(_day_json())
        client = self._client(session)
        await client.get_prices_today()
        session.get.assert_called_once()
        args, kwargs = session.get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert args[0] == "https://api.example.nl/api/v1/prices/today"

    @pytest.mark.asyncio
    async def test_parses_24_hours(self):
        session, _ = _mock_session(_day_json())
        hours = await self._client(session).get_prices_today()
        assert len(hours) == 24
        assert hours[0].market_price == pytest.approx(0.05)
        assert hours[0].consumer_price == pytest.approx(0.21)
        assert hours[0].rank == 1
        assert hours[0].starts_at.tzinfo is not None
        assert hours[0].hour_utc == 0

    @pytest.mark.asyncio
    async def test_incomplete_day_raises(self):
        body = _day_json()
        body["hours"] = body["hours"][:20]
        session, _ = _mock_session(body)
        with pytest.raises(APIError, match="24"):
            await self._client(session).get_prices_today()

    @pytest.mark.asyncio
    async def test_http_error_raises_with_detail(self):
        session, _ = _mock_session({"detail": "Invalid API key"}, status=401)
        with pytest.raises(APIError, match="Invalid API key"):
            await self._client(session).get_prices_today()

    @pytest.mark.asyncio
    async def test_get_me(self):
        session, _ = _mock_session({"provider": "frank_energie", "plan": "free", "key_active": True})
        me = await self._client(session).get_me()
        assert me["provider"] == "frank_energie"
        assert me["key_active"] is True

    @pytest.mark.asyncio
    async def test_current_price(self):
        session, _ = _mock_session({"current": _hour_json(5)})
        data = await self._client(session).get_current_price()
        assert data.hour_utc == 5
        assert data.rank == 6
