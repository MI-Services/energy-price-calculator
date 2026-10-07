"""Home Assistant Dynamic Energy Price Calculator Component."""
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_change

from .const import CONF_API_KEY, CONF_SERVER_URL, DOMAIN
from .helpers.api_client import DynamicEnergyPricingClient
from .helpers.coordinator import RETRY_INTERVAL, PriceDataCoordinator

# The component registers two platforms: the price sensors (sensor) and the
# cheapest-X% indicators (binary_sensor). Binary sensors MUST be registered
# via the binary_sensor platform: registering them through the sensor
# platform would give them a sensor.* entity_id prefix, breaking automations
# that target binary_sensor.* (found during harness testing).
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the energy price calculator from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    server_url = entry.options.get(CONF_SERVER_URL, entry.data.get(CONF_SERVER_URL))
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY))
    client = DynamicEnergyPricingClient(async_get_clientsession(hass), server_url, api_key)

    coordinator = PriceDataCoordinator(hass, client)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # --- Schedule: one refresh per day, retry while the last one failed ---
    retry_unsub = None

    @callback
    def _retry(_now):
        nonlocal retry_unsub
        retry_unsub = None
        hass.async_create_task(coordinator.async_request_refresh())

    @callback
    def _on_coordinator_update():
        # Success cancels any pending retry; failure arms one (idempotent:
        # only one retry timer runs at a time).
        nonlocal retry_unsub
        if coordinator.last_update_success:
            if retry_unsub is not None:
                retry_unsub()
                retry_unsub = None
        elif retry_unsub is None:
            retry_unsub = async_call_later(hass, RETRY_INTERVAL, _retry)

    @callback
    def _daily_refresh(_now):
        hass.async_create_task(coordinator.async_request_refresh())

    unsub_listener = coordinator.async_add_listener(_on_coordinator_update)
    unsub_daily = async_track_time_change(hass, _daily_refresh, hour=0, minute=5, second=0)
    entry.async_on_unload(unsub_listener)
    entry.async_on_unload(unsub_daily)

    @callback
    def _cancel_retry():
        if retry_unsub is not None:
            retry_unsub()

    entry.async_on_unload(_cancel_retry)

    # Initial fetch. Failures do NOT abort setup: entities surface the
    # error via their attributes and the retry timer takes over.
    await coordinator.async_refresh()

    # Home Assistant moved from async_forward_entry_setup to async_forward_entry_setups.
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
