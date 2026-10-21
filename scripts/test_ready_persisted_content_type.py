#!/usr/bin/env python3
"""Persisted queue content_type / exact-slot READY regression (no network).

This validates the canonical Sheets queue schema and keeps all existing
publisher, validator, and safety gates in place. Synthetic rows only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import maintain_text_ready_inventory as inventory  # noqa: E402
from sheets_client import TAB_DEFINITIONS  # noqa: E402

ACCOUNT = "night_scout"
SLOT = {
    "slot_id": "ns_1400_reference",
    "business_date_jst": "2026-10-22",
    "post_type": "reference_text",
}


def persisted_ready(**changes):
    row = {
        "queue_id": "synthetic-queue-one",
        "account_id": ACCOUNT,
        "target_account_id": ACCOUNT,
        "platform": "threads",
        "slot_id": SLOT["slot_id"],
        "business_date_jst": SLOT["business_date_jst"],
        "content_type": "reference_text",
        "status": "READY",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "public_post_text": "公開投稿のテスト用短文。",
        "media_asset_id": "",
    }
    row.update(changes)
    return row


def checked(rows, *, runtime_status="DRY_RUN"):
    fake_publisher = SimpleNamespace(
        process_one=lambda *args, **kwargs: {"status": runtime_status}
    )
    with patch.dict(sys.modules, {"process_threads_queue": fake_publisher}), \
         patch.object(inventory, "final_public_post_validator",
                      return_value={"status": "PASS"}), \
         patch.object(inventory, "build_source_context", return_value={}), \
         patch.object(inventory, "hybrid_ai_gate_passed",
                      return_value=(True, "PASS")):
        return inventory._publishable_ready_rows(
            object(), rows, ACCOUNT, SLOT
        )


def rejection(row, *, runtime_status="DRY_RUN"):
    fake_publisher = SimpleNamespace(
        process_one=lambda *args, **kwargs: {"status": runtime_status}
    )
    with patch.dict(sys.modules, {"process_threads_queue": fake_publisher}), \
         patch.object(inventory, "final_public_post_validator",
                      return_value={"status": "PASS"}), \
         patch.object(inventory, "build_source_context", return_value={}), \
         patch.object(inventory, "hybrid_ai_gate_passed",
                      return_value=(True, "PASS")):
        return inventory.generated_ready_rejection_counts(
            object(), [row], ACCOUNT, SLOT, [row["queue_id"]]
        )


class PersistedQueueRouteRegression(unittest.TestCase):
    def test_real_queue_schema_persists_content_type_not_post_type(self):
        self.assertIn("content_type", TAB_DEFINITIONS["queue"])
        self.assertNotIn("post_type", TAB_DEFINITIONS["queue"])
        self.assertIn("post_type", TAB_DEFINITIONS["publication_review"])

    def test_valid_persisted_ready_row_is_not_lost_for_missing_post_type(self):
        row = persisted_ready()
        self.assertNotIn("post_type", row)
        self.assertEqual(checked([row]), [row])

    def test_legacy_in_memory_post_type_only_keeps_backward_compatibility(self):
        row = persisted_ready()
        del row["content_type"]
        row["post_type"] = "reference_text"
        self.assertEqual(checked([row]), [row])

    def test_conflicting_types_fail_closed(self):
        row = persisted_ready(post_type="direct_reference_media")
        self.assertEqual(checked([row]), [])
        self.assertEqual(rejection(row), {"NON_TEXT_POST_TYPE": 1})

    def test_missing_type_never_becomes_publishable(self):
        row = persisted_ready(content_type="")
        self.assertEqual(checked([row]), [])
        self.assertEqual(rejection(row), {"NON_TEXT_POST_TYPE": 1})

    def test_media_type_is_not_misclassified_as_text(self):
        row = persisted_ready(content_type="approved_source_clip")
        self.assertEqual(checked([row]), [])
        self.assertEqual(rejection(row), {"NON_TEXT_POST_TYPE": 1})

    def test_beauty_text_generation_alias_is_existing_allowed_text_route(self):
        row = persisted_ready(content_type="new_text_generation")
        self.assertEqual(checked([row]), [row])

    def test_exact_date_and_slot_cannot_be_bypassed(self):
        for changes in (
            {"slot_id": "other-slot"},
            {"business_date_jst": "2026-10-20"},
            {"account_id": "liver_manager"},
            {"status": "WAITING_REVIEW"},
            {"account_fit_status": "FAILED"},
        ):
            self.assertEqual(checked([persisted_ready(**changes)]), [])

    def test_hybrid_ai_gate_remains_mandatory(self):
        row = persisted_ready()
        with patch.object(inventory, "hybrid_ai_gate_passed",
                          return_value=(False, "BLOCKED")):
            self.assertEqual(checked([row]), [])

    def test_runtime_dry_run_gate_remains_mandatory(self):
        row = persisted_ready()
        self.assertEqual(checked([row], runtime_status="BLOCKED"), [])

    def test_diagnostics_follows_same_persisted_route(self):
        row = persisted_ready()
        self.assertEqual(
            rejection(row),
            {"PUBLISHABILITY_AUDIT_INCONSISTENT": 1},
        )

    def test_no_real_post_calls_in_gate(self):
        fake_publisher = SimpleNamespace(process_one=lambda *a, **kw: (
            self.assertTrue(kw.get("dry_run"))
            or self.assertFalse(kw.get("confirm_real_post"))
            or {"status": "DRY_RUN"}
        ))
        row = persisted_ready()
        with patch.dict(sys.modules, {"process_threads_queue": fake_publisher}), \
             patch.object(inventory, "final_public_post_validator",
                          return_value={"status": "PASS"}), \
             patch.object(inventory, "build_source_context", return_value={}), \
             patch.object(inventory, "hybrid_ai_gate_passed",
                          return_value=(True, "PASS")):
            self.assertEqual(
                inventory._publishable_ready_rows(object(), [row], ACCOUNT, SLOT),
                [row],
            )


if __name__ == "__main__":
    unittest.main()
