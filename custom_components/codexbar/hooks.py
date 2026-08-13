"""CodexBar hook event contract helpers."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

EVENT_HOOK = "codexbar_hook"
HOOK_EVENT_TYPES = (
    "quota_low",
    "quota_reached",
    "quota_reset",
    "provider_unavailable",
    "provider_recovered",
    "refresh_failed",
)
MAX_HOOK_PAYLOAD_BYTES = 4096

_OPTIONAL_STRING_FIELDS = ("account", "window", "status")
_OPTIONAL_NUMBER_FIELDS = ("usagePercent", "used", "limit")


class HookValidationError(ValueError):
    """Raised when a CodexBar hook payload is invalid."""


def _validate_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HookValidationError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise HookValidationError(f"{field} must be an ISO 8601 timestamp") from err
    if parsed.tzinfo is None:
        raise HookValidationError(f"{field} must include a timezone")
    return value


def _validate_number(value: Any, field: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise HookValidationError(f"{field} must be a number")
    if not math.isfinite(value):
        raise HookValidationError(f"{field} must be finite")
    return value


def validate_hook_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize a CodexBar v1 hook payload."""
    if not isinstance(payload, dict):
        raise HookValidationError("hook payload must be a JSON object")

    event_type = payload.get("event")
    if event_type not in HOOK_EVENT_TYPES:
        raise HookValidationError(f"unsupported hook event {event_type!r}")

    provider = payload.get("provider")
    if not isinstance(provider, str) or not provider:
        raise HookValidationError("provider must be a non-empty string")

    normalized: dict[str, Any] = {
        "event": event_type,
        "provider": provider,
        "timestamp": _validate_timestamp(payload.get("timestamp"), "timestamp"),
    }

    for field in _OPTIONAL_STRING_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise HookValidationError(f"{field} must be a string")
        normalized[field] = value

    for field in _OPTIONAL_NUMBER_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        normalized[field] = _validate_number(value, field)

    if "usagePercent" in normalized and not 0 <= normalized["usagePercent"] <= 1:
        raise HookValidationError("usagePercent must be between 0 and 1")

    reset_at = payload.get("resetAt")
    if reset_at is not None:
        normalized["resetAt"] = _validate_timestamp(reset_at, "resetAt")

    return normalized


def hook_signal(entry_id: str) -> str:
    """Return the dispatcher signal for one config entry."""
    return f"codexbar_{entry_id}_hook"
