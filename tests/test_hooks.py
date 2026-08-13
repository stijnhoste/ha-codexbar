"""Tests for the CodexBar hook event contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

HOOKS_MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "codexbar" / "hooks.py"
)
SPEC = importlib.util.spec_from_file_location("codexbar_hooks", HOOKS_MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
HOOKS_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOKS_MODULE
SPEC.loader.exec_module(HOOKS_MODULE)

HookValidationError = HOOKS_MODULE.HookValidationError
HOOK_EVENT_TYPES = HOOKS_MODULE.HOOK_EVENT_TYPES
validate_hook_payload = HOOKS_MODULE.validate_hook_payload


def hook(**overrides):
    """Return a minimal valid CodexBar hook payload."""
    payload = {
        "event": "quota_reset",
        "provider": "codex",
        "timestamp": "2026-08-13T05:00:00Z",
    }
    payload.update(overrides)
    return payload


class HookValidationTests(unittest.TestCase):
    """Verify strict handling of CodexBar hook input."""

    def test_accepts_quota_reset(self):
        payload = hook(window="weekly", usagePercent=0)
        self.assertEqual(validate_hook_payload(payload), payload)

    def test_all_events(self):
        for event_type in HOOK_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertEqual(
                    validate_hook_payload(hook(event=event_type))["event"],
                    event_type,
                )

    def test_accepts_all_documented_optional_fields(self):
        payload = hook(
            event="quota_low",
            account="redacted",
            window="session",
            usagePercent=0.9,
            used=90,
            limit=100,
            resetAt="2026-08-13T06:00:00+00:00",
            status="warning",
        )
        self.assertEqual(validate_hook_payload(payload), payload)

    def test_ignores_unknown_optional_fields(self):
        validated = validate_hook_payload(hook(futureField="future-value"))
        self.assertNotIn("futureField", validated)

    def test_rejects_unknown_event(self):
        with self.assertRaisesRegex(HookValidationError, "unsupported hook event"):
            validate_hook_payload(hook(event="cost_threshold_reached"))

    def test_rejects_invalid_usage_fraction(self):
        with self.assertRaisesRegex(HookValidationError, "between 0 and 1"):
            validate_hook_payload(hook(usagePercent=90))

    def test_rejects_missing_timestamp(self):
        payload = hook()
        payload.pop("timestamp")
        with self.assertRaisesRegex(HookValidationError, "timestamp"):
            validate_hook_payload(payload)

    def test_rejects_timestamp_without_timezone(self):
        with self.assertRaisesRegex(HookValidationError, "timezone"):
            validate_hook_payload(hook(timestamp="2026-08-13T05:00:00"))


if __name__ == "__main__":
    unittest.main()
