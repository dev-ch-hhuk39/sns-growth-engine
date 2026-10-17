#!/usr/bin/env python3
"""Offline regression for gspread numericising RAW attribution cell values."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_growth_attribution_cycle import (  # noqa: E402
    AttributionWriteBlocked,
    _same_sheet_value,
    _upsert_rows,
)
from sheets_client import TAB_DEFINITIONS  # noqa: E402


class FakeWorksheet:
    def __init__(self, logical: str, rows: list[dict] | None = None) -> None:
        self.headers = list(TAB_DEFINITIONS[logical])
        self.rows = list(rows or [])
        self.batch_calls = 0
        self.append_calls = 0
        self.corrupt_readback = False

    def row_values(self, row: int) -> list[str]:
        assert row == 1
        return self.headers

    def get_all_records(self) -> list[dict]:
        return [dict(v) for v in self.rows]

    def batch_update(self, updates: list[dict], *, value_input_option: str) -> None:
        assert value_input_option == "RAW"
        self.batch_calls += 1
        for update in updates:
            # These synthetic fixtures need only a single existing record.
            row = dict(zip(self.headers, update["values"][0]))
            self.rows[0] = self._normalised(row)

    def append_rows(self, values: list[list], *, value_input_option: str) -> None:
        assert value_input_option == "RAW"
        self.append_calls += 1
        for values_row in values:
            row = dict(zip(self.headers, values_row))
            if self.corrupt_readback:
                row["performance_score"] = 999
            self.rows.append(self._normalised(row))

    @staticmethod
    def _normalised(row: dict) -> dict:
        # Emulate gspread's get_all_records numericising 1.0 as int 1.
        return {
            key: int(value) if isinstance(value, float) and value.is_integer() else value
            for key, value in row.items()
        }


class FakeClient:
    def __init__(self, ws: FakeWorksheet) -> None:
        self.ws = ws

    def _ws(self, _logical: str) -> FakeWorksheet:
        return self.ws


class NumericSheetsReadbackTests(unittest.TestCase):
    def test_numeric_whole_values_equal(self):
        self.assertTrue(_same_sheet_value("post_attributions", "performance_score", 1, 1.0))
        self.assertTrue(_same_sheet_value("post_attributions", "window_hours", "72", 72))
        self.assertTrue(_same_sheet_value("strategy_state", "sample_count", 3, 3.0))
        self.assertTrue(_same_sheet_value("strategy_state", "exploration_floor", "0.20", 0.2))

    def test_numeric_distinctions_not_erased(self):
        self.assertFalse(_same_sheet_value("post_attributions", "performance_score", 1, 1.01))
        self.assertFalse(_same_sheet_value("strategy_state", "sample_count", "", 0))
        self.assertFalse(_same_sheet_value("strategy_state", "confidence", True, 1.0))

    def test_identity_and_json_fields_stay_exact(self):
        self.assertFalse(_same_sheet_value("post_attributions", "attribution_id", "01", "1"))
        self.assertFalse(_same_sheet_value("post_attributions", "feature_evidence_json", "[1]", "[1.0]"))
        self.assertFalse(_same_sheet_value("strategy_state", "strategy_id", "001", "1"))

    def test_repeated_numeric_row_is_skipped_without_external_write(self):
        ws = FakeWorksheet("post_attributions", [{
            "attribution_id": "attr-001", "account_id": "night_scout",
            "window_hours": 72, "performance_score": 1,
            "created_at": "2026-10-16T00:00:00Z",
        }])
        proposed = [{
            "attribution_id": "attr-001", "account_id": "night_scout",
            "window_hours": 72.0, "performance_score": 1.0,
            "created_at": "2026-10-17T00:00:00Z",
        }]
        result = _upsert_rows(FakeClient(ws), "post_attributions", "attribution_id",
                              proposed, account_id="night_scout", max_changes=20)
        self.assertEqual(result["skipped"], 1)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(ws.batch_calls + ws.append_calls, 0)

    def test_appended_whole_numeric_value_readback_verifies(self):
        ws = FakeWorksheet("post_attributions")
        rows = [{
            "attribution_id": "attr-002", "account_id": "night_scout",
            "window_hours": 168, "performance_score": 1.0,
        }]
        result = _upsert_rows(FakeClient(ws), "post_attributions", "attribution_id",
                              rows, account_id="night_scout", max_changes=20)
        self.assertEqual(result["created"], 1)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(ws.append_calls, 1)
        self.assertEqual(ws.rows[0]["performance_score"], 1)

    def test_strategy_numeric_readback_verifies(self):
        ws = FakeWorksheet("strategy_state")
        rows = [{
            "strategy_id": "strategy-01", "account_id": "liver_manager",
            "sample_count": 5.0, "allocation_weight": 1.0,
            "exploration_floor": 0.20,
        }]
        result = _upsert_rows(FakeClient(ws), "strategy_state", "strategy_id",
                              rows, account_id="liver_manager", max_changes=20)
        self.assertEqual(result["created"], 1)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(ws.rows[0]["sample_count"], 5)

    def test_real_mismatch_remains_blocked_and_not_retried(self):
        ws = FakeWorksheet("post_attributions")
        ws.corrupt_readback = True
        rows = [{
            "attribution_id": "attr-003", "account_id": "night_scout",
            "performance_score": 0.42,
        }]
        with self.assertRaisesRegex(AttributionWriteBlocked, "attribution_external_outcome_unknown"):
            _upsert_rows(FakeClient(ws), "post_attributions", "attribution_id",
                         rows, account_id="night_scout", max_changes=20)
        self.assertEqual(ws.append_calls, 1)


if __name__ == "__main__":
    unittest.main()
