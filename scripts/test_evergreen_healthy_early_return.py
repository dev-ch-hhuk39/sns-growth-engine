#!/usr/bin/env python3
"""The scheduled SNS evergreen bank must not churn healthy inventory.

Synthetic tests only: no Sheets network, paid provider, or real SNS post.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import evergreen_inventory
import maintain_text_ready_inventory as module
import process_threads_queue


class HealthyBankEarlyReturnTests(unittest.TestCase):
    @staticmethod
    def owner():
        c = Mock()
        c._ensure_tab = Mock()
        return c

    def test_existing_sufficient_approved_bank_skips_all_mutations_and_paid_ai(self):
        client = self.owner()
        reserve = [{"canonical_queue": {"slot_id": slot["slot_id"]}, "normalized_hash": "safe-" + str(i)} for slot in module.text_slots("night_scout") for i in range(11)]
        with (
            patch.object(process_threads_queue, "records", return_value=[]),
            patch.object(module, "usable_evergreen_entries", return_value=reserve),
            patch.object(module, "replenish") as generation,
            patch.object(evergreen_inventory, "release_expired_unpublished_bank_allocations") as release,
            patch.object(evergreen_inventory, "admit_bank_batch") as admission,
            patch.object(module, "prime_readonly_record_cache"),
        ):
            result = module.replenish_bank(client, "night_scout", apply=True)
        self.assertEqual(result["status"], "READY_INVENTORY_OK")
        self.assertEqual(result["usable_evergreen"], 30)
        self.assertEqual(result["attempts"], [])
        self.assertEqual(result["expired_allocation_release"]["status"], "SKIPPED_HEALTHY_BANK")
        self.assertFalse(result["would_post"])
        release.assert_not_called()
        admission.assert_not_called()
        generation.assert_not_called()

    def test_released_unpublished_bank_reaches_minimum_without_paid_ai(self):
        client = self.owner()
        call_count = 0

        def returns_bank(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return ([] if call_count == 1 else
                    [{"canonical_queue": {"slot_id": slot["slot_id"]}, "normalized_hash": "safe-" + str(i)} for slot in module.text_slots("night_scout") for i in range(10)])

        with (
            patch.object(process_threads_queue, "records", return_value=[]),
            patch.object(module, "usable_evergreen_entries", side_effect=returns_bank),
            patch.object(evergreen_inventory, "expired_unpublished_bank_allocations", return_value=[{"account_id": "night_scout"}]),
            patch.object(evergreen_inventory, "release_expired_unpublished_bank_allocations", return_value={"status": "PASS"}) as release,
            patch.object(evergreen_inventory, "admit_bank_batch") as admission,
            patch.object(module, "prime_readonly_record_cache"),
            patch.object(module, "replenish") as generation,
        ):
            result = module.replenish_bank(client, "night_scout", apply=True)
        self.assertEqual(result["status"], "READY_INVENTORY_OK")
        self.assertEqual(result["expired_allocation_release"]["status"], "PASS")
        self.assertEqual(result["usable_evergreen"], 30)
        self.assertEqual(call_count, 2)
        release.assert_called_once()
        admission.assert_not_called()
        generation.assert_not_called()

    def test_legacy_bank_surplus_does_not_hide_empty_current_slots(self):
        slots = module.text_slots("night_scout")
        data = [
            {"canonical_queue": {"slot_id": "retired_legacy_slot"}}
            for _ in range(200)
        ] + [
            {"canonical_queue": {"slot_id": slots[0]["slot_id"]}}
            for _ in range(80)
        ]
        usable, deficits, per_slot = module.evergreen_canonical_slot_health(
            data, "night_scout", 30)
        self.assertEqual(usable, 10)
        self.assertEqual(sum(deficits.values()), 20)
        self.assertEqual(per_slot[slots[0]["slot_id"]], 80)
        self.assertEqual(per_slot[slots[1]["slot_id"]], 0)
        self.assertEqual(per_slot[slots[2]["slot_id"]], 0)

    def test_bank_attempt_targets_missing_canonical_slot(self):
        client = self.owner()
        with (
            patch.object(process_threads_queue, "records", return_value=[]),
            patch.object(module, "usable_evergreen_entries", return_value=[]),
            patch.object(evergreen_inventory, "expired_unpublished_bank_allocations", return_value=[]),
            patch.object(evergreen_inventory, "release_expired_unpublished_bank_allocations",
                         return_value={"status": "SKIPPED"}),
            patch.object(module, "evergreen_theme_variants", return_value=[]),
            patch.object(module, "replenish", return_value={
                "status": "QUALITY_EXHAUSTED", "queue_ids": [],
                "failure_category": "QUALITY_EXHAUSTED", "attempts": [],
            }) as generation,
            patch.object(module, "hard_replenishment_blocker", return_value=True),
        ):
            result = module.replenish_bank(client, "night_scout", apply=True)
        self.assertEqual(result["status"], "QUALITY_EXHAUSTED")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["usable_evergreen"], 0)
        self.assertEqual(generation.call_count, 1)
        submitted = generation.call_args.args[1]
        self.assertEqual(submitted["slot_id"], module.text_slots("night_scout")[0]["slot_id"])
        self.assertEqual(submitted["post_type"], "original_text")
        self.assertFalse(result["would_post"])

    def test_beauty_media_only_cycle_not_counted_as_text_bank(self):
        active = module.evergreen_active_text_slots("beauty_account")
        self.assertEqual([slot["slot_id"] for slot in active], ["beauty_1130"])
        entries = [
            {"canonical_queue": {"slot_id": "beauty_2030"}}
            for _ in range(90)
        ] + [
            {"canonical_queue": {"slot_id": "beauty_1130"}}
            for _ in range(9)
        ]
        usable, deficits, by_slot = module.evergreen_canonical_slot_health(
            entries, "beauty_account", 30)
        self.assertEqual(usable, 9)
        self.assertEqual(deficits, {"beauty_1130": 21})
        self.assertEqual(by_slot, {"beauty_1130": 9})

    def test_bank_plan_never_creates_runtime_client(self):
        owner = self.owner()
        result = module.replenish_bank(owner, "beauty_account", apply=False)
        self.assertEqual(result["status"], "PLAN_ONLY")
        owner._ensure_tab.assert_not_called()


if __name__ == "__main__":
    unittest.main()
