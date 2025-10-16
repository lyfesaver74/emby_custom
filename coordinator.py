from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EmbyClient, EmbyAuthError

_LOGGER = logging.getLogger(__name__)

class EmbyUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(self, hass: HomeAssistant, client: EmbyClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Emby sessions",
            update_interval=timedelta(seconds=20),
        )
        self.client = client

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return await self.client.async_get_sessions()
        except EmbyAuthError as err:
            raise UpdateFailed(f"Auth error: {err}") from err
        except Exception as err:
            raise UpdateFailed(err) from err
