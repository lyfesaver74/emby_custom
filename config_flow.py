from __future__ import annotations

from typing import Any
from asyncio import TimeoutError
from aiohttp import ClientError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession  # <-- import this

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_API_KEY,
    CONF_VERIFY_SSL,
    DEFAULT_OPTIONS,
    OPT_ENABLE_RECORDINGS,
    OPT_ENABLE_ACTIVE_STREAMS,
    OPT_ENABLE_MULTISESSION,
    OPT_ENABLE_BANDWIDTH,
    OPT_ENABLE_TRANSCODING,
    OPT_ENABLE_SERVER_STATS,
    OPT_ENABLE_LIBRARY_STATS,
    OPT_ENABLE_LATEST_MOVIES,
    OPT_ENABLE_LATEST_EPISODES,
    OPT_ENABLE_UPCOMING_EPISODES,
)
from .api import EmbyClient, EmbyAuthError

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Optional(CONF_SSL, default=False): bool,
    vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    vol.Required(CONF_API_KEY): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # ✅ Correct way to get the session in a config flow:
            session = async_get_clientsession(
                self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, True)
            )

            client = EmbyClient(
                session=session,
                host=user_input[CONF_HOST],
                port=user_input.get(CONF_PORT, DEFAULT_PORT),
                use_ssl=user_input.get(CONF_SSL, False),
                api_key=user_input[CONF_API_KEY],
            )

            try:
                info = await client.async_get_system_info()
            except EmbyAuthError:
                errors["base"] = "invalid_auth"
            except (ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                unique_id = info.get("Id") or f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("ServerName", "Emby"),
                    data=user_input,
                )

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            # Save options
            return self.async_create_entry(title="Options", data=user_input)

        options = {**DEFAULT_OPTIONS, **(self.config_entry.options or {})}

        schema = vol.Schema({
            vol.Optional(OPT_ENABLE_RECORDINGS, default=options.get(OPT_ENABLE_RECORDINGS, True)): bool,
            vol.Optional(OPT_ENABLE_ACTIVE_STREAMS, default=options.get(OPT_ENABLE_ACTIVE_STREAMS, True)): bool,
            vol.Optional(OPT_ENABLE_MULTISESSION, default=options.get(OPT_ENABLE_MULTISESSION, True)): bool,
            vol.Optional(OPT_ENABLE_BANDWIDTH, default=options.get(OPT_ENABLE_BANDWIDTH, True)): bool,
            vol.Optional(OPT_ENABLE_TRANSCODING, default=options.get(OPT_ENABLE_TRANSCODING, True)): bool,
            vol.Optional(OPT_ENABLE_SERVER_STATS, default=options.get(OPT_ENABLE_SERVER_STATS, True)): bool,
            vol.Optional(OPT_ENABLE_LIBRARY_STATS, default=options.get(OPT_ENABLE_LIBRARY_STATS, True)): bool,
            vol.Optional(OPT_ENABLE_LATEST_MOVIES, default=options.get(OPT_ENABLE_LATEST_MOVIES, True)): bool,
            vol.Optional(OPT_ENABLE_LATEST_EPISODES, default=options.get(OPT_ENABLE_LATEST_EPISODES, True)): bool,
            vol.Optional(OPT_ENABLE_UPCOMING_EPISODES, default=options.get(OPT_ENABLE_UPCOMING_EPISODES, True)): bool,
        })

        return self.async_show_form(step_id="init", data_schema=schema)

