"""Config flow for CodexBar."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_HOST, DOMAIN, SNAPSHOT_PATH


class CannotConnectError(Exception):
    """Raised when the CodexBar server cannot be reached."""


class InvalidAuthError(Exception):
    """Raised when the dashboard token is rejected."""

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, description={"suggested_value": "http://127.0.0.1:8080"}): str,
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

    VERSION = 1

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
                return self.async_create_entry(
                    title=f"CodexBar ({host})",
                    data={CONF_HOST: host, CONF_TOKEN: token},
                )
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, import_data: dict[str, Any]):
        """Import a `codexbar:` entry from configuration.yaml."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        host = normalize_host(import_data[CONF_HOST])
        token = normalize_token(import_data[CONF_TOKEN])
        return self.async_create_entry(
            title=f"CodexBar ({host})",
            data={CONF_HOST: host, CONF_TOKEN: token},
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
        except InvalidAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnectError from err
