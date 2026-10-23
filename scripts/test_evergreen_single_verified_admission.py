#!/usr/bin/env python3
"""SNS-only synthetic verification: one bank admission, one durable readback."""
from __future__ import annotations

from collections import Counter
import unittest
from unittest.mock import Mock, patch

import evergreen_inventory
import maintain_text_ready_inventory as maintenance
import process_threads_queue


class VerifiedBankAdmissionTests(unittest.TestCase):
    def test_canonical_batch_receipt_allows_single_verified_admission(self):
        candidate = {"queue_id": "q_synthetic"}
        expected = {"status": "SAVED", "count": 1, "created": 1,
                    "read_after_write": "PASS", "would_post": False}
        with patch.object(evergreen_inventory, "admit_bank_batch",
                          return_value=expected) as batch:
            receipt = maintenance.verified_bank_admission(
                object(), [candidate], now=maintenance.datetime.now(maintenance.JST),
                runtime_check=lambda _row: True,
            )
        self.assertEqual(receipt, expected)
        batch.assert_called_once()
        self.assertTrue(batch.call_args.kwargs["apply"])

    def test_invalid_receipt_fails_closed_before_success_is_reported(self):
        candidate = {"queue_id": "q_synthetic"}
        receipts = (
            None,
            {},
            {"status": "SAVED", "read_after_write": "PASS",
             "count": 1, "would_post": True},
            {"status": "SAVED", "read_after_write": "FAILED",
             "count": 1, "would_post": False},
            {"status": "SAVED", "read_after_write": "PASS",
             "count": True, "would_post": False},
            {"status": "SAVED", "read_after_write": "PASS",
             "count": 0, "would_post": False},
            {"status": "EXISTS", "read_after_write": "PASS",
             "count": 1, "would_post": False},
        )
        for receipt in receipts:
            with self.subTest(receipt=receipt):
                with patch.object(evergreen_inventory, "admit_bank_batch",
                                  return_value=receipt) as batch:
                    with self.assertRaisesRegex(
                        RuntimeError, "EVERGREEN_ADMISSION_RECEIPT_UNVERIFIED"
                    ):
                        maintenance.verified_bank_admission(
                            object(), [candidate],
                            now=maintenance.datetime.now(maintenance.JST),
                            runtime_check=lambda _row: True,
                        )
                    batch.assert_called_once()

    def test_empty_or_oversized_batch_is_refused_before_any_writer(self):
        with patch.object(evergreen_inventory, "admit_bank_batch") as batch:
            for rows in ([], [{"queue_id": str(i)} for i in range(31)]):
                with self.assertRaisesRegex(
                    ValueError, "EVERGREEN_ADMISSION_BATCH_SCOPE_INVALID"
                ):
                    maintenance.verified_bank_admission(
                        object(), rows, now=maintenance.datetime.now(maintenance.JST),
                        runtime_check=lambda _row: True,
                    )
            batch.assert_not_called()

    def test_newly_generated_approved_reserve_does_not_clear_dates_twice(self):
        queue = {
            "queue_id": "q_synthetic",
            "account_id": "beauty_account",
            "slot_id": "beauty_1130",
            "business_date_jst": "2026-11-07",
            "schedule_date_jst": "2026-11-07",
            "status": "READY",
            "generation_mode": "beauty_new_text_generation",
            "public_post_text": "synthetic safe phrase",
        }
        bank = []
        calls = Counter()
        def records(_client, name):
            calls[name] += 1
            if name == "queue":
                return [dict(queue)]
            if name == "evergreen_bank":
                return [dict(item) for item in bank]
            return []

        def approved_entries(*_args, **_kwargs):
            if (bank and not queue["business_date_jst"]
                    and not queue["schedule_date_jst"]):
                return [{"canonical_queue": {"slot_id": "beauty_1130"}}]
            return []

        def canonical_admit(_client, rows, **_kwargs):
            self.assertEqual([r["queue_id"] for r in rows], ["q_synthetic"])
            self.assertEqual(queue["business_date_jst"], "2026-11-07")
            queue["business_date_jst"] = ""
            queue["schedule_date_jst"] = ""
            bank.append({"queue_id": "q_synthetic", "account_id": "beauty_account"})
            return {"status": "SAVED", "read_after_write": "PASS",
                    "count": 1, "created": 1, "would_post": False}

        client = Mock()
        with (
            patch.object(maintenance, "policy",
                         return_value={"minimum_evergreen_per_account": 1}),
            patch.object(maintenance, "evergreen_active_text_slots",
                         return_value=[{"slot_id": "beauty_1130",
                                        "post_type": "original_text"}]),
            patch.object(maintenance, "usable_evergreen_entries",
                         side_effect=approved_entries),
            patch.object(maintenance, "eligible_ready", return_value=True),
            patch.object(maintenance, "has_media", return_value=False),
            patch.object(maintenance, "final_public_post_validator",
                         return_value={"status": "PASS"}),
            patch.object(maintenance, "hybrid_ai_gate_passed",
                         return_value=(True, {})),
            patch.object(maintenance, "build_source_context", return_value={}),
            patch.object(maintenance, "evergreen_theme_variants", return_value=[]),
            patch.object(maintenance, "replenish", return_value={
                "status": "READY_REPLENISHED", "queue_ids": ["q_synthetic"],
                "attempts": [], "failure_category": "",
            }) as generation,
            patch.object(process_threads_queue, "records", side_effect=records),
            patch.object(process_threads_queue, "process_one",
                         return_value={"status": "DRY_RUN"}),
            patch.object(evergreen_inventory, "expired_unpublished_bank_allocations",
                         return_value=[]),
            patch.object(evergreen_inventory,
                         "release_expired_unpublished_bank_allocations",
                         return_value={"status": "SKIPPED"}),
            patch.object(evergreen_inventory, "admit_bank_batch",
                         side_effect=canonical_admit) as admission,
            patch.object(maintenance, "release_temporary_bank_allocations",
                         side_effect=AssertionError("Second queue mutation denied")) as duplicate,
            patch.object(maintenance, "prime_readonly_record_cache"),
        ):
            report = maintenance.replenish_bank(client, "beauty_account", apply=True)
        self.assertEqual(report["status"], "READY_INVENTORY_OK")
        self.assertEqual(report["usable_evergreen"], 1)
        self.assertFalse(report["would_post"])
        self.assertEqual(queue["business_date_jst"], "")
        self.assertEqual(queue["schedule_date_jst"], "")
        self.assertEqual(generation.call_count, 1)
        admission.assert_called_once()
        duplicate.assert_not_called()
        self.assertGreater(calls["queue"], 0)
        self.assertGreater(calls["evergreen_bank"], 0)


if __name__ == "__main__":
    unittest.main()
