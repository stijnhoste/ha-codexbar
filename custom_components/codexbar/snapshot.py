"""Validation and presentation helpers for the CodexBar dashboard contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1


class SnapshotValidationError(ValueError):
    """Raised when a dashboard snapshot does not match the supported contract."""


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotValidationError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise SnapshotValidationError(f"{field} must be an ISO 8601 timestamp") from err
    if parsed.tzinfo is None:
        raise SnapshotValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_snapshot(payload: Any) -> dict[str, Any]:
    """Validate the stable fields this integration consumes from schema v1."""
    if not isinstance(payload, dict):
        raise SnapshotValidationError("snapshot must be a JSON object")

    schema_version = payload.get("schemaVersion")
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise SnapshotValidationError(
            f"unsupported schemaVersion {schema_version!r}; expected {SCHEMA_VERSION}"
        )

    _parse_timestamp(payload.get("generatedAt"), "generatedAt")

    stale_after = payload.get("staleAfterSeconds")
    if type(stale_after) is not int or stale_after < 0:
        raise SnapshotValidationError(
            "staleAfterSeconds must be a non-negative integer"
        )

    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise SnapshotValidationError("providers must be an array")

    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            raise SnapshotValidationError(f"providers[{index}] must be an object")
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise SnapshotValidationError(
                f"providers[{index}].id must be a non-empty string"
            )
        if type(provider.get("enabled")) is not bool:
            raise SnapshotValidationError(
                f"providers[{index}].enabled must be a boolean"
            )
        error = provider.get("error")
        if error is not None and not isinstance(error, dict):
            raise SnapshotValidationError(
                f"providers[{index}].error must be an object or null"
            )
        if isinstance(error, dict) and (
            not isinstance(error.get("message"), str) or not error["message"]
        ):
            raise SnapshotValidationError(
                f"providers[{index}].error.message must be a non-empty string"
            )
        accounts_error = provider.get("accountsError")
        if accounts_error is not None and not isinstance(accounts_error, str):
            raise SnapshotValidationError(
                f"providers[{index}].accountsError must be a string or null"
            )

    return payload


def snapshot_is_stale(payload: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Return whether a validated snapshot is older than its freshness window."""
    generated_at = _parse_timestamp(payload.get("generatedAt"), "generatedAt")
    stale_after = payload["staleAfterSeconds"]
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include a timezone")
    return current_time.astimezone(timezone.utc) >= generated_at + timedelta(
        seconds=stale_after
    )


def provider_error_attributes(provider: dict[str, Any]) -> dict[str, Any]:
    """Return Home Assistant-safe attributes for provider-local failures."""
    attributes: dict[str, Any] = {}
    error = provider.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            attributes["provider_error"] = message
        kind = error.get("kind")
        if isinstance(kind, str) and kind:
            attributes["provider_error_kind"] = kind
        code = error.get("code")
        if isinstance(code, (int, str)) and not isinstance(code, bool):
            attributes["provider_error_code"] = code

    accounts_error = provider.get("accountsError")
    if isinstance(accounts_error, str) and accounts_error:
        attributes["accounts_error"] = accounts_error
    return attributes


def provider_status_value(provider: dict[str, Any]) -> str:
    """Return one stable summary state for a provider row."""
    error_attributes = provider_error_attributes(provider)
    if "provider_error" in error_attributes:
        return "Error"
    if "accounts_error" in error_attributes:
        return "Degraded"
    status = provider.get("status")
    if isinstance(status, dict):
        label = status.get("label")
        if isinstance(label, str) and label:
            return label
    return "Available"
