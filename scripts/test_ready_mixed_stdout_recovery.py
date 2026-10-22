#!/usr/bin/env python3
"""No-network recovery of the final READY report from mixed private stdout."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import ready_inventory_diagnostics as reader

PRIVATE = "private unpublished caption and private provider details"


def final_report():
    return {
        "status": "FAILED",
        "would_post": False,
        "text_delivery_coverage_by_account": {
            "night_scout": {"covered_slots": 0, "required_slots": 1},
        },
        "results": [{
            "account_id": "night_scout",
            "delivery_slo": "FAIL",
            "delivery_generation_failure_category": "NO_VALIDATED_BANK_CANDIDATE",
            "public_post_text": PRIVATE,
            "queue_id": "private-identifier",
        }],
    }


class MixedReadyReportTests(unittest.TestCase):
    def test_last_report_is_recovered_after_unstructured_noise(self):
        stdout = (
            "SDK warning with private caption " + PRIVATE + "\n"
            + json.dumps({"candidate": {"draft": PRIVATE}}, ensure_ascii=False, indent=2)
            + "\n"
            + json.dumps(final_report(), ensure_ascii=False, indent=2)
            + "\n"
        )
        recovered = reader.parse_bounded_ready_json(stdout)
        self.assertEqual(recovered["status"], "FAILED")
        self.assertEqual(len(recovered["results"]), 1)
        view = reader.render_report(recovered, "night_scout")
        self.assertIn("NO_VALIDATED_BANK_CANDIDATE", view)
        self.assertNotIn(PRIVATE, view)
        self.assertNotIn("private-identifier", view)

    def test_valid_direct_report_contract_is_unchanged(self):
        raw = json.dumps({"status": "PASS", "results": [
            {"account_id": "night_scout", "delivery_slo": "PASS"}
        ]})
        self.assertEqual(reader.parse_bounded_ready_json(raw)["status"], "PASS")

    def test_no_plausible_summary_fails_closed(self):
        for raw in ("", "temporary startup warnings only", "{broken JSON"):
            with self.subTest(raw=raw[:10]):
                with self.assertRaises(ValueError):
                    reader.parse_bounded_ready_json(raw)

    def test_embedded_unrelated_objects_are_not_accepted(self):
        text = (
            json.dumps({"status": "PASS", "results": [], "public_post_text": PRIVATE})
            + "\n" + "no complete READY report"
        )
        with self.assertRaises(ValueError):
            reader.parse_bounded_ready_json(text)

    def test_oversized_and_excessive_candidates_fail_closed(self):
        with self.assertRaises(ValueError):
            reader.parse_bounded_ready_json("x" * 5_000_001)
        with self.assertRaises(ValueError):
            reader.parse_bounded_ready_json("{broken\n" * 513)

    def test_cli_keeps_failure_reason_private_and_job_failed(self):
        with tempfile.TemporaryDirectory() as root:
            report = Path(root) / "stdout"
            error = Path(root) / "stderr"
            report.write_text("non-json private log " + PRIVATE + "\n"
                              + json.dumps(final_report(), indent=2))
            error.write_text("")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = reader.main([
                    "--account-id", "night_scout",
                    "--report", str(report),
                    "--private-stderr", str(error),
                ])
            self.assertEqual(code, 0)  # reporter parsed it; original command still failed
            self.assertIn("NO_VALIDATED_BANK_CANDIDATE", output.getvalue())
            self.assertNotIn(PRIVATE, output.getvalue())
            self.assertNotIn("private-identifier", output.getvalue())

    def test_early_cli_block_is_classified_without_leaking_custom_reason(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "out"
            output = io.StringIO()
            payload = {"status": "BLOCKED", "reason": "apply_requires_one_account",
                       "would_post": False}
            path.write_text("private value must not leak" + chr(10)
                            + json.dumps(payload, indent=2), encoding="utf-8")
            with contextlib.redirect_stdout(output):
                status = reader.main(["--account-id", "night_scout", "--report", str(path)])
            self.assertEqual(status, 0)
            self.assertIn("MULTI_ACCOUNT_APPLY_BLOCKED", output.getvalue())
            self.assertNotIn("private value", output.getvalue())

            payload["reason"] = "SECRET_UNPUBLISHED_CUSTOMER_TEXT"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = reader.main(["--account-id", "night_scout", "--report", str(path)])
            self.assertEqual(status, 0)
            self.assertIn("UNCLASSIFIED_EARLY_BLOCK", output.getvalue())
            self.assertNotIn("SECRET_UNPUBLISHED_CUSTOMER_TEXT", output.getvalue())


if __name__ == "__main__":
    unittest.main()
