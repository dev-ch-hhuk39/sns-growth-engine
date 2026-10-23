#!/usr/bin/env python3
"""No-network malformed generation output / review receipt safety tests."""
from __future__ import annotations

import tempfile
from pathlib import Path as RealPath
import unittest
from unittest.mock import patch

import maintain_text_ready_inventory as module
import ready_evergreen_bank_summary as summary


SLOT = {"slot_id": "beauty_1130", "business_date_jst": "2026-11-07",
        "post_type": "original_text"}


class GeneratorEnvelopeSafety(unittest.TestCase):
    def test_null_nonlist_duplicate_and_untrusted_queue_ids_fail_closed(self):
        for value in (None, "synthetic", {"id": "q"}, [None], [33], ["q", "q"],
                      ["q\nnewline"], ["q" * 257], [True]):
            with self.subTest(value=value):
                self.assertEqual(
                    module._validated_generation_queue_ids(
                        {"effective_queue_ids": value}, "night_scout"),
                    ([], False),
                )

    def test_valid_string_ids_are_preserved_without_widening_scope(self):
        self.assertEqual(
            module._validated_generation_queue_ids(
                {"effective_queue_ids": ["q_one", "q-two"]}, "night_scout"),
            (["q_one", "q-two"], True),
        )

    def test_beauty_receipt_must_be_affirmative_and_bounded(self):
        for value in (None, 2, "PASS", {"queue_id": "q_a", "read_after_write": False},
                      {"queue_id": "q_a", "read_after_write": "FAILED"},
                      {"queue_id": None, "read_after_write": True},
                      {"queue_id": "q_a\nprivate", "read_after_write": True}):
            with self.subTest(value=value):
                result = {"queue_ids": ["q_other"], "apply_result": value}
                self.assertEqual(
                    module._validated_generation_queue_ids(result, "beauty_account"),
                    ([], False),
                )
        for affirmative in (True, "PASS"):
            result = {"queue_ids": ["q_unverified"],
                      "apply_result": {
                          "queue_id": "q_confirmed",
                          "read_after_write": affirmative,
                      }}
            self.assertEqual(
                module._validated_generation_queue_ids(result, "beauty_account"),
                (["q_confirmed"], True),
            )

    def test_malformed_nested_budget_envelope_never_crashes(self):
        for record in (
            {"stages": None},
            {"stages": "not_a_list", "runtime_errors": None},
            {"stages": [{"payload": None}], "runtime_errors": ["invalid"]},
            {"stages": [{"payload": {"runtime_errors": None}}]},
        ):
            with self.subTest(record=record):
                self.assertFalse(module.approval_budget_exhausted(record))
        evidence = {
            "stages": [
                {"payload": {"runtime_errors": [
                    {"reason": "HYBRID_AI_DAILY_LIMIT_EXCEEDED"}
                ]}}
            ]
        }
        self.assertTrue(module.approval_budget_exhausted(evidence))

    def test_invalid_generator_envelope_does_not_start_ready_approval(self):
        with (
            patch.object(module, "_generation_commands", return_value=[("primary", ["synthetic"])]),
            patch.object(module, "_run", return_value=(
                0, {"status": "GENERATED", "effective_queue_ids": None,
                    "apply_result": None}
            )) as child,
        ):
            report = module.replenish("beauty_account", SLOT, apply=True, required=1)
        child.assert_called_once()
        self.assertEqual(report["status"], "QUALITY_EXHAUSTED")
        self.assertEqual(report["queue_ids"], [])
        self.assertEqual(report["failure_category"], "GENERATION_OUTPUT_INVALID")
        self.assertEqual(report["attempts"][0]["reason"], "GENERATION_OUTPUT_INVALID")
        self.assertFalse(report["would_post"])

    def test_malformed_approval_file_cannot_approve_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = RealPath(tmp) / "review.json"
            def fake_run(command):
                if command == ["synthetic_generator"]:
                    return 0, {"status": "GENERATED", "effective_queue_ids": ["q_synth"]}
                output_path.write_text("{broken-json", encoding="utf-8")
                return 0, {"status": "READY"}
            with (
                patch.object(module, "_generation_commands",
                             return_value=[("primary", ["synthetic_generator"])]),
                patch.object(module, "Path", return_value=output_path),
                patch.object(module, "_run", side_effect=fake_run) as child,
            ):
                result = module.replenish(
                    "night_scout", {**SLOT, "slot_id": "ns_1600_original"},
                    apply=True, required=1)
            self.assertEqual(child.call_count, 2)
            self.assertEqual(result["status"], "QUALITY_EXHAUSTED")
            self.assertEqual(result["queue_ids"], [])
            self.assertEqual(result["attempts"][-1]["reason"], "READY_REVIEW_REPORT_INVALID")

    def test_public_summary_only_reports_fixed_invalid_envelope_codes(self):
        for code in ("GENERATION_OUTPUT_INVALID", "READY_REVIEW_REPORT_INVALID"):
            report = {
                "status": "FAILED", "mode": "EVERGREEN_BANK", "would_post": False,
                "evergreen_bank_by_account": {"beauty_account": {
                    "status": "QUALITY_EXHAUSTED",
                    "usable_evergreen": 22, "minimum": 30,
                }},
                "results": [{"account_id": "beauty_account",
                             "attempts": [{"failure_category": code,
                                           "queue_id": "private-not-to-print"}]}],
            }
            rendered, ok = summary.redacted_bank_summary(report, "beauty_account")
            self.assertFalse(ok)
            self.assertIn("category=" + code, rendered)
            self.assertNotIn("private-not-to-print", rendered)


if __name__ == "__main__":
    unittest.main()
