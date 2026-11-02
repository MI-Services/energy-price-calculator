"""Home Assistant Dynamic Energy Price Calculator Component."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_change

from .const import (
    CONF_API_KEY,
    CONF_SERVER_URL,
    COORD_TODAY,
    COORD_TOMORROW,
    DOMAIN,
    TODAY_FETCH_HOUR,
    TODAY_FETCH_MINUTE,
    TOMORROW_FETCH_HOUR,
    TOMORROW_FETCH_MINUTE,
)
from .helpers.api_client import DynamicEnergyPricingClient
from .helpers.coordinator import (
    RETRY_INTERVAL,
    PriceDataCoordinator,
    TomorrowPriceCoordinator,
)

# The component registers two platforms: the price sensors (sensor) and the
# cheapest-X% indicators (binary_sensor). Binary sensors MUST be registered
# via the binary_sensor platform: registering them through the sensor
# platform would give them a sensor.* entity_id prefix, breaking
# automations that target binary_sensor.*.
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _bind_refresh_schedule(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
    fetch_hour: int,
    fetch_minute: int,
    on_scheduled_refresh=None,
) -> None:
    """Bind one coordinator to a daily refresh moment + failure retry.

    Refreshes once per day at (fetch_hour, fetch_minute) LOCAL time and arms
    a single 30-minute retry timer while the last refresh failed (idempotent:
    a success cancels any pending retry). Callers must bind BEFORE the
    initial refresh so a failing setup fetch arms the retry.
    """
    retry_unsub = None

    @callback
    def _retry(_now):
        nonlocal retry_unsub
        retry_unsub = None
        hass.async_create_task(coordinator.async_request_refresh())

    @callback
    def _on_coordinator_update():
        # Success cancels any pending retry; failure arms one.
        nonlocal retry_unsub
        if coordinator.last_update_success:
            if retry_unsub is not None:
                retry_unsub()
                retry_unsub = None
        elif retry_unsub is None:
            retry_unsub = async_call_later(hass, RETRY_INTERVAL, _retry)

    @callback
    def _scheduled_refresh(_now):
        if on_scheduled_refresh is not None:
            on_scheduled_refresh()
        hass.async_create_task(coordinator.async_request_refresh())

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))
    entry.async_on_unload(
        async_track_time_change(
            hass,
            _scheduled_refresh,
            hour=fetch_hour,
            minute=fetch_minute,
            second=0,
        )
    )

    @callback
    def _cancel_retry():
        nonlocal retry_unsub
        if retry_unsub is not None:
            retry_unsub()
            retry_unsub = None

    entry.async_on_unload(_cancel_retry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the energy price calculator from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    server_url = entry.options.get(CONF_SERVER_URL, entry.data.get(CONF_SERVER_URL))
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY))
    client = DynamicEnergyPricingClient(async_get_clientsession(hass), server_url, api_key)

    today = PriceDataCoordinator(hass, client)
    tomorrow = TomorrowPriceCoordinator(hass, client)
    hass.data[DOMAIN][entry.entry_id] = {COORD_TODAY: today, COORD_TOMORROW: tomorrow}

    # Two fetch moments per day: today just after midnight, and tomorrow
    # (day-ahead, published by the market around 14:00) in the afternoon so
    # evening planning has the coming night available the same day. The day
    # boundary also drops yesterday's day-ahead set so it can never show as
    # stale "tomorrow" data.
    _bind_refresh_schedule(
        hass, entry, today, TODAY_FETCH_HOUR, TODAY_FETCH_MINUTE,
        on_scheduled_refresh=tomorrow.async_reset,
    )
    _bind_refresh_schedule(hass, entry, tomorrow, TOMORROW_FETCH_HOUR, TOMORROW_FETCH_MINUTE)

    # Initial fetch of both datasets. Failures do NOT abort setup: entities
    # surface the error via their attributes and the retry timers take over.
    # Before ~14:00 the tomorrow fetch answers 404 - not an error, just not
    # published yet; its retry keeps trying until the market publishes.
    await today.async_refresh()
    await tomorrow.async_refresh()

    # async_forward_entry_setups is the batch variant; older HA versions
    # only support per-platform setup.
    if hasattr(hass.config_entries, "async_forward_entry_setups"):
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    else:
        for platform in PLATFORMS:
            await hass.config_entries.async_forward_entry_setup(entry, platform)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
