"""Config flow for CodexBar."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_TOKEN, CONF_WEBHOOK_ID
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, DOMAIN, SNAPSHOT_PATH
from .snapshot import SnapshotValidationError, validate_snapshot


class CannotConnectError(Exception):
    """Raised when the CodexBar server cannot be reached."""


class InvalidAuthError(Exception):
    """Raised when the dashboard token is rejected."""


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_HOST,
            description={"suggested_value": "http://127.0.0.1:8080"},
        ): str,
        vol.Required(CONF_TOKEN): str,
    }
)


def normalize_host(host: str) -> str:
    """Strip trailing slashes and add a scheme if missing."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def normalize_token(token: str) -> str:
    """Allow the user to paste either a bare token or a `Bearer <token>` string."""
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


class CodexBarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CodexBar."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            token = normalize_token(user_input[CONF_TOKEN])
            try:
                await self._validate(host, token)
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            else:
                webhook_id = webhook.async_generate_id()
                return self.async_create_entry(
                    title=f"CodexBar ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_TOKEN: token,
                        CONF_WEBHOOK_ID: webhook_id,
                    },
                    description_placeholders={
                        "webhook_url": webhook.async_generate_url(self.hass, webhook_id)
                    },
                )
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def _validate(self, host: str, token: str) -> None:
        """Check reachability and the token against /dashboard/v1/snapshot."""
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with session.get(
                f"{host}{SNAPSHOT_PATH}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    raise InvalidAuthError
                resp.raise_for_status()
                validate_snapshot(await resp.json())
        except InvalidAuthError:
            raise
        except (
            aiohttp.ClientError,
            SnapshotValidationError,
            TimeoutError,
            ValueError,
        ) as err:
            raise CannotConnectError from err

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow that displays the hook URL."""
        return CodexBarOptionsFlow(config_entry)


class CodexBarOptionsFlow(OptionsFlow):
    """Show the generated CodexBar hook URL."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow for one config entry."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Display the webhook URL without exposing it as entity state."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        webhook_url = webhook.async_generate_url(
            self.hass,
            self._config_entry.data[CONF_WEBHOOK_ID],
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={"webhook_url": webhook_url},
        )
