# custom_components/emby_custom/__init__.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Awaitable, Dict, List
import logging
_LOGGER = logging.getLogger(__name__)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_OPTIONS
from .api import EmbyClient



PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """YAML setup not used for this custom integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Removed extra logging
    """Set up Emby (Custom) from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data.get("host")
    port = int(entry.data.get("port", DEFAULT_PORT))
    use_ssl = bool(entry.data.get("ssl", False))
    api_key = entry.data.get("api_key", "")

    session = async_get_clientsession(hass)
    client = EmbyClient(session=session, host=host, port=port, use_ssl=use_ssl, api_key=api_key)

    # Merge defaults into options on first setup if options are empty
    if not entry.options:
        hass.config_entries.async_update_entry(entry, options={**DEFAULT_OPTIONS})

    # ---------------- Sessions coordinator (fast) ----------------
    async def _async_update_sessions() -> list[dict]:
        return await client.async_get_sessions()

    sessions_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_sessions",
        update_method=_async_update_sessions,
        update_interval=timedelta(seconds=10),
    )

    # ---------------- Library coordinator (slower) ----------------
    async def _safe(label: str, fn: Callable[..., Awaitable[List[dict]]], *args) -> List[dict]:
        try:
            data = await fn(*args)
            return data or []
        except Exception:
            return []

    async def _async_update_library() -> Dict[str, List[dict]]:
        # Get standard library content
        return {
            "upcoming_episodes": await _safe("upcoming_episodes", client.async_get_upcoming_episodes, 5),
            "latest_movies": await _safe("latest_movies", client.async_get_latest_movies, 5),
            "latest_episodes": await _safe("latest_episodes", client.async_get_latest_episodes, 5),
        }

    library_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_library",
        update_method=_async_update_library,
        update_interval=timedelta(minutes=15),
    )

    # Make coordinators available to platforms immediately.
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": sessions_coordinator,
        "library_coordinator": library_coordinator,
    }

    # Kick off initial refreshes (don’t block setup)
    try:
        await sessions_coordinator.async_refresh()
    except Exception:
        pass

    try:
        await library_coordinator.async_refresh()
    except Exception:
        pass

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry cleanly."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data.get(DOMAIN, {})
        data.pop(entry.entry_id, None)
        if not data:
            hass.data.pop(DOMAIN, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle entry reloads."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
