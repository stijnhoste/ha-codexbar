"""DataUpdateCoordinator for CodexBar.

Polls `codexbar serve`'s normalized `/dashboard/v1/snapshot` endpoint, which
returns a generic, display-oriented payload covering every provider CodexBar
supports (no per-provider code needed here).
"""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, SNAPSHOT_PATH

_LOGGER = logging.getLogger(__name__)


class CodexBarCoordinator(DataUpdateCoordinator):
    """Fetch and cache the CodexBar dashboard snapshot."""

    def __init__(self, hass: HomeAssistant, host: str, token: str) -> None:
        """Initialize the coordinator."""
        self.host = host.rstrip("/")
        self.token = token
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        """Fetch the latest snapshot from codexbar serve."""
        url = f"{self.host}{SNAPSHOT_PATH}"
        headers = {"Authorization": f"Bearer {self.token}"}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 401:
                    raise UpdateFailed("Invalid dashboard token (HTTP 401)")
                resp.raise_for_status()
                return await resp.json()
        except UpdateFailed:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching CodexBar data: {err}") from err
