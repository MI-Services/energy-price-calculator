#!/usr/bin/env python3
"""Live check: call the thin API client against a running server.

Runs OUTSIDE Home Assistant: it uses the component's api_client (the only
piece without homeassistant.* imports) to fetch real data from the server.

Timestamps are shown twice: UTC (the server's ground truth, ADR-0006) and
local time (what the HA sensors display, converted via dt_util.as_local
inside Home Assistant). This script converts with the HOST's timezone, so
run it on a machine in the same timezone as your HA install to verify the
sensor mapping.

    python scripts/check_api_live.py http://localhost:8000 demo-key-1
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
from energy_price_calculator.helpers.api_client import (  # noqa: E402
    APIError,
    DynamicEnergyPricingClient,
)


def _local(starts_at: datetime) -> str:
    """Local (host timezone) representation of a UTC timestamp."""
    return starts_at.astimezone().strftime("%H:%M")


async def main() -> int:
    if len(sys.argv) < 3:
        print("usage: check_api_live.py <server_url> <api_key>")
        return 2
    server_url, api_key = sys.argv[1], sys.argv[2]

    async with aiohttp.ClientSession() as session:
        client = DynamicEnergyPricingClient(session, server_url, api_key)

        # /me: key valid + provider
        try:
            me = await client.get_me()
        except APIError as exc:
            print(f"FAILED: {exc}")
            return 1
        print("== /me ==")
        print(f"  provider:   {me.get('provider')}")
        print(f"  plan:       {me.get('plan')}")
        print(f"  key active: {me.get('key_active')}")

        # current hour
        current = await client.get_current_price()
        print("\n== current ==")
        print(f"  UTC {_local(current.starts_at) and current.hour_utc:02d}:00  "
              f"market {current.market_price:.4f}  "
              f"consumer {current.consumer_price:.4f}  rank {current.rank}")
        print(f"  local: {_local(current.starts_at)}  "
              f"(HA sensor 'Huidige uurprijs' shows this hour)")

        # today (full table)
        hours = await client.get_prices_today()
        print("\n== today ==")
        print("  UTC  local  market    consumer  rank")
        for h in hours:
            marker = " <-- nu" if h.hour_utc == current.hour_utc else ""
            print(f"  {h.hour_utc:02d}   {_local(h.starts_at)}  {h.market_price:8.4f}  "
                  f"{h.consumer_price:8.4f}  {h.rank:2d}{marker}")

        # tomorrow (404 until the market publishes, ~13:00 NL)
        print("\n== tomorrow ==")
        try:
            tmr = await client.get_prices_tomorrow()
            print(f"  {len(tmr)} hours available")
        except APIError as exc:
            print(f"  not available yet: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
