#!/usr/bin/env python3
"""No-post synthetic checks for generated evergreen queue readback failures."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

import evergreen_inventory
import maintain_text_ready_inventory as maintenance
import process_threads_queue
import evergreen_inventory
import process_threads_queue


ACCOUNT = "beauty_account"
SLOT = "beauty_1130"


def ready(queue_id="q_synthetic", status="READY", account=ACCOUNT, slot=SLOT):
    return {
        "queue_id": queue_id, "status": status, "account_id": account,
        "slot_id": slot, "public_post_text": "PRIVATE_SYNTHETIC_TEXT",
        "platform": "threads", "generation_mode": "beauty_new_text_generation",
        "business_date_jst": "2026-11-07",
    }


class GeneratedAdmissionClassifierTests(unittest.TestCase):
    def classify(self, rows, ids, check=lambda _row: True):
        return maintenance.classified_generated_bank_admissions(
            rows, ids, ACCOUNT, SLOT, check,
        )

    def test_exact_approved_same_slot_row_only(self):
        row = ready()
        with patch.object(maintenance, "eligible_ready", return_value=True), patch.object(
            maintenance, "has_media", return_value=False
        ):
            approved, rejected = self.classify([row], ["q_synthetic"])
        self.assertEqual(approved, [row])
        self.assertEqual(rejected, {})

    def test_unverified_and_duplicate_generated_ids_never_admit(self):
        for ids in (None, "q_synthetic", {"queue_id": "q_synthetic"},
                    ["q_synthetic", "q_synthetic"], ["bad\nvalue"],
                    list(map(str, range(4))), [True], ["x" * 257]):
            with self.subTest(ids=str(ids)[:25]):
                approved, rejected = self.classify([ready()], ids)
                self.assertEqual(approved, [])
                self.assertEqual(rejected, {"GENERATED_ID_LIST_UNVERIFIABLE": 1})
        for rows in ([], [ready(), ready()]):
            approved, rejected = self.classify(rows, ["q_synthetic"])
            self.assertEqual(approved, [])
            self.assertEqual(rejected, {"GENERATED_READBACK_UNVERIFIED": 1})

    def test_wrong_account_or_immutable_slot_is_rejected(self):
        for row in (ready(account="night_scout"), ready(slot="beauty_2030")):
            approved, rejected = self.classify([row], ["q_synthetic"])
            self.assertEqual(approved, [])
            self.assertEqual(rejected, {"GENERATED_IDENTITY_MISMATCH": 1})

    def test_nonready_or_incomplete_approval_blocks_without_runtime_check(self):
        runtime = Mock(side_effect=AssertionError("runtime must not run"))
        approved, reasons = self.classify([ready(status="WAITING_REVIEW")], ["q_synthetic"], runtime)
        self.assertEqual(approved, [])
        self.assertEqual(reasons, {"GENERATED_NOT_READY": 1})
        runtime.assert_not_called()
        with patch.object(maintenance, "eligible_ready", return_value=False):
            approved, reasons = self.classify([ready()], ["q_synthetic"], runtime)
        self.assertEqual(approved, [])
        self.assertEqual(reasons, {"GENERATED_APPROVAL_INCOMPLETE": 1})
        runtime.assert_not_called()

    def test_runtime_quality_rejection_and_mixed_batch_are_fail_closed(self):
        with patch.object(maintenance, "eligible_ready", return_value=True), patch.object(
            maintenance, "has_media", return_value=False
        ):
            approved, rejected = self.classify([ready()], ["q_synthetic"], lambda _row: False)
            self.assertEqual(approved, [])
            self.assertEqual(rejected, {"GENERATED_RUNTIME_GATE_REJECTED": 1})
            approved, rejected = self.classify([ready(), ready("q_other", status="WAITING_REVIEW")],
                                                ["q_synthetic", "q_other"])
            self.assertEqual(approved, [])
            self.assertEqual(rejected, {"GENERATED_NOT_READY": 1})
            self.assertNotIn("PRIVATE_SYNTHETIC_TEXT", json.dumps(rejected))


class ExplicitBeautyStagedReserveTests(unittest.TestCase):
    NOW = datetime(2026, 10, 23, 21, 0, tzinfo=timezone(timedelta(hours=9)))

    def candidate(self, *, reserve=True, date="2026-10-30"):
        number = "reserve_1_" if reserve else ""
        return {
            **ready(queue_id=f"q_beauty_{date.replace('-', '')}_1_chadult_v1_{number}deadbeef"),
            "generated_by": "prepare_beauty_review_candidates.py",
            "business_date_jst": date,
            "schedule_date_jst": "",
        }

    def test_only_explicit_reserve_identity_qualifies(self):
        staged = self.candidate()
        def check(row):
            return maintenance.is_explicit_staged_beauty_reserve(
                row, now=self.NOW, posted_ids=set(), bank_ids=set(), used_run_ids=set())
        self.assertTrue(check(staged))
        self.assertFalse(check(self.candidate(reserve=False)))
        for updates in (
            {"generated_by": "other_script.py"}, {"status": "WAITING_REVIEW"},
            {"account_id": "night_scout"}, {"slot_id": "beauty_2030"},
            {"business_date_jst": "2026-10-29"},
            {"schedule_date_jst": "2026-10-29"},
        ):
            with self.subTest(updates=updates):
                self.assertFalse(check({**staged, **updates}))
        self.assertFalse(check(self.candidate(date="2026-10-24")))
        self.assertFalse(check(self.candidate(date="2026-11-01")))
        self.assertTrue(check(self.candidate(date="2026-10-25")))

    def test_used_posted_banked_id_never_recovered(self):
        row = self.candidate()
        qid = row["queue_id"]
        for field in ("posted_ids", "bank_ids", "used_run_ids"):
            with self.subTest(field=field):
                args = {"posted_ids": set(), "bank_ids": set(), "used_run_ids": set()}
                args[field] = {qid}
                self.assertFalse(maintenance.is_explicit_staged_beauty_reserve(
                    row, now=self.NOW, **args))


class StagedRecoveryIntegrationTests(unittest.TestCase):
    def test_one_reserved_candidate_reused_without_touching_primary_or_ai(self):
        now = datetime.now(maintenance.JST)
        future = (now.date() + timedelta(days=7)).isoformat()
        code = future.replace("-", "")
        reserved = {
            **ready(f"q_beauty_{code}_1_chadult_v1_reserve_1_deadbeef"),
            "business_date_jst": future, "generated_by": "prepare_beauty_review_candidates.py",
            "generation_mode": "beauty_new_text_generation",
        }
        primary = {
            **ready(f"q_beauty_{code}_1_chadult_v1_deadbeef"),
            "business_date_jst": future, "generated_by": "prepare_beauty_review_candidates.py",
            "generation_mode": "beauty_new_text_generation",
        }
        queue = [dict(reserved), dict(primary)]
        bank = []
        client = Mock()
        def records(_client, tab):
            return {
                "queue": [dict(row) for row in queue],
                "evergreen_bank": [dict(row) for row in bank],
                "posted_results": [],
                "content_slot_runs": [],
            }[tab]
        def commit(_client, rows, **_kw):
            self.assertEqual([row["queue_id"] for row in rows], [reserved["queue_id"]])
            queue[0]["business_date_jst"] = ""
            queue[0]["schedule_date_jst"] = ""
            bank.append({"queue_id": reserved["queue_id"], "account_id": ACCOUNT})
            return {"status": "SAVED", "count": 1, "would_post": False,
                    "read_after_write": "PASS"}
        with (
            patch.object(maintenance, "policy", return_value={"minimum_evergreen_per_account": 1}),
            patch.object(maintenance, "evergreen_active_text_slots",
                         return_value=[{"slot_id": SLOT, "post_type": "original_text"}]),
            patch.object(maintenance, "eligible_ready", return_value=True),
            patch.object(maintenance, "has_media", return_value=False),
            patch.object(maintenance, "final_public_post_validator", return_value={"status": "PASS"}),
            patch.object(maintenance, "hybrid_ai_gate_passed", return_value=(True, "pass")),
            patch.object(maintenance, "build_source_context", return_value={}),
            patch.object(process_threads_queue, "process_one", return_value={"status": "DRY_RUN"}),
            patch.object(process_threads_queue, "records", side_effect=records),
            patch.object(maintenance, "usable_evergreen_entries",
                         side_effect=lambda *_a, **_kw: [
                             {"canonical_queue": {"slot_id": SLOT}} for _ in bank]),
            patch.object(maintenance, "evergreen_canonical_slot_health",
                         side_effect=lambda rows, _account, _minimum: (
                             len(rows), {SLOT: max(0, 1 - len(rows))}, {SLOT: len(rows)})),
            patch.object(evergreen_inventory, "expired_unpublished_bank_allocations",
                         return_value=[]),
            patch.object(evergreen_inventory, "release_expired_unpublished_bank_allocations",
                         return_value={"status": "SKIPPED"}),
            patch.object(maintenance, "prime_readonly_record_cache"),
            patch.object(maintenance, "verified_bank_admission", side_effect=commit) as admission,
            patch.object(maintenance, "replenish",
                         side_effect=AssertionError("No new paid provider request")) as generator,
        ):
            outcome = maintenance.replenish_bank(client, ACCOUNT, apply=True)
        self.assertEqual(outcome["status"], "READY_INVENTORY_OK")
        self.assertEqual(outcome["usable_evergreen"], 1)
        self.assertEqual(queue[0]["business_date_jst"], "")
        self.assertEqual(queue[1]["business_date_jst"], future)
        admission.assert_called_once()
        generator.assert_not_called()
        self.assertFalse(outcome["would_post"])


class GeneratedBankIntegrationTests(unittest.TestCase):
    def run_bank(self, *, status: str, runtime_gate=True):
        queue = ready(status=status)
        client = Mock()
        client._ensure_tab = Mock()

        def records(_client, tab):
            if tab == "queue":
                return [dict(queue)]
            if tab in ("evergreen_bank", "posted_results", "content_slot_runs"):
                return []
            raise AssertionError("Unexpected tab")

        def health(_rows, _account, _minimum):
            return (0, {SLOT: 1}, {SLOT: 0})

        with (
            patch.object(maintenance, "policy", return_value={"minimum_evergreen_per_account": 1}),
            patch.object(maintenance, "evergreen_active_text_slots",
                         return_value=[{"slot_id": SLOT, "post_type": "original_text"}]),
            patch.object(maintenance, "evergreen_canonical_slot_health", side_effect=health),
            patch.object(maintenance, "usable_evergreen_entries", return_value=[]),
            patch.object(maintenance, "evergreen_theme_variants", return_value=[]),
            patch.object(maintenance, "eligible_ready", return_value=status == "READY"),
            patch.object(maintenance, "has_media", return_value=False),
            patch.object(maintenance, "final_public_post_validator", return_value={"status": "PASS"}),
            patch.object(maintenance, "hybrid_ai_gate_passed", return_value=(True, "pass")),
            patch.object(maintenance, "build_source_context", return_value={}),
            patch.object(process_threads_queue, "records", side_effect=records),
            patch.object(process_threads_queue, "process_one",
                         return_value={"status": "DRY_RUN" if runtime_gate else "BLOCKED"}),
            patch.object(evergreen_inventory, "expired_unpublished_bank_allocations",
                         return_value=[]),
            patch.object(evergreen_inventory, "release_expired_unpublished_bank_allocations",
                         return_value={"status": "SKIPPED"}),
            patch.object(maintenance, "prime_readonly_record_cache"),
            patch.object(maintenance, "replenish", return_value={
                "status": "READY_REPLENISHED", "queue_ids": ["q_synthetic"],
                "attempts": [], "failure_category": "",
            }) as generation,
            patch.object(maintenance, "verified_bank_admission") as admission,
        ):
            result = maintenance.replenish_bank(client, ACCOUNT, apply=True)
            return result, generation.call_count, admission.call_count

    def test_waiting_review_has_one_attempt_no_false_success_or_write(self):
        report, runs, writes = self.run_bank(status="WAITING_REVIEW")
        self.assertEqual(report["status"], "QUALITY_EXHAUSTED")
        self.assertEqual(report["usable_evergreen"], 0)
        self.assertEqual(runs, 1)
        self.assertEqual(writes, 0)
        self.assertEqual(report["attempts"][0]["failure_category"],
                         "GENERATED_READBACK_UNVERIFIED")
        self.assertEqual(report["attempts"][0]["verification_rejection_counts"],
                         {"GENERATED_NOT_READY": 1})
        self.assertFalse(report["would_post"])

    def test_runtime_rejected_uses_only_existing_bounded_ten_theme_budget(self):
        report, runs, writes = self.run_bank(status="READY", runtime_gate=False)
        self.assertEqual(report["status"], "QUALITY_EXHAUSTED")
        self.assertEqual(report["usable_evergreen"], 0)
        self.assertEqual(runs, 10)
        self.assertEqual(writes, 0)
        self.assertEqual(len(report["attempts"]), 10)
        self.assertEqual(report["attempts"][0]["failure_category"],
                         "GENERATED_RUNTIME_GATE_REJECTED")
        self.assertFalse(report["would_post"])


if __name__ == "__main__":
    unittest.main()
