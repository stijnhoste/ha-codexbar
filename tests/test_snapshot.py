"""Tests for the CodexBar dashboard snapshot contract."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

SNAPSHOT_MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "codexbar" / "snapshot.py"
)
SPEC = importlib.util.spec_from_file_location("codexbar_snapshot", SNAPSHOT_MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
SNAPSHOT_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SNAPSHOT_MODULE
SPEC.loader.exec_module(SNAPSHOT_MODULE)

SnapshotValidationError = SNAPSHOT_MODULE.SnapshotValidationError
provider_error_attributes = SNAPSHOT_MODULE.provider_error_attributes
provider_status_value = SNAPSHOT_MODULE.provider_status_value
snapshot_is_stale = SNAPSHOT_MODULE.snapshot_is_stale
validate_snapshot = SNAPSHOT_MODULE.validate_snapshot


def snapshot(**overrides):
    """Return a minimal valid dashboard-v1 snapshot."""
    payload = {
        "schemaVersion": 1,
        "generatedAt": "2026-08-13T05:00:00Z",
        "staleAfterSeconds": 180,
        "providers": [
            {
                "id": "codex",
                "name": "Codex",
                "enabled": True,
                "error": None,
            }
        ],
    }
    payload.update(overrides)
    return payload


class SnapshotValidationTests(unittest.TestCase):
    """Verify strict handling of the versioned dashboard contract."""

    def test_accepts_schema_v1(self):
        payload = snapshot()
        self.assertIs(validate_snapshot(payload), payload)

    def test_rejects_unknown_schema_version(self):
        with self.assertRaisesRegex(SnapshotValidationError, "schemaVersion"):
            validate_snapshot(snapshot(schemaVersion=2))

    def test_rejects_invalid_freshness_metadata(self):
        with self.assertRaisesRegex(SnapshotValidationError, "generatedAt"):
            validate_snapshot(snapshot(generatedAt="not-a-timestamp"))
        with self.assertRaisesRegex(SnapshotValidationError, "staleAfterSeconds"):
            validate_snapshot(snapshot(staleAfterSeconds=-1))

    def test_rejects_invalid_provider_error_shape(self):
        payload = snapshot()
        payload["providers"][0]["error"] = "temporary failure"
        with self.assertRaisesRegex(SnapshotValidationError, "error"):
            validate_snapshot(payload)

    def test_reports_snapshot_freshness(self):
        payload = snapshot()
        self.assertFalse(
            snapshot_is_stale(
                payload,
                now=datetime(2026, 8, 13, 5, 2, 59, tzinfo=timezone.utc),
            )
        )
        self.assertTrue(
            snapshot_is_stale(
                payload,
                now=datetime(2026, 8, 13, 5, 3, tzinfo=timezone.utc),
            )
        )

    def test_exposes_provider_error_details(self):
        provider = {
            "error": {
                "code": 1,
                "kind": "provider",
                "message": "temporary failure",
            }
        }
        self.assertEqual(
            provider_error_attributes(provider),
            {
                "provider_error": "temporary failure",
                "provider_error_kind": "provider",
                "provider_error_code": 1,
            },
        )
        self.assertEqual(provider_status_value(provider), "Error")

    def test_accounts_error_is_degraded(self):
        provider = {"accountsError": "account source unavailable"}
        self.assertEqual(provider_status_value(provider), "Degraded")

    def test_uses_codexbar_status_when_no_error_exists(self):
        provider = {"status": {"level": "ok", "label": "Operational"}}
        self.assertEqual(provider_status_value(provider), "Operational")


if __name__ == "__main__":
    unittest.main()
