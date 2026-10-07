"""Harness tests for the sensor platform: real HA runtime, mocked server.

Covers what the unit tests + CLI check cannot: entity registration, the
UTC -> local hour mapping (with a frozen clock and a non-UTC timezone),
error behaviour, and the one-call-per-day contract - all against the
actual Home Assistant sensor machinery.
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
)

SERVER = "http://localhost:8000"
TODAY_URL = SERVER + "/api/v1/prices/today"


def _day(day="2026-10-03", price=None, consumer=None, rank=None):
    """Build a valid /prices/today response body (ADR-0006 contract)."""
    hours = []
    for h in range(24):
        hours.append({
            "hour": h,
            "starts_at": day + "T" + str(h).zfill(2) + ":00:00Z",
            "market_price": (price or (lambda hh: 0.05 + hh * 0.001))(h),
            "consumer_price": (consumer or (lambda hh: 0.21 + hh * 0.001))(h),
            "rank": (rank or (lambda hh: hh + 1))(h),
        })
    return {"price_date": day, "provider": "frank_energie", "currency": "EUR", "market": "NL", "hours": hours}


async def _setup(hass, aioclient_mock, day_body):
    aioclient_mock.get(TODAY_URL, json=day_body)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERVER_URL: SERVER, CONF_API_KEY: "test-key"},
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _count_today_calls(aioclient_mock):
    return len([
        c for c in aioclient_mock.mock_calls if "prices/today" in str(c[1])
    ])


class TestSensorSetup:
    async def test_setup_creates_all_sensor_entities(self, hass, aioclient_mock):
        await _setup(hass, aioclient_mock, _day())
        # 1 current + 24 hourly price sensors
        assert hass.states.get("sensor.huidige_uurprijs") is not None
        for h in range(24):
            assert hass.states.get("sensor.uurprijs_" + str(h).zfill(2) + "_00") is not None

    async def test_api_errors_do_not_crash_setup(self, hass, aioclient_mock):
        import aiohttp
        aioclient_mock.get(TODAY_URL, exc=aiohttp.ClientError("server down"))
        await _setup(hass, aioclient_mock, None)
        state = hass.states.get("sensor.huidige_uurprijs")
        assert state is not None  # entity exists even without data
        assert state.state == "unknown"
        assert "error" in state.attributes


class TestCurrentHourSensor:
    async def test_shows_current_hour_consumer_price(self, hass, aioclient_mock, freezer):
        # Freeze the clock at 20:30 UTC: current hour is 20
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day())
        state = hass.states.get("sensor.huidige_uurprijs")
        assert state is not None
        assert float(state.state) == pytest.approx(0.21 + 20 * 0.001)
        assert state.attributes["rank"] == 21
        assert state.attributes["market_price"] == pytest.approx(0.05 + 20 * 0.001)


class TestUtcToLocalMapping:
    async def test_utc_timezone_maps_identity(self, hass, aioclient_mock, freezer):
        """With UTC configured, local hour == API hour."""
        from homeassistant.util import dt as dt_util

        original_time_zone = dt_util.get_default_time_zone()
        dt_util.set_default_time_zone(dt_util.UTC)
        try:
            freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
            await _setup(hass, aioclient_mock, _day())
            # Local sensor Uurprijs 20:00 carries the API hour-20 data
            assert float(hass.states.get("sensor.uurprijs_20_00").state) == pytest.approx(0.21 + 20 * 0.001)
        finally:
            dt_util.set_default_time_zone(original_time_zone)

    async def test_amsterdam_timezone_shifts_hours(self, hass, aioclient_mock, freezer):
        """Europe/Amsterdam is UTC+2 on 2026-10-03 (CEST).

        The API hour starting 20:00 UTC is locally 22:00, so the local
        Uurprijs 22:00 sensor must carry the UTC-20 entry. This pins the
        UTC -> local conversion that HA shows the user.
        """
        from zoneinfo import ZoneInfo

        from homeassistant.util import dt as dt_util

        original_time_zone = dt_util.get_default_time_zone()
        dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
        try:
            freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
            await _setup(hass, aioclient_mock, _day())
            # local 22:00 == UTC 20:00 entry
            assert float(hass.states.get("sensor.uurprijs_22_00").state) == pytest.approx(0.21 + 20 * 0.001)
            # and local 20:00 == UTC 18:00 entry
            assert float(hass.states.get("sensor.uurprijs_20_00").state) == pytest.approx(0.21 + 18 * 0.001)
            # current-hour sensor also follows local time
            assert float(hass.states.get("sensor.huidige_uurprijs").state) == pytest.approx(0.21 + 20 * 0.001)
        finally:
            dt_util.set_default_time_zone(original_time_zone)


@pytest.fixture
def amsterdam_tz():
    """The 00:05 schedule is local time; the harness default is US/Pacific."""
    from zoneinfo import ZoneInfo

    from homeassistant.util import dt as dt_util

    original = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
    yield
    dt_util.set_default_time_zone(original)


class TestDailySchedule:
    """The one-call-per-day contract (werksessie 2026-10-04)."""

    async def test_setup_makes_single_api_call(self, hass, aioclient_mock, freezer):
        """Regression: the old per-sensor polling design fired 30+ identical
        /prices/today calls per tick; the shared coordinator must make
        exactly ONE call for the whole setup."""
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day())
        assert _count_today_calls(aioclient_mock) == 1

    async def test_no_extra_call_on_hour_rollover(self, hass, aioclient_mock, freezer):
        """State changes on the hour boundary (
current-hour sensor,
        percentage sensors) must be a local re-render: an hour passing
        does NOT trigger a fetch."""
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day())
        assert _count_today_calls(aioclient_mock) == 1

        # Move into the next hour and let HA process the time-change event
        now = datetime(2026, 10, 3, 21, 30, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_today_calls(aioclient_mock) == 1

    async def test_new_day_triggers_exactly_one_refresh(self, hass, aioclient_mock, freezer):
        """The 00:05 local schedule fires the single daily refresh."""
        from zoneinfo import ZoneInfo

        from homeassistant.util import dt as dt_util

        original_time_zone = dt_util.get_default_time_zone()
        dt_util.set_default_time_zone(ZoneInfo("Europe/Amsterdam"))
        try:
            # 20:30 local = 18:30 UTC on 2026-10-03
            freezer.move_to(datetime(2026, 10, 3, 18, 30, 0, tzinfo=timezone.utc))
            await _setup(hass, aioclient_mock, _day())
            assert _count_today_calls(aioclient_mock) == 1

            # 00:05 local next day = 22:05 UTC same UTC-day (CEST)
            now = datetime(2026, 10, 3, 22, 5, 0, tzinfo=timezone.utc)
            freezer.move_to(now)
            async_fire_time_changed(hass, now)
            await hass.async_block_till_done()
            assert _count_today_calls(aioclient_mock) == 2
        finally:
            dt_util.set_default_time_zone(original_time_zone)

    async def test_failed_refresh_retries(self, hass, aioclient_mock, freezer, amsterdam_tz):
        """A failed daily refresh arms the 30-minute retry until success."""
        import aiohttp

        # First call (setup) succeeds
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day())
        assert _count_today_calls(aioclient_mock) == 1

        # Daily refresh fails
        aioclient_mock.clear_requests()
        aioclient_mock.get(TODAY_URL, exc=aiohttp.ClientError("server down"))
        now = datetime(2026, 10, 3, 22, 5, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_today_calls(aioclient_mock) == 1  # failed, will retry

        # Retry succeeds
        aioclient_mock.clear_requests()
        aioclient_mock.get(TODAY_URL, json=_day())
        now = datetime(2026, 10, 3, 22, 35, 0, tzinfo=timezone.utc)
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert _count_today_calls(aioclient_mock) == 1
