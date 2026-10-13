#!/usr/bin/env python3
"""Offline adversarial tests for bounded strategy persistence and zero-AI READY.

No Google credentials, Google API writes, SNS posts or paid AI calls.
"""
from __future__ import annotations

import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import evergreen_inventory  # noqa: E402
import maintain_text_ready_inventory as ready  # noqa: E402
import run_growth_attribution_cycle as attribution  # noqa: E402
from sheets_client import TAB_DEFINITIONS  # noqa: E402


class FakeSheet:
    def __init__(self, logical, rows=None, *, truncated_headers=False):
        self.headers = list(TAB_DEFINITIONS[logical])
        if truncated_headers:
            self.headers.remove("account_id")
        self.rows = [dict(row) for row in (rows or [])]
        self.operations = []
        self.fail_after_write = False
        self.readback_stale = False
        self.read_calls = 0

    def row_values(self, number):
        assert number == 1
        return self.headers

    def get_all_records(self):
        self.read_calls += 1
        if self.readback_stale and self.read_calls > 1:
            return []
        return [dict(row) for row in self.rows]

    def append_rows(self, rows, *, value_input_option):
        self.operations.append(("append", value_input_option))
        assert value_input_option == "RAW"
        self.rows.extend(dict(zip(self.headers, values)) for values in rows)
        if self.fail_after_write:
            raise TimeoutError("provider_ack_lost")

    def batch_update(self, updates, *, value_input_option):
        self.operations.append(("update", value_input_option))
        assert value_input_option == "RAW"
        for item in updates:
            target = re.search(r"A(\d+):", item["range"])
            assert target is not None
            row_number = int(target.group(1)) - 2
            self.rows[row_number] = dict(zip(self.headers, item["values"][0]))
        if self.fail_after_write:
            raise TimeoutError("provider_ack_lost")


class FakeReportingClient:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.queries = []

    def _ws(self, logical):
        self.queries.append(logical)
        return self.worksheet

    def _ensure_tab(self, *_args):
        raise AssertionError("cannot mutate operational tabs or create tabs")


def call_main(module, *args):
    buf = io.StringIO()
    with patch.object(module.sys, "argv", ["mock", *args]), redirect_stdout(buf):
        status = module.main()
    return status, json.loads(buf.getvalue())


class BoundedStrategyPersistenceTests(unittest.TestCase):
    account = "night_scout"

    def persist(self, sheet, rows, *, key="attribution_id", logical="post_attributions",
                account="night_scout", max_changes=10):
        return attribution._upsert_rows(
            FakeReportingClient(sheet), logical, key, rows,
            account_id=account, max_changes=max_changes,
        )

    def test_new_verified_raw_evidence_row(self):
        sheet = FakeSheet("post_attributions")
        row = {
            "attribution_id": "attr_001", "account_id": "night_scout",
            "explanation": "=HYPERLINK(\"https://unsafe.example\")",
            "created_at": "2026-10-13T01:00:00Z",
        }
        result = self.persist(sheet, [row])
        self.assertEqual(result["created"], 1)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(sheet.operations, [("append", "RAW")])
        self.assertEqual(sheet.rows[0]["explanation"], row["explanation"])

    def test_repeated_identical_rows_do_not_write_or_duplicate(self):
        sheet = FakeSheet("post_attributions")
        base = {
            "attribution_id": "attr_001", "account_id": "night_scout",
            "explanation": "measured evidence only",
            "created_at": "2026-10-13T00:00:00Z",
        }
        self.persist(sheet, [base])
        result = self.persist(sheet, [{**base, "created_at": "2026-10-13T01:00:00Z"}])
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(len(sheet.rows), 1)
        self.assertEqual(sheet.operations, [("append", "RAW")])

    def test_preexisting_row_changes_only_under_exact_key(self):
        sheet = FakeSheet("post_attributions", [{
            "attribution_id": "attr_001", "account_id": "night_scout",
            "explanation": "old evidence", "created_at": "first",
        }])
        result = self.persist(sheet, [{
            "attribution_id": "attr_001", "account_id": "night_scout",
            "explanation": "revised evidence", "created_at": "new",
        }])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(sheet.operations, [("update", "RAW")])
        self.assertEqual(sheet.rows[0]["created_at"], "first")
        self.assertEqual(sheet.rows[0]["explanation"], "revised evidence")

    def test_strategy_rows_are_scoped_and_readback_verified(self):
        sheet = FakeSheet("strategy_state")
        result = self.persist(
            sheet, [{
                "strategy_id": "strategy_001", "account_id": "liver_manager",
                "allocation_weight": 1.0, "exploration_floor": 0.2,
                "status": "ACTIVE",
            }],
            key="strategy_id", logical="strategy_state",
            account="liver_manager",
        )
        self.assertTrue(result["readback_verified"])
        self.assertEqual(sheet.rows[0]["account_id"], "liver_manager")

    def test_strategy_same_evidence_does_not_rewrite_timestamp(self):
        sheet = FakeSheet("strategy_state", [{
            "strategy_id": "strategy_001", "account_id": "night_scout",
            "sample_count": 14, "allocation_weight": 1.0,
            "updated_at": "first",
        }])
        result = self.persist(
            sheet, [{
                "strategy_id": "strategy_001", "account_id": "night_scout",
                "sample_count": 14, "allocation_weight": 1.0,
                "updated_at": "later",
            }], key="strategy_id", logical="strategy_state",
        )
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(sheet.rows[0]["updated_at"], "first")
        self.assertEqual(sheet.operations, [])

    def test_wrong_account_or_duplicate_key_rejected_before_mutation(self):
        for rows in (
            [{"attribution_id": "attr_001", "account_id": "liver_manager"}],
            [{"attribution_id": "", "account_id": "night_scout"}],
            [
                {"attribution_id": "attr_001", "account_id": "night_scout"},
                {"attribution_id": "attr_001", "account_id": "night_scout"},
            ],
        ):
            with self.subTest(rows=rows):
                sheet = FakeSheet("post_attributions")
                with self.assertRaises(attribution.AttributionWriteBlocked):
                    self.persist(sheet, rows)
                self.assertEqual(sheet.operations, [])

    def test_same_key_occupied_by_other_account_is_blocked(self):
        sheet = FakeSheet("post_attributions", [
            {"attribution_id": "attr_001", "account_id": "liver_manager"},
        ])
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_existing_account_mismatch"
        ):
            self.persist(sheet, [
                {"attribution_id": "attr_001", "account_id": "night_scout"},
            ])
        self.assertFalse(sheet.operations)

    def test_duplicate_existing_key_is_blocked(self):
        sheet = FakeSheet("post_attributions", [
            {"attribution_id": "attr_001", "account_id": "night_scout"},
            {"attribution_id": "attr_001", "account_id": "night_scout"},
        ])
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_existing_duplicate_key"
        ):
            self.persist(sheet, [
                {"attribution_id": "attr_001", "account_id": "night_scout"},
            ])
        self.assertEqual(sheet.operations, [])

    def test_missing_schema_is_never_auto_migrated(self):
        sheet = FakeSheet("post_attributions", truncated_headers=True)
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_output_schema_unverified"
        ):
            self.persist(sheet, [{
                "attribution_id": "attr_001", "account_id": "night_scout",
            }])
        self.assertEqual(sheet.operations, [])

    def test_budget_rejects_before_any_write(self):
        sheet = FakeSheet("post_attributions")
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_write_budget_exceeded"
        ):
            self.persist(sheet, [
                {"attribution_id": f"attr_{n}", "account_id": "night_scout"}
                for n in range(11)
            ])
        self.assertEqual(sheet.operations, [])

    def test_ambiguous_write_stops_without_retry(self):
        sheet = FakeSheet("post_attributions")
        sheet.fail_after_write = True
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_external_outcome_unknown"
        ):
            self.persist(sheet, [{
                "attribution_id": "attr_001", "account_id": "night_scout",
            }])
        self.assertEqual(sheet.operations, [("append", "RAW")])
        self.assertEqual(len(sheet.rows), 1)

    def test_missing_readback_is_unknown_not_success(self):
        sheet = FakeSheet("post_attributions")
        sheet.readback_stale = True
        with self.assertRaisesRegex(
            attribution.AttributionWriteBlocked, "attribution_external_outcome_unknown"
        ):
            self.persist(sheet, [{
                "attribution_id": "attr_001", "account_id": "night_scout",
            }])
        self.assertEqual(sheet.operations, [("append", "RAW")])

    def test_apply_with_no_real_measured_rows_never_writes(self):
        class MockClient:
            def __init__(self, *_args, **_kwargs):
                pass
            def _ws(self, *_args):
                raise AssertionError("no measured data must not open output tab")
            def _ensure_tab(self, *_args):
                raise AssertionError("no operational tab changes")
        with patch("config_loader.get_config", return_value={
            "sheet_id": "fake", "sa_dict": {},
        }), patch("sheets_client.SheetsClient", MockClient), patch.object(
            attribution, "_read_tab", return_value=([], ""),
        ), patch.object(
            attribution, "build_growth_cycle",
            return_value={
                "status": "PLAN_ONLY", "observation_count": 0,
                "attributions": [], "strategy_state": [],
            },
        ):
            code, payload = call_main(
                attribution, "--account-id", "night_scout", "--apply",
                "--confirm-attribution", "--use-sheets",
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "NO_MEASURED_OBSERVATIONS")
        self.assertFalse(payload["would_write"])

    def test_writer_budget_rejected_before_output_tabs(self):
        class MockClient:
            def __init__(self, *_args, **_kwargs):
                pass
            def _ws(self, *_args):
                raise AssertionError("budget refusal must not open output tab")
        with patch("config_loader.get_config", return_value={
            "sheet_id": "fake", "sa_dict": {},
        }), patch("sheets_client.SheetsClient", MockClient), patch.object(
            attribution, "_read_tab", return_value=([], ""),
        ), patch.object(
            attribution, "build_growth_cycle",
            return_value={
                "status": "PLAN_ONLY", "observation_count": 100,
                "attributions": [{"account_id": "night_scout"}] * 125,
                "strategy_state": [],
            },
        ):
            code, payload = call_main(
                attribution, "--account-id", "night_scout", "--apply",
                "--confirm-attribution", "--use-sheets",
                "--max-write-rows", "120",
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["reason"], "attribution_write_budget_exceeded")
        self.assertFalse(payload["would_write"])


class NoPaidReadyReuseTests(unittest.TestCase):
    slot = {
        "slot_id": "ns_1400_reference",
        "post_type": "reference_text",
        "business_date_jst": "2026-10-13",
    }

    def _execute(self, *args, ready_rows=None, slots=None, allocator=None):
        class FakeClient:
            dry_run = False
            def __init__(self, *_args, **kwargs):
                self.dry_run = kwargs.get("dry_run")
            def _ws(self, logical):
                assert logical == "evergreen_bank"
                return object()
            def _ensure_tab(self, *_args):
                raise AssertionError("bank reuse cannot auto-migrate operational tabs")
        def fake_allocate(*_args, **_kwargs):
            return {"status": "NO_VALIDATED_BANK_CANDIDATE"}
        with patch.object(
            ready, "get_config", return_value={"sheet_id": "fake", "sa_dict": {}},
        ), patch.object(
            ready, "SheetsClient", FakeClient,
        ), patch.object(
            ready, "read_records_safely", return_value=[],
        ), patch.object(
            ready, "_required_text_slots",
            return_value=slots if slots is not None else [self.slot],
        ), patch.object(
            ready, "_publishable_ready_rows",
            return_value=ready_rows if ready_rows is not None else [],
        ), patch.object(
            ready, "replenish", side_effect=AssertionError("paid generation forbidden"),
        ) as generated, patch.object(
            ready, "replenish_bank",
            side_effect=AssertionError("evergreen bank generation forbidden"),
        ) as bank_generate, patch.object(
            ready, "prime_readonly_record_cache", return_value=None,
        ), patch.object(
            evergreen_inventory, "allocate_bank_candidate",
            side_effect=allocator or fake_allocate,
        ) as allocated:
            code, payload = call_main(
                ready, "--account-id", "night_scout",
                "--apply", "--confirm-ready-maintenance", "--use-sheets",
                "--reuse-only", *args,
            )
        return code, payload, generated, bank_generate, allocated

    def test_reuse_only_with_no_bank_candidate_never_calls_ai(self):
        code, payload, generated, bank_generate, allocated = self._execute()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "FAILED")
        self.assertFalse(payload["would_post"])
        self.assertEqual(
            payload["results"][0]["delivery_generation_status"],
            "SKIPPED_PAID_GENERATION_REUSE_ONLY",
        )
        budget = payload["results"][-1]
        self.assertFalse(budget["paid_ai_requests_allowed"])
        self.assertEqual(budget["allocation_count"], 0)
        generated.assert_not_called()
        bank_generate.assert_not_called()
        self.assertEqual(allocated.call_count, 1)

    def test_bank_allocations_bounded_across_multiple_slots(self):
        calls = []
        def allocator(*_args, **_kwargs):
            calls.append(len(calls))
            return {"status": "ALLOCATED", "queue_id": f"validated_q_{len(calls)}"}
        code, payload, generated, _bank, allocated = self._execute(
            "--max-bank-allocations", "2",
            ready_rows=[{"queue_id": "eligible", "account_id": "night_scout"}],
            slots=[self.slot, {**self.slot, "slot_id": "ns_1600_original"}],
            allocator=allocator,
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["results"][-1]["allocation_count"], 2)
        self.assertEqual(allocated.call_count, 2)
        generated.assert_not_called()

    def test_zero_budget_does_not_call_allocator(self):
        code, payload, generated, _bank, allocated = self._execute(
            "--max-bank-allocations", "0",
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["results"][-1]["allocation_limit"], 0)
        generated.assert_not_called()
        allocated.assert_not_called()

    def test_reuse_only_blocks_unbounded_or_ai_evergreen_mode_before_credentials(self):
        for extra in (
            ("--max-bank-allocations", "7"),
            ("--max-bank-allocations", "-1"),
            ("--evergreen-bank",),
        ):
            with self.subTest(extra=extra), patch.object(
                ready, "get_config", side_effect=AssertionError("no credentials")
            ) as cfg:
                code, payload = call_main(
                    ready, "--account-id", "night_scout", "--apply",
                    "--confirm-ready-maintenance", "--use-sheets",
                    "--reuse-only", *extra,
                )
                self.assertEqual(code, 1)
                self.assertEqual(payload["status"], "BLOCKED")
                cfg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
