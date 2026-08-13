"""Event platform for CodexBar hooks."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hooks import HOOK_EVENT_TYPES, hook_signal


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CodexBar hook event entity."""
    async_add_entities([CodexBarHookEvent(entry)])


class CodexBarHookEvent(EventEntity):
    """Represent transition events emitted by CodexBar hooks."""

    _attr_event_types = list(HOOK_EVENT_TYPES)
    _attr_icon = "mdi:webhook"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the hook event entity."""
        self._entry_id = entry.entry_id
        self._attr_name = "CodexBar Hook"
        self._attr_unique_id = f"{entry.entry_id}_hook"

    async def async_added_to_hass(self) -> None:
        """Subscribe to validated webhook events."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                hook_signal(self._entry_id),
                self._async_handle_hook,
            )
        )

    @callback
    def _async_handle_hook(self, payload: dict[str, Any]) -> None:
        """Record the latest CodexBar hook event."""
        event_type = payload["event"]
        attributes = {key: value for key, value in payload.items() if key != "event"}
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
