#!/usr/bin/env python3
"""No-network privacy regression for redacted generated READY gate failures."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import maintain_text_ready_inventory as inventory  # noqa: E402
import ready_inventory_diagnostics as reporting  # noqa: E402


SLOT = {"slot_id": "slot_example", "business_date_jst": "2026-10-24",
        "post_type": "original_text"}
ACCOUNT = "beauty_account"
SECRET_TEXT = "NeverDisplayThisUnpublishedCustomerDraft"


def fake_ready(**override):
    row = {
        "queue_id": "private-queue-one",
        "account_id": ACCOUNT,
        "slot_id": SLOT["slot_id"],
        "business_date_jst": SLOT["business_date_jst"],
        "post_type": SLOT["post_type"],
        "status": "READY",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "public_post_text": SECRET_TEXT,
    }
    row.update(override)
    return row


def inspect(rows, ids=("private-queue-one",), runtime_status="DRY_RUN"):
    fake_module = SimpleNamespace(process_one=lambda *args, **kwargs: {
        "status": runtime_status
    })
    with patch.dict(sys.modules, {"process_threads_queue": fake_module}), \
         patch.object(inventory, "eligible_ready", return_value=True), \
         patch.object(inventory, "has_media", return_value=False), \
         patch.object(inventory, "final_public_post_validator",
                      return_value={"status": "PASS"}), \
         patch.object(inventory, "build_source_context", return_value={}), \
         patch.object(inventory, "hybrid_ai_gate_passed", return_value=(True, "PASS")):
        return inventory.generated_ready_rejection_counts(
            object(), rows, ACCOUNT, SLOT, list(ids)
        )


class GeneratedReadyRejectionDiagnostics(unittest.TestCase):
    def test_generated_queue_id_is_not_visible(self):
        result=inspect([])
        self.assertEqual(result, {"QUEUE_ID_NOT_UNIQUE_OR_NOT_VISIBLE": 1})

    def test_mismatched_exact_slot_is_not_a_publishable_ready(self):
        result=inspect([fake_ready(slot_id="different_slot")])
        self.assertEqual(result, {"EXACT_SLOT_OR_DATE_MISMATCH": 1})

    def test_different_account_is_blocked_without_crossing_accounts(self):
        result=inspect([fake_ready(account_id="night_scout")])
        self.assertEqual(result, {"ACCOUNT_ID_MISMATCH": 1})

    def test_created_waiting_review_does_not_bypass_status(self):
        result=inspect([fake_ready(status="WAITING_REVIEW")])
        self.assertEqual(result, {"STATUS_NOT_READY": 1})

    def test_ready_missing_validator_gate_never_passes(self):
        result=inspect([fake_ready(account_fit_status="FAILED")])
        self.assertEqual(result, {"READY_APPROVAL_FLAGS_INCOMPLETE": 1})

    def test_runtime_rejection_category_does_not_leak_original_status(self):
        result=inspect([fake_ready()],runtime_status="SECRET_PRIVATE_BLOCK_MESSAGE")
        self.assertEqual(result, {"RUNTIME_DRY_RUN_GATE": 1})
        self.assertNotIn("SECRET_", str(result))

    def test_valid_runtime_is_not_falsely_rejected(self):
        result=inspect([fake_ready()])
        self.assertEqual(result, {"PUBLISHABILITY_AUDIT_INCONSISTENT": 1})

    def test_duplicate_queue_id_is_not_counted_as_valid(self):
        result=inspect([fake_ready(),fake_ready()])
        self.assertEqual(result, {"QUEUE_ID_NOT_UNIQUE_OR_NOT_VISIBLE": 1})

    def test_missing_ids_and_invalid_ids_are_bounded(self):
        self.assertEqual(inspect([fake_ready()],ids=()),
                         {"GENERATION_REPORTED_NO_IDS": 1})
        self.assertEqual(inspect([fake_ready()],ids=(123,)),
                         {"GENERATED_ID_LIST_UNVERIFIABLE": 1})

    def test_report_sanitizes_private_text_and_identifiers(self):
        counts=inspect([fake_ready()],runtime_status="VERY_SECRET_RUNTIME_ERROR")
        data={"status":"FAILED","results":[{
            "account_id":ACCOUNT,"delivery_slo":"FAIL",
            "delivery_generation_failure_category":"READY_CREATED_NOT_PUBLISHABLE",
            "generated_ready_rejection_counts":counts,
        }]}
        report=reporting.render_report(data,ACCOUNT)
        self.assertIn("READY_CREATED_NOT_PUBLISHABLE",report)
        self.assertNotIn(SECRET_TEXT,report)
        self.assertNotIn("private-queue",report)
        self.assertNotIn("VERY_SECRET_RUNTIME_ERROR",report)

    def test_readiness_report_rejection_reasons_are_whitelisted_and_bounded(self):
        data = {"status": "FAILED", "results": [{
            "account_id": ACCOUNT, "delivery_slo": "FAIL",
            "delivery_generation_failure_category": "READY_CREATED_NOT_PUBLISHABLE",
            "generated_ready_rejection_counts": {
                "EXACT_SLOT_OR_DATE_MISMATCH": 2,
                "PRIVATE_LEAK_" + SECRET_TEXT: 10000000,
                "RUNTIME_DRY_RUN_GATE": 1,
            },
        }]}
        report = reporting.render_report(data, ACCOUNT)
        self.assertIn("Generated READY rejection EXACT_SLOT_OR_DATE_MISMATCH: 2", report)
        self.assertIn("Generated READY rejection RUNTIME_DRY_RUN_GATE: 1", report)
        self.assertIn("Generated READY rejection UNCLASSIFIED_REJECTION: 1", report)
        self.assertNotIn(SECRET_TEXT, report)
        self.assertNotIn("10000000", report)

    def test_generated_diagnostics_never_posts_or_updates(self):
        source=(Path(__file__).resolve().parent/"maintain_text_ready_inventory.py").read_text()
        start = source.index("def generated_ready_rejection_counts(")
        end = source.index("\ndef _reserve_status(", start)
        section = source[start:end]
        for forbidden in ("apply=True","confirm_real_post=True",
                          "client.update","update_row(","print(row",
                          "str(queue_id)", "SECRET"):
            self.assertNotIn(forbidden,section)
        self.assertIn("dry_run=True, confirm_real_post=False",section)


if __name__ == "__main__":
    unittest.main()
