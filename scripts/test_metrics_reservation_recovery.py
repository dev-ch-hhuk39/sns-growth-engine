#!/usr/bin/env python3
"""Offline reservation persistence and CLI integration, no provider credentials."""
from __future__ import annotations

import copy
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from metrics_reservations import JOB_HEADERS, ReservationBlocked, plan_reservations, reserve_metrics
from metrics_collection_schedule import build_metric_collection_jobs
from process_threads_metric_jobs import classify_due_work
from process_threads_queue import schedule_metrics_after_post
import schedule_threads_metric_collection as cli

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
POST = dict(result_id="r1", account_id="night_scout", platform="threads", status="POSTED",
            verification_status="READ_AFTER_WRITE_PASS", external_post_id="18066462212730000",
            post_url="https://www.threads.com/@test/post/one", posted_at="2026-10-01T00:00:00+00:00")


class Sheet:
    def __init__(self, headers, rows):
        self.headers = list(headers)
        self.rows = copy.deepcopy(list(rows))
        self.calls = []
        self.mode = "ok"
        self.on_append = lambda: None

    def get_all_values(self):
        return [self.headers[:]] + [[str(row.get(h, "")) for h in self.headers] for row in self.rows]

    def append_rows(self, rows, value_input_option):
        self.calls.append((copy.deepcopy(rows), value_input_option))
        self.on_append()
        if self.mode != "before_write":
            self.rows.extend(dict(zip(self.headers, row)) for row in rows)
        if self.mode != "ok":
            raise TimeoutError("private provider details must not escape")


class Client:
    dry_run = False

    def __init__(self, jobs=()):
        self.tables = {"posted_results": Sheet(POST, [POST]),
                       "metrics_collection_jobs": Sheet(JOB_HEADERS, jobs)}

    def _ws(self, logical):
        return self.tables[logical]


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.expected = build_metric_collection_jobs([POST], [], now=NOW)
        self.client = Client()
        self.sheet = self.client._ws("metrics_collection_jobs")

    def reserve(self, apply=True):
        return reserve_metrics(self.client, account_id="night_scout", result_id="r1", apply=apply)

    def test_initial_write_and_repeat_return_verified_total(self):
        self.assertEqual(schedule_metrics_after_post(self.client, "r1"), 3)
        self.assertEqual(schedule_metrics_after_post(self.client, "r1"), 3)
        self.assertEqual(len(self.sheet.calls), 1)
        self.assertEqual(self.sheet.calls[0][1], "RAW")
        self.assertEqual(len(self.sheet.rows), 3)
        self.assertEqual(set(self.client.tables), {"posted_results", "metrics_collection_jobs"})

    def test_partial_repair_preserves_measured_job(self):
        measured = {**self.expected[0], "status": "COMPLETE", "attempt_count": "2"}
        self.sheet.rows = [measured]
        self.assertEqual(self.reserve()["verified_count"], 3)
        self.assertEqual(self.sheet.rows[0], measured)
        self.assertEqual(len(self.sheet.calls[0][0]), 2)

    def test_dry_run_and_dry_client_do_not_write(self):
        self.assertEqual(self.reserve(False)["missing_count"], 3)
        self.assertEqual(self.sheet.calls, [])
        self.client.dry_run = True
        with self.assertRaisesRegex(ReservationBlocked, "dry_run_client"):
            self.reserve()
        self.assertEqual(self.sheet.calls, [])

    def test_lost_response_reconciles_without_second_append(self):
        self.sheet.mode = "after_write"
        self.assertEqual(self.reserve()["verified_count"], 3)
        self.assertEqual(len(self.sheet.calls), 1)

    def test_unknown_outcome_stops_without_retry(self):
        self.sheet.mode = "before_write"
        with self.assertRaisesRegex(ReservationBlocked, "outcome_unknown_manual_reconciliation"):
            self.reserve()
        self.assertEqual(len(self.sheet.calls), 1)

    def test_partial_append_cannot_report_success_or_retry(self):
        def append(rows, value_input_option):
            self.sheet.calls.append(rows)
            self.sheet.rows.append(dict(zip(self.sheet.headers, rows[0])))
        self.sheet.append_rows = append
        with self.assertRaisesRegex(ReservationBlocked, "outcome_unknown"):
            self.reserve()
        self.assertEqual(len(self.sheet.calls), 1)

    def test_duplicate_cancelled_and_foreign_jobs_block_without_write(self):
        for rows in ([self.expected[0], self.expected[0]],
                     [{**self.expected[0], "status": "CANCELLED"}],
                     [{**self.expected[0], "account_id": "liver_manager"}],
                     [{**self.expected[0], "post_url": "https://wrong.example"}],
                     [{**self.expected[0], "scheduled_for": "2026-10-12T00:00:00Z"}]):
            with self.subTest(rows=rows):
                self.sheet.rows = rows
                with self.assertRaises(ReservationBlocked):
                    self.reserve()
                self.assertEqual(self.sheet.calls, [])

    def test_ambiguous_or_unverified_result_blocked(self):
        for rows in ([], [POST, POST], [dict(POST, account_id="liver_manager")],
                     [dict(POST, external_post_id="")], [dict(POST, status="PROCESSING")],
                     [dict(POST, verification_status="PENDING")], [dict(POST, posted_at="invalid")]):
            with self.subTest(rows=rows):
                self.client._ws("posted_results").rows = rows
                with self.assertRaises(ReservationBlocked):
                    self.reserve()
                self.assertEqual(self.sheet.calls, [])

    def test_readback_source_change_not_success(self):
        self.sheet.on_append = lambda: self.client._ws("posted_results").rows[0].update(account_id="liver_manager")
        with self.assertRaisesRegex(ReservationBlocked, "outcome_unknown"):
            self.reserve()
        self.assertEqual(len(self.sheet.calls), 1)

    def test_incomplete_schema_not_auto_created(self):
        self.sheet.headers.remove("job_id")
        with self.assertRaisesRegex(ReservationBlocked, "schema_incomplete"):
            self.reserve()
        self.assertEqual(self.sheet.calls, [])

    def test_completed_and_failed_jobs_not_reset(self):
        self.sheet.rows = [dict(job, status="FAILED", attempt_count="3") for job in self.expected]
        self.assertEqual(self.reserve()["verified_count"], 3)
        self.assertEqual(self.sheet.calls, [])

    def test_planner_does_not_mutate_inputs(self):
        before = copy.deepcopy(self.expected)
        plan = plan_reservations([POST], self.expected[:1], account_id="night_scout", result_id="r1", now=NOW)
        self.assertEqual(plan["missing_count"], 2)
        self.assertEqual(self.expected, before)

    def test_collector_never_uses_another_accounts_result(self):
        jobs = [dict(self.expected[0], account_id="liver_manager")]
        result = classify_due_work([POST], jobs, now=NOW)
        self.assertEqual(result["collect"], [])
        self.assertEqual(result["cancel"][0]["error_reason"], "posted_result_account_mismatch")

    def test_collector_rejects_duplicate_results_in_either_order(self):
        foreign = dict(POST, account_id="liver_manager", external_post_id="another-post")
        for rows in ([POST, foreign], [foreign, POST], [POST, POST]):
            result = classify_due_work(rows, self.expected[:1], now=NOW)
            self.assertEqual(result["collect"], [])
            self.assertEqual(result["cancel"][0]["error_reason"], "posted_result_ambiguous")

    def run_cli(self, args, env=None):
        output = io.StringIO()
        with patch.object(cli.sys, "argv", ["schedule", *args]), \
                patch.dict(os.environ, env or {}, clear=True), \
                patch.object(cli, "load_client", return_value=self.client) as load, redirect_stdout(output):
            code = cli.main()
        return code, json.loads(output.getvalue()), load

    def test_cli_missing_gates_block_before_client(self):
        for args in (["--apply"], ["--apply", "--dry-run"],
                     ["--apply", "--input-json", "/not/read"],
                     ["--use-sheets", "--input-json", "/not/read"],
                     ["--apply", "--use-sheets", "--confirm-metrics-schedule"]):
            code, result, load = self.run_cli(args)
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "BLOCKED")
            load.assert_not_called()

    def test_cli_reads_live_state_in_dry_run(self):
        code, result, load = self.run_cli(["--use-sheets", "--dry-run", "--account-id", "night_scout"])
        self.assertEqual(code, 0)
        self.assertEqual(result["job_count"], 3)
        load.assert_called_once_with(apply=False)
        self.assertEqual(self.sheet.calls, [])

    def test_cli_repair_one_exact_result(self):
        code, result, load = self.run_cli(
            ["--apply", "--use-sheets", "--confirm-metrics-schedule", "--account-id", "night_scout", "--result-id", "r1"],
            {"ALLOW_METRICS_SCHEDULE_WRITE": "true"})
        self.assertEqual(code, 0)
        self.assertEqual(result["verified_count"], 3)
        load.assert_called_once_with(apply=True)

    def test_cli_does_not_expand_beauty_scope_or_bulk_repair(self):
        for account in ("beauty_account", "all"):
            code, _, load = self.run_cli(
                ["--apply", "--use-sheets", "--confirm-metrics-schedule", "--account-id", account, "--result-id", "r1"],
                {"ALLOW_METRICS_SCHEDULE_WRITE": "true"})
            self.assertEqual(code, 1)
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
