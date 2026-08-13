"""Inbound webhook support for CodexBar hook events."""

from __future__ import annotations

from http import HTTPStatus
import json
import logging

from aiohttp.hdrs import METH_POST
from aiohttp.web import Request, Response, json_response

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN
from .coordinator import CodexBarCoordinator
from .hooks import (
    EVENT_HOOK,
    MAX_HOOK_PAYLOAD_BYTES,
    HookValidationError,
    hook_signal,
    validate_hook_payload,
)

_LOGGER = logging.getLogger(__name__)


def async_register_hook_webhook(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: CodexBarCoordinator,
) -> None:
    """Register the inbound webhook for one CodexBar config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def async_handle_hook(
        hass: HomeAssistant, _webhook_id: str, request: Request
    ) -> Response:
        if (
            request.content_length is not None
            and request.content_length > MAX_HOOK_PAYLOAD_BYTES
        ):
            return json_response(
                {"error": "payload_too_large"},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )

        raw_payload = await request.content.read(MAX_HOOK_PAYLOAD_BYTES + 1)
        if len(raw_payload) > MAX_HOOK_PAYLOAD_BYTES:
            return json_response(
                {"error": "payload_too_large"},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )

        try:
            payload = validate_hook_payload(json.loads(raw_payload))
        except (HookValidationError, UnicodeDecodeError, json.JSONDecodeError) as err:
            _LOGGER.debug("Rejected invalid CodexBar hook payload: %s", err)
            return json_response(
                {"error": "invalid_payload"}, status=HTTPStatus.BAD_REQUEST
            )

        async_dispatcher_send(hass, hook_signal(entry.entry_id), payload)
        hass.bus.async_fire(EVENT_HOOK, payload)
        hass.async_create_task(coordinator.async_request_refresh())
        return json_response({"status": "accepted"}, status=HTTPStatus.ACCEPTED)

    webhook.async_register(
        hass,
        DOMAIN,
        entry.title,
        webhook_id,
        async_handle_hook,
        allowed_methods=[METH_POST],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
