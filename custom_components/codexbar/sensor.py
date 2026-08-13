"""Sensor platform for CodexBar.

Generic: it consumes the normalized `/dashboard/v1/snapshot` payload and
creates, for every enabled provider, one set of sensors per rate-limit window
(used / remaining / reset-at / reset-at-date) plus plan, credits, cost, and
status where the provider exposes them.

Entities are reconciled on every coordinator update, so providers and windows
that appear or disappear in CodexBar are reflected automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import COST_ROUND, CREDITS_ROUND, DOMAIN, PERCENT_ROUND
from .coordinator import CodexBarCoordinator

_LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------- helpers


def _round(value: Any, ndigits: int):
    if value is None:
        return None
    try:
        result = round(float(value), ndigits)
    except (TypeError, ValueError):
        return None
    if result == int(result):
        return int(result)
    return result


def _parse_ts(value: Any):
    if not value:
        return None
    return dt_util.parse_datetime(value)


def _absolute(value: Any) -> str | None:
    dt = _parse_ts(value)
    if dt is None:
        return None
    dt = dt_util.as_local(dt)
    ampm = "AM" if dt.hour < 12 else "PM"
    hour12 = dt.hour % 12 or 12
    return f"{dt.strftime('%b')} {dt.day}, {dt.year} {hour12}:{dt.minute:02d} {ampm}"


def _window_getter(kind: str, label: str, field: str) -> Callable[[dict], Any]:
    def getter(provider: dict) -> Any:
        for window in provider.get("windows") or []:
            if window.get("kind") == kind and window.get("label") == label:
                return window.get(field)
        return None

    return getter


# --------------------------------------------------------------------------- spec


@dataclass
class Spec:
    """Describes one sensor to create for a provider."""

    provider_id: str
    key: str
    name: str
    value_fn: Callable[[dict], Any]
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    native_unit: str | None = None
    icon: str | None = None

    @property
    def unique_id(self) -> str:
        return f"{self.provider_id}_{self.key}"


def _provider_specs(provider: dict) -> list[Spec]:
    """Build the sensor specs for a single provider row."""
    pid = provider.get("id") or slugify(provider.get("name") or "provider")
    name = provider.get("name") or pid
    specs: list[Spec] = []

    identity = provider.get("identity") or {}
    if identity.get("plan"):
        specs.append(
            Spec(
                pid,
                "plan",
                f"{name} Plan",
                lambda p: (p.get("identity") or {}).get("plan"),
            )
        )

    for window in provider.get("windows") or []:
        kind = window.get("kind") or window.get("label") or "window"
        label = window.get("label") or window.get("kind") or "Window"
        key = slugify(kind)
        base = f"{name} {label}"

        specs.append(
            Spec(
                pid,
                f"{key}_used",
                f"{base} Used",
                lambda p, k=kind, l=label: _round(_window_getter(k, l, "usedPercent")(p), PERCENT_ROUND),
                state_class=SensorStateClass.MEASUREMENT,
                native_unit=PERCENTAGE,
            )
        )
        specs.append(
            Spec(
                pid,
                f"{key}_remaining",
                f"{base} Remaining",
                lambda p, k=kind, l=label: _round(_window_getter(k, l, "remainingPercent")(p), PERCENT_ROUND),
                state_class=SensorStateClass.MEASUREMENT,
                native_unit=PERCENTAGE,
            )
        )
        specs.append(
            Spec(
                pid,
                f"{key}_resets_at",
                f"{base} Resets At",
                lambda p, k=kind, l=label: _parse_ts(_window_getter(k, l, "resetAt")(p)),
                device_class=SensorDeviceClass.TIMESTAMP,
            )
        )
        specs.append(
            Spec(
                pid,
                f"{key}_resets_at_date",
                f"{base} Resets At (date)",
                lambda p, k=kind, l=label: _absolute(_window_getter(k, l, "resetAt")(p)),
            )
        )

    credits = provider.get("credits") or {}
    if credits.get("remaining") is not None:
        specs.append(
            Spec(
                pid,
                "credits",
                f"{name} Credits",
                lambda p: _round((p.get("credits") or {}).get("remaining"), CREDITS_ROUND),
                state_class=SensorStateClass.MEASUREMENT,
                native_unit=credits.get("unit"),
                icon="mdi:ticket-percent",
            )
        )

    cost = provider.get("cost") or {}
    if cost.get("todayUSD") is not None:
        specs.append(
            Spec(
                pid,
                "cost_today",
                f"{name} Cost Today",
                lambda p: _round((p.get("cost") or {}).get("todayUSD"), COST_ROUND),
                state_class=SensorStateClass.MEASUREMENT,
                native_unit="USD",
                icon="mdi:cash",
            )
        )
    if cost.get("last30DaysUSD") is not None:
        specs.append(
            Spec(
                pid,
                "cost_30d",
                f"{name} Cost 30d",
                lambda p: _round((p.get("cost") or {}).get("last30DaysUSD"), COST_ROUND),
                state_class=SensorStateClass.MEASUREMENT,
                native_unit="USD",
                icon="mdi:cash",
            )
        )

    status = provider.get("status") or {}
    if status.get("label"):
        specs.append(
            Spec(
                pid,
                "status",
                f"{name} Status",
                lambda p: (p.get("status") or {}).get("label"),
            )
        )

    return specs


# --------------------------------------------------------------------------- entity


class CodexBarSensor(CoordinatorEntity, SensorEntity):
    """A single CodexBar sensor entity."""

    def __init__(self, coordinator: CodexBarCoordinator, spec: Spec) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._provider_id = spec.provider_id
        self._attr_name = spec.name
        self._attr_unique_id = spec.unique_id
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_native_unit_of_measurement = spec.native_unit
        if spec.icon:
            self._attr_icon = spec.icon

    def _provider(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        for provider in data.get("providers", []):
            if provider.get("id") == self._provider_id:
                return provider
        return None

    @property
    def native_value(self):
        provider = self._provider()
        if provider is None:
            return None
        return self._spec.value_fn(provider)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        provider = self._provider()
        if provider is None:
            return {}
        identity = provider.get("identity") or {}
        attrs: dict[str, Any] = {"provider": self._provider_id}
        if identity.get("accountEmail"):
            attrs["account"] = identity["accountEmail"]
        if provider.get("source"):
            attrs["source"] = provider["source"]
        return attrs


# --------------------------------------------------------------------------- platform


class CodexBarSensorManager:
    """Creates and removes sensors as the snapshot changes."""

    def __init__(
        self,
        coordinator: CodexBarCoordinator,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self._entities: dict[str, CodexBarSensor] = {}

    def _desired(self) -> dict[str, Spec]:
        desired: dict[str, Spec] = {}
        data = self.coordinator.data or {}
        for provider in data.get("providers", []):
            if provider.get("enabled") is False:
                continue
            for spec in _provider_specs(provider):
                desired[spec.unique_id] = spec
        return desired

    def reconcile(self, *_args) -> None:
        desired = self._desired()

        new_entities: list[CodexBarSensor] = []
        for unique_id, spec in desired.items():
            if unique_id not in self._entities:
                entity = CodexBarSensor(self.coordinator, spec)
                self._entities[unique_id] = entity
                new_entities.append(entity)
        if new_entities:
            self.async_add_entities(new_entities)

        for unique_id in list(self._entities):
            if unique_id not in desired:
                self._entities.pop(unique_id).async_remove()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CodexBar sensors from a config entry."""
    coordinator: CodexBarCoordinator = hass.data[DOMAIN][entry.entry_id]

    manager = CodexBarSensorManager(coordinator, async_add_entities)
    manager.reconcile()
    entry.async_on_unload(coordinator.async_add_listener(manager.reconcile))
