"""Harness tests for the config flow: form, validation, errors."""
import aiohttp
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.energy_price_calculator.const import (
    CONF_API_KEY,
    CONF_SERVER_URL,
    DOMAIN,
)

SERVER = "http://localhost:8000"
ME_URL = SERVER + "/api/v1/me"
USER_INPUT = {CONF_SERVER_URL: SERVER, CONF_API_KEY: "test-key"}


async def _start_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


class TestConfigFlow:
    async def test_form_is_shown(self, hass):
        result = await _start_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_valid_key_creates_entry(self, hass, aioclient_mock):
        aioclient_mock.get(ME_URL, json={"provider": "frank_energie", "plan": "free", "key_active": True})
        result = await _start_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=USER_INPUT)
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == USER_INPUT
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    async def test_invalid_key_shows_error(self, hass, aioclient_mock):
        aioclient_mock.get(ME_URL, status=401, json={"detail": "Invalid API key"})
        result = await _start_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=USER_INPUT)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "Invalid API key"
        assert len(hass.config_entries.async_entries(DOMAIN)) == 0

    async def test_unreachable_server_shows_error(self, hass, aioclient_mock):
        aioclient_mock.get(ME_URL, exc=aiohttp.ClientError("connection refused"))
        result = await _start_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=USER_INPUT)
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"]
        assert len(hass.config_entries.async_entries(DOMAIN)) == 0
