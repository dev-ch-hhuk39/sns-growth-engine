#!/usr/bin/env python3
"""Exercise strict health with offline Sheets boundaries, never live evidence."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_autonomous_health as health  # noqa: E402

PRIVATE = "PRIVATE_UNPUBLISHED_PROVIDER_OR_CREDENTIAL_VALUE"


def tables() -> dict[str, list[list[str]]]:
    headers = {
        "queue": ["queue_id", "account_id", "status", "text"],
        "posted_results": ["result_id", "account_id", "platform", "status"],
        "metrics_collection_jobs": ["job_id", "result_id", "account_id", "status"],
        "metric_snapshots": ["snapshot_id", "result_id", "account_id", "metrics_status"],
    }
    result = {}
    for logical, columns in headers.items():
        rows = [columns]
        for account, count in (("night_scout", 1), ("liver_manager", 2), ("beauty_account", 3)):
            for index in range(count):
                values = {columns[0]: f"{logical}_{account}_{index}", "account_id": account,
                          "result_id": f"result_{account}_{index}", "platform": "threads",
                          "status": PRIVATE, "metrics_status": PRIVATE, "text": PRIVATE}
                rows.append([values[column] for column in columns])
        result[logical] = rows
    return result


class MockSheetsBoundary:
    """The real CLI must refuse a mock-client instance, even if reads work."""


class StrictRuntimeTests(unittest.TestCase):
    def boundary(self, data=None, *, fail_tab=None, fail_config=False, fail_open=False,
                 mock_client=False, config_mock=False):
        data = copy.deepcopy(tables() if data is None else data)
        reads = []
        opened = []

        def get_config():
            print(PRIVATE)
            if fail_config:
                raise ValueError(PRIVATE)
            return {"sheet_id": "offline-fixture", "sa_dict": {"fixture": True},
                    "mock_sheets": config_mock}

        class Worksheet:
            def __init__(self, logical):
                self.logical = logical

            def get_all_values(self):
                reads.append(self.logical)
                print(PRIVATE, file=sys.stderr)
                if self.logical == fail_tab:
                    raise RuntimeError(PRIVATE)
                return data[self.logical]

        base = MockSheetsBoundary if mock_client else object

        class Client(base):
            def __init__(self, sheet_id, sa_dict, dry_run=False):
                opened.append((sheet_id, sa_dict, dry_run))
                print(PRIVATE)
                if fail_open:
                    raise RuntimeError(PRIVATE)

            def _ws(self, logical):
                return Worksheet(logical)

        config = types.ModuleType("config_loader")
        config.get_config = get_config
        sheets = types.ModuleType("sheets_client")
        sheets.SheetsClient = Client
        sheets.MockSheetsClient = MockSheetsBoundary
        return {"config_loader": config, "sheets_client": sheets}, reads, opened

    def execute(self, account="night_scout", *, argv=None, env=None, **kwargs):
        modules, reads, opened = self.boundary(**kwargs)
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, modules), patch.dict(health.os.environ, env or {}, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            if argv is None:
                result = health.build_strict_runtime_health(account)
                code = 0 if result["status"] == "READ_OK" else 1
            else:
                with patch.object(health.sys, "argv", ["health", *argv]):
                    code = health.main()
                result = json.loads(out.getvalue())
        self.assertNotIn(PRIVATE, out.getvalue() + err.getvalue() + json.dumps(result))
        self.assertFalse(result["would_write"])
        self.assertFalse(result["would_post"])
        return code, result, reads, opened

    def test_both_supported_accounts_read_only_required_tabs_and_scope_counts(self):
        for account, count in (("night_scout", 1), ("liver_manager", 2)):
            with self.subTest(account=account):
                code, result, reads, opened = self.execute(account)
                self.assertEqual(code, 0)
                self.assertEqual(result["status"], "READ_OK")
                self.assertEqual(result["health_scope"], "aftercare_required_runtime_reads")
                self.assertEqual(reads, ["queue", "posted_results", "metrics_collection_jobs", "metric_snapshots"])
                self.assertEqual(len(opened), 1)
                self.assertIs(opened[0][2], True)
                self.assertTrue(all(tab == {"status": "READ_OK", "row_count": count}
                                    for tab in result["tabs"].values()))
                self.assertNotIn("beauty_account", json.dumps(result))

    def test_header_only_tables_prove_reads_without_inventing_stock_or_metrics(self):
        empty = {key: [value[0]] for key, value in tables().items()}
        code, result, reads, _ = self.execute(data=empty)
        self.assertEqual(code, 0)
        self.assertEqual(len(reads), 4)
        self.assertTrue(all(tab["row_count"] == 0 for tab in result["tabs"].values()))
        self.assertNotIn("PASS", json.dumps(result))

    def test_unsupported_accounts_are_refused_before_configuration_or_reads(self):
        for account in ("all", "beauty_account", PRIVATE):
            with self.subTest(account=account):
                code, result, reads, opened = self.execute(account)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_requires_one_supported_account")
                self.assertEqual((reads, opened), ([], []))

    def test_mock_controls_and_actual_mock_instances_cannot_be_evidence(self):
        for args in ({"env": {"MOCK_SHEETS": "true"}}, {"env": {"MOCK_SHEETS": "1"}},
                     {"env": {"MOCK_SHEETS": "unexpected"}}, {"config_mock": True},
                     {"mock_client": True}):
            with self.subTest(args=args):
                code, result, reads, _ = self.execute(**args)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_mock_forbidden")
                self.assertEqual(reads, [])

    def test_configuration_and_provider_open_failures_are_sanitized_and_nonzero(self):
        for args, reason in (({"fail_config": True}, "strict_runtime_configuration_unavailable"),
                             ({"fail_open": True}, "strict_runtime_read_unavailable")):
            with self.subTest(args=args):
                code, result, reads, _ = self.execute(**args)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(reads, [])

    def test_each_required_table_failure_stops_without_retry_or_optional_table_read(self):
        expected = ["queue", "posted_results", "metrics_collection_jobs", "metric_snapshots"]
        for index, logical in enumerate(expected):
            with self.subTest(logical=logical):
                code, result, reads, _ = self.execute(fail_tab=logical)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_read_unavailable")
                self.assertEqual(reads, expected[:index + 1])

    def test_missing_empty_and_duplicate_headers_do_not_certify_the_table(self):
        for header in ([], ["queue_id", "status"], ["queue_id", "account_id", "status", "status"],
                       ["queue_id", "account_id", "status", ""], ["queue_id", "account_id", 7]):
            with self.subTest(header=header):
                data = tables()
                data["queue"] = [header]
                code, result, _, _ = self.execute(data=data)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_schema_invalid")

    def test_bad_row_shape_is_rejected_without_row_content(self):
        for row in (["extra"] * 5, [4, "night_scout", PRIVATE], "unexpected-row"):
            with self.subTest(row=row):
                data = tables()
                data["queue"].append(row)
                code, result, _, _ = self.execute(data=data)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_schema_invalid")

    def test_selected_duplicate_or_cross_account_identity_is_ambiguous(self):
        for owner in ("night_scout", "liver_manager", "beauty_account"):
            with self.subTest(owner=owner):
                data = tables()
                row = list(data["queue"][1])
                row[1] = owner
                data["queue"].append(row)
                code, result, _, _ = self.execute(data=data)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_identity_ambiguous")

    def test_blank_selected_identity_and_unscoped_nonempty_rows_fail_closed(self):
        for index, reason in ((0, "strict_runtime_identity_ambiguous"),
                              (1, "strict_runtime_account_unverified")):
            with self.subTest(index=index):
                data = tables()
                data["queue"][1][index] = ""
                code, result, _, _ = self.execute(data=data)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], reason)

    def test_wholly_blank_rows_are_ignored(self):
        data = tables()
        data["queue"].extend([[], ["", "", "", ""]])
        code, result, _, _ = self.execute(data=data)
        self.assertEqual(code, 0)
        self.assertEqual(result["tabs"]["queue"]["row_count"], 1)

    def test_padded_account_or_identity_cannot_hide_a_selected_row(self):
        for index, value, reason in ((0, "   ", "strict_runtime_identity_ambiguous"),
                                     (0, " padded ", "strict_runtime_identity_ambiguous"),
                                     (1, "night_scout ", "strict_runtime_account_unverified")):
            with self.subTest(index=index, value=value):
                data = tables()
                data["queue"][1][index] = value
                code, result, _, _ = self.execute(data=data)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], reason)

    def test_strict_cli_requires_explicit_readonly_and_sheets_before_any_io(self):
        for argv in (["--strict-runtime"], ["--strict-runtime", "--dry-run"],
                     ["--strict-runtime", "--use-sheets"]):
            with self.subTest(argv=argv):
                code, result, reads, opened = self.execute(argv=argv)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason"], "strict_runtime_requires_dry_run_and_sheets")
                self.assertEqual((reads, opened), ([], []))

    def test_strict_cli_propagates_real_read_failure_instead_of_legacy_warn_success(self):
        argv = ["--strict-runtime", "--dry-run", "--use-sheets", "--account-id", "liver_manager"]
        for fail_tab, expected in ((None, 0), ("metric_snapshots", 1)):
            with self.subTest(fail_tab=fail_tab):
                code, _, _, _ = self.execute(argv=argv, fail_tab=fail_tab)
                self.assertEqual(code, expected)

    def test_legacy_warn_behavior_and_cli_contract_are_unchanged(self):
        out = io.StringIO()
        with patch.object(health.sys, "argv", ["health", "--dry-run"]), \
                patch.object(health, "build_health", return_value={"status": "WARN"}) as legacy, \
                patch.object(health, "build_strict_runtime_health") as strict, redirect_stdout(out):
            self.assertEqual(health.main(), 0)
        legacy.assert_called_once_with("all", use_sheets=False)
        strict.assert_not_called()
        self.assertEqual(json.loads(out.getvalue()), {"status": "WARN"})


if __name__ == "__main__":
    unittest.main()
