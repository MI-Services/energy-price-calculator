"""Harness tests for the binary_sensor platform (cheapest X% of the day)."""
from datetime import datetime, timezone

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_price_calculator.const import (
    CONF_API_KEY,
    CONF_SERVER_URL,
    DOMAIN,
    PERCENT_THRESHOLDS,
)

SERVER = "http://localhost:8000"
TODAY_URL = SERVER + "/api/v1/prices/today"


def _day(rank):
    hours = [
        {
            "hour": h,
            "starts_at": "2026-10-03T" + str(h).zfill(2) + ":00:00Z",
            "market_price": 0.05 + h * 0.001,
            "consumer_price": 0.21 + h * 0.001,
            "rank": rank(h),
        }
        for h in range(24)
    ]
    return {"price_date": "2026-10-03", "provider": "frank_energie", "currency": "EUR", "market": "NL", "hours": hours}


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


class TestBinarySensors:
    async def test_entities_have_binary_sensor_prefix(self, hass, aioclient_mock, freezer):
        """Regression: binary sensors registered via the sensor platform would
        get a sensor.* prefix and break binary_sensor.* automations."""
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day(lambda h: h + 1))
        for pct in PERCENT_THRESHOLDS:
            assert hass.states.get("binary_sensor.goedkoopste_" + str(pct) + "_van_de_dag") is not None
            assert hass.states.get("sensor.goedkoopste_" + str(pct) + "_van_de_dag") is None

    async def test_top_n_on_when_rank_at_or_below_threshold(self, hass, aioclient_mock, freezer):
        # Current hour (20 UTC) has rank 2 of 24 (8.3%): ON from 10% upward
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day(lambda h: 2 if h == 20 else 24))
        assert hass.states.get("binary_sensor.goedkoopste_10_van_de_dag").state == "on"
        assert hass.states.get("binary_sensor.goedkoopste_20_van_de_dag").state == "on"
        assert hass.states.get("binary_sensor.goedkoopste_50_van_de_dag").state == "on"
        assert hass.states.get("binary_sensor.goedkoopste_10_van_de_dag").attributes["rank"] == 2

    async def test_all_off_when_rank_above_thresholds(self, hass, aioclient_mock, freezer):
        # Current hour has rank 21 of 24 (87.5%): 10-80% OFF, 90% ON
        # (21*100 <= 24*90, but not <= 24*80). Most expensive hour (rank 24,
        # 100%) leaves every threshold OFF.
        freezer.move_to(datetime(2026, 10, 3, 20, 30, 0, tzinfo=timezone.utc))
        await _setup(hass, aioclient_mock, _day(lambda h: 21 if h == 20 else h + 1))
        for pct in PERCENT_THRESHOLDS:
            expected = "on" if pct >= 90 else "off"
            assert hass.states.get("binary_sensor.goedkoopste_" + str(pct) + "_van_de_dag").state == expected
