"""Configuration flow for the energy price calculator (thin client).

The user configures the server URL and API key; the flow validates them
against /api/v1/me before saving (ADR-0006). Uses HA's managed client
session (async_get_clientsession) so no sessions leak on reload.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_SERVER_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def _validate(self, server_url: str, api_key: str) -> tuple[bool, str]:
        """Validate server URL + API key against /api/v1/me."""
        url = server_url.rstrip("/") + "/api/v1/me"
        try:
            async with asyncio.timeout(10):
                session = async_get_clientsession(self.hass)
                async with session.get(
                    url, headers={"Authorization": f"Bearer {api_key}"}
                ) as response:
                    if response.status == 200:
                        return True, ""
                    body = await response.json(content_type=None)
                    detail = body.get("detail", "") if isinstance(body, dict) else ""
                    return False, detail or f"HTTP {response.status}"
        except (aiohttp.ClientError, TimeoutError) as exc:
            return False, f"Cannot reach server: {exc}"

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            ok, error = await self._validate(
                user_input[CONF_SERVER_URL], user_input[CONF_API_KEY]
            )
            if ok:
                return self.async_create_entry(
                    title="Dynamic Energy Pricing",
                    data=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER_URL): str,
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SERVER_URL,
                        default=self.config_entry.data.get(CONF_SERVER_URL, ""),
                    ): str,
                    vol.Optional(
                        CONF_API_KEY,
                        default=self.config_entry.data.get(CONF_API_KEY, ""),
                    ): str,
                }
            ),
        )
