#!/usr/bin/env python3
"""An empty short manual slot window must be a no-op, not false READY PASS.

Synthetic only: absolutely no real Sheets, paid providers, or SNS publishes.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import unittest
from unittest.mock import Mock, patch

import maintain_text_ready_inventory as inventory
import ready_inventory_diagnostics as diagnostics


class NoDueTextSlotTests(unittest.TestCase):
    def run_inventory(self, horizon: int, *, apply: bool) -> tuple[int, dict]:
        args = ["maintain_text_ready_inventory.py", "--account-id", "liver_manager",
                "--horizon-hours", str(horizon)]
        if apply:
            args += ["--apply", "--confirm-ready-maintenance", "--use-sheets"]
        else:
            args.append("--dry-run")
        writer = Mock(side_effect=AssertionError("No remote Sheets client for empty manual window"))
        with (
            patch.object(sys, "argv", args),
            patch.object(inventory, "_required_text_slots", return_value=[]),
            patch.object(inventory, "SheetsClient", writer),
            patch.object(inventory, "get_config",
                         side_effect=AssertionError("No secrets for empty window")),
            patch.object(inventory, "replenish", side_effect=AssertionError("No generation")),
            redirect_stdout(StringIO()) as output,
        ):
            status = inventory.main()
        writer.assert_not_called()
        return status, json.loads(output.getvalue())

    def test_short_manual_apply_no_due_returns_explicit_skip_without_io(self):
        code, result = self.run_inventory(6, apply=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "SKIPPED_NO_DUE_TEXT_SLOTS")
        self.assertIsNone(result["text_delivery_coverage_72h_percent"])
        self.assertEqual(result["text_delivery_coverage_by_account"],
                         {"liver_manager": {"covered_slots": 0, "required_slots": 0}})
        self.assertEqual(result["coverage_failure_reason"], "NO_REQUIRED_TEXT_SLOTS")
        self.assertEqual(result["reserve_status"], "NOT_APPLICABLE")
        self.assertEqual(result["results"], [])
        self.assertFalse(result["would_post"])

    def test_short_manual_dry_run_no_due_is_a_noop(self):
        status, report = self.run_inventory(6, apply=False)
        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "SKIPPED_NO_DUE_TEXT_SLOTS")

    def test_short_skip_diagnostic_is_not_false_ready_success(self):
        _rc, data = self.run_inventory(6, apply=True)
        output = diagnostics.render_report(data, "liver_manager")
        self.assertIn("Maintenance outcome: SKIPPED_NO_DUE_TEXT_SLOTS", output)
        self.assertIn("not READY coverage PASS", output)
        self.assertIn("NO_DUE_TEXT_SLOTS_IN_REQUESTED_HORIZON", output)
        self.assertNotIn("Maintenance outcome: PASS", output)

    def test_invalid_skip_shapes_fail_closed_for_every_account(self):
        _rc, data = self.run_inventory(6, apply=True)
        variants = [
            {"horizon_hours": 24},
            {"horizon_hours": True},
            {"status": "PASS"},
            {"would_post": True},
            {"results": [{"account_id": "liver_manager"}]},
            {"text_delivery_coverage_72h_percent": 100.0},
            {"text_delivery_coverage_by_account":
             {"night_scout": {"covered_slots": 0, "required_slots": 0}}},
        ]
        for change in variants:
            with self.subTest(change=change):
                record = {**data, **change}
                if record["status"] == "PASS":
                    self.assertIn("Maintenance outcome: BLOCKED",
                                  diagnostics.render_report(record, "liver_manager"))
                else:
                    with self.assertRaises(ValueError):
                        diagnostics.render_report(record, "liver_manager")

    def test_long_horizon_zero_due_still_fails_closed(self):
        client = Mock()
        with (
            patch.object(sys, "argv", [
                "maintain_text_ready_inventory.py",
                "--account-id", "liver_manager", "--horizon-hours", "24",
                "--apply", "--confirm-ready-maintenance", "--use-sheets",
            ]),
            patch.object(inventory, "_required_text_slots", return_value=[]),
            patch.object(inventory, "SheetsClient", return_value=client),
            patch.object(inventory, "get_config",
                         return_value={"sheet_id": "synthetic", "sa_dict": {}}),
            patch.object(inventory, "read_records_safely", return_value=[]),
            redirect_stdout(StringIO()) as output,
        ):
            code = inventory.main()
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["coverage_failure_reason"], "NO_REQUIRED_TEXT_SLOTS")
        self.assertEqual(result["text_delivery_coverage_72h_percent"], 0.0)
        self.assertNotEqual(result["status"], "SKIPPED_NO_DUE_TEXT_SLOTS")

    def test_evergreen_bank_mode_is_not_skipped_by_no_due_slot_rule(self):
        _rc, short = self.run_inventory(6, apply=True)
        self.assertEqual(short["status"], "SKIPPED_NO_DUE_TEXT_SLOTS")
        with (
            patch.object(sys, "argv", [
                "maintain_text_ready_inventory.py", "--account-id", "liver_manager",
                "--horizon-hours", "6", "--evergreen-bank", "--dry-run",
            ]),
            patch.object(inventory, "_required_text_slots", side_effect=AssertionError("Due slots not relevant")),
            patch.object(inventory, "replenish_bank", return_value={
                "status": "PLAN_ONLY", "account_id": "liver_manager",
                "minimum": 30, "would_post": False,
            }) as bank,
            redirect_stdout(StringIO()) as output,
        ):
            code = inventory.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "EVERGREEN_BANK")
        bank.assert_called_once()


if __name__ == "__main__":
    unittest.main()
