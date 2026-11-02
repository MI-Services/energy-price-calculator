"""Harness tests for the day-ahead (tomorrow) entities - issue #64.

The day-ahead market publishes around 14:00 local; the component fetches
tomorrow's prices at 14:30 (retry every 30 minutes while they are not
published) so evening planning has the coming night available the same
day. These tests pin that contract against the real HA machinery:
entity registration, the 14:30 schedule, the unpublished retry, the
day-boundary reset and the floor semantics of the cheapest-hours window.
"""
from datetime import datetime, timezone

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.energy_price_calculator.const import (
    CONF_API_KEY,
    CONF_SERVER_URL,
    DOMAIN,
    PERCENT_THRESHOLDS,
)

SERVER = "http://localhost:8000"
TODAY_URL = SERVER + "/api/v1/prices/today"
TOMORROW_URL = SERVER + "/api/v1/prices/tomorrow"


def _day(day, rank=None):
    """Build a valid /prices/{today,tomorrow} response body (ADR-0006)."""
    hours = [
        {
            "hour": h,
            "starts_at": day + "T" + str(h).zfill(2) + ":00:00Z",
            "market_price": 0.05 + h * 0.001,
            "consumer_price": 0.21 + h * 0.001,
            "rank": (rank or (lambda hh: hh + 1))(h),
        }
        for h in range(24)
    ]
    return {
        "price_date": day,
        "provider": "frank_energie",
        "currency": "EUR",
        "market": "NL",
        "hours": hours,
    }


def _today():
    return _day("2026-10-03")


def _tomorrow(rank=None):
    return _day("2026-10-04", rank)


async def _setup(hass, aioclient_mock, today_body, tomorrow_body):
    """Set up the integration with today mocked and tomorrow either
    mocked (dict) or answering 404 not-published (None)."""
    aioclient_mock.get(TODAY_URL, json=today_body)
    if tomorrow_body is None:
        aioclient_mock.get(TOMORROW_URL, status=404, json={"detail": "not published yet"})
    else:
        aioclient_mock.get(TOMORROW_URL, json=tomorrow_body)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERVER_URL: SERVER, CONF_API_KEY: "test-key"},
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _count_tomorrow_calls(aioclient_mock):
    return len([
        c for c in aioclient_mock.mock_calls if "prices/tomorrow" in str(c[1])
    ])


@pytest.fixture
def amsterdam_tz():
    """The fetch schedules run in local time; harness default is US/Pacific."""
    from zoneinfo import ZoneInfo

    from homeassistant.util import dt as dt_util

    original = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
    yield
    dt_util.set_default_time_zone(original)



class TestTomorrowEntities:
    async def test_setup_creates_all_tomorrow_entities(self, hass, aioclient_mock):
        await _setup(hass, aioclient_mock, _today(), _tomorrow())
        # 24 hourly tomorrow sensors
        for h in range(24):
            assert hass.states.get("sensor.uurprijs_morgen_" + str(h).zfill(2) + "_00") is not None
        # one cheapest-hours window sensor per percentage threshold
        for pct in PERCENT_THRESHOLDS:
            assert hass.states.get("sensor.goedkoopste_uren_morgen_" + str(pct)) is not None
        # today entities are unchanged
        assert hass.states.get("sensor.huidige_uurprijs") is not None
        assert hass.states.get("sensor.uurprijs_08_00") is not None

    async def test_today_call_count_unaffected(self, hass, aioclient_mock, freezer):
        """The extra day-ahead fetch must not add /prices/today calls."""
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), _tomorrow())
        today_calls = len([c for c in aioclient_mock.mock_calls if "prices/today" in str(c[1])])
        assert today_calls == 1
        assert _count_tomorrow_calls(aioclient_mock) == 1

    async def test_tomorrow_hourly_sensors_show_day_ahead_prices(self, hass, aioclient_mock, freezer):
        """UTC->local mapping for tomorrow mirrors the today sensors."""
        from zoneinfo import ZoneInfo

        from homeassistant.util import dt as dt_util

        original_time_zone = dt_util.get_default_time_zone()
        dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
        try:
            # 2026-10-03 is CEST (UTC+2): local 22:00 == UTC 20:00
            freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
            await _setup(hass, aioclient_mock, _today(), _tomorrow())
            state = hass.states.get("sensor.uurprijs_morgen_22_00")
            assert state is not None
            assert float(state.state) == 0.21 + 20 * 0.001
        finally:
            dt_util.set_default_time_zone(original_time_zone)

    async def test_cheapest_hours_window_uses_floor_semantics(self, hass, aioclient_mock, freezer):
        """rank*100 <= pct*intervals, identical to the binary sensors.

        With rank(h) = h+1 (24 intervals): 10% covers rank 1-2 (hours
        00-01), 20% covers rank 1-4 (hours 00-03), 50% covers rank 1-12
        (hours 00-11). A rank just above the boundary must stay out:
        20% excludes rank 5 (hour 04).
        """
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), _tomorrow())
        assert hass.states.get("sensor.goedkoopste_uren_morgen_10").state == "00, 01"
        assert hass.states.get("sensor.goedkoopste_uren_morgen_20").state == "00, 01, 02, 03"
        assert hass.states.get("sensor.goedkoopste_uren_morgen_50").state == ", ".join(
            str(h).zfill(2) for h in range(12)
        )
        attrs = hass.states.get("sensor.goedkoopste_uren_morgen_10").attributes
        assert attrs["hours"] == [0, 1]
        assert attrs["pct"] == 10
        assert len(attrs["starts_at"]) == 2

    async def test_unpublished_day_ahead_keeps_entities_visible(self, hass, aioclient_mock, freezer):
        """Before ~14:00 the tomorrow entities exist with a clear error,
        not "unavailable" (the diagnosis must stay visible)."""
        freezer.move_to(datetime(2026, 10, 3, 11, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), None)
        state = hass.states.get("sensor.uurprijs_morgen_08_00")
        assert state is not None
        assert state.state == "unknown"
        assert "not published yet" in state.attributes["error"]
        # the window sensor is unknown as well, with the same diagnosis
        window = hass.states.get("sensor.goedkoopste_uren_morgen_10")
        assert window.state == "unknown"
        assert "not published yet" in window.attributes["error"]


class TestAfternoonSchedule:
    async def test_afternoon_schedule_fetches_tomorrow(self, hass, aioclient_mock, freezer, amsterdam_tz):
        """14:30 local triggers the single day-ahead refresh."""
        # 11:00 UTC = 13:00 local (CEST): tomorrow not published yet
        freezer.move_to(datetime(2026, 10, 3, 11, 0, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), None)
        assert _count_tomorrow_calls(aioclient_mock) == 1  # the initial fetch

        # The market published: 12:30 UTC = 14:30 local fires the schedule
        aioclient_mock.clear_requests()
        aioclient_mock.get(TODAY_URL, json=_today())
        aioclient_mock.get(TOMORROW_URL, json=_tomorrow())
        now = datetime(2026, 10, 3, 12, 30, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_tomorrow_calls(aioclient_mock) == 1
        state = hass.states.get("sensor.uurprijs_morgen_08_00")
        assert state is not None
        assert float(state.state) == 0.21 + 8 * 0.001

    async def test_unpublished_retries_every_30_minutes(self, hass, aioclient_mock, freezer, amsterdam_tz):
        """A 404 answer arms the 30-minute retry until the prices arrive."""
        # 13:00 local (CEST): initial fetch 404s
        freezer.move_to(datetime(2026, 10, 3, 11, 0, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), None)
        assert _count_tomorrow_calls(aioclient_mock) == 1

        # 13:30 local: retry fires, still 404
        now = datetime(2026, 10, 3, 11, 30, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_tomorrow_calls(aioclient_mock) == 2

        # 14:00 local: retry fires again, now the market has published
        aioclient_mock.clear_requests()
        aioclient_mock.get(TODAY_URL, json=_today())
        aioclient_mock.get(TOMORROW_URL, json=_tomorrow())
        now = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_tomorrow_calls(aioclient_mock) == 1
        assert hass.states.get("sensor.goedkoopste_uren_morgen_10").state == "00, 01"

    async def test_hour_rollover_does_not_refetch_tomorrow(self, hass, aioclient_mock, freezer):
        """An hour passing is a local re-render, never a fetch."""
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), _tomorrow())
        assert _count_tomorrow_calls(aioclient_mock) == 1

        now = datetime(2026, 10, 3, 21, 30, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_tomorrow_calls(aioclient_mock) == 1


class TestDayBoundary:
    async def test_new_day_clears_tomorrow_without_refetch(self, hass, aioclient_mock, freezer, amsterdam_tz):
        """At 00:05 local the day-ahead set of yesterday (which describes
        the day that just started) is dropped: unknown, no error, and NO
        refetch - the next fetch waits for the 14:30 schedule."""
        # 20:30 local (CEST): both datasets available
        freezer.move_to(datetime(2026, 10, 3, 18, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _today(), _tomorrow())
        assert float(hass.states.get("sensor.uurprijs_morgen_08_00").state) == 0.21 + 8 * 0.001

        # 00:05 local next day = 22:05 UTC same UTC-day (CEST)
        now = datetime(2026, 10, 3, 22, 5, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.uurprijs_morgen_08_00")
        assert state.state == "unknown"
        # dropped, not an error: the day-ahead set simply is not there yet
        assert "error" not in state.attributes
        assert hass.states.get("sensor.goedkoopste_uren_morgen_10").state == "unknown"
        # no extra tomorrow fetch happened at the day boundary
        assert _count_tomorrow_calls(aioclient_mock) == 1
