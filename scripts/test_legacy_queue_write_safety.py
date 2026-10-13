#!/usr/bin/env python3
"""Offline adversarial tests for legacy operational Sheets mutation safety.

Covers the existing queue writers during a staged SQLite cutover. No credentials,
providers, SNS API, database migrations or live mutation are involved.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from gspread.utils import a1_to_rowcol  # noqa: E402

import auto_approve_queue as auto_ready  # noqa: E402
import process_threads_queue as publisher_queue  # noqa: E402
from sheets_client import SheetsClient, SheetsMutationOutcomeUnknown  # noqa: E402


class Worksheet:
    headers = ("queue_id", "account_id", "platform", "status", "public_post_text",
               "validator_status", "internal_leak_status", "account_fit_status")

    def __init__(self, *, status="WAITING_REVIEW", rows=None):
        self.rows = [dict(row) for row in rows] if rows is not None else [{
            "queue_id": "q1", "account_id": "night_scout", "platform": "threads",
            "status": status, "public_post_text": "=HYPERLINK(unsafe)",
        }]
        self.calls = 0
        self.append_calls = 0
        self.fail_after_write = False
        self.ignore_write = False
        self.fail_readback = False
        self.write_modes = []

    def get_all_values(self):
        if self.fail_readback and self.calls:
            raise ConnectionError("provider read unavailable")
        return [list(self.headers)] + [
            [str(row.get(h, "")) for h in self.headers] for row in self.rows
        ]

    def row_values(self, number):
        if number == 1:
            return list(self.headers)
        if self.fail_readback and self.calls:
            raise ConnectionError("provider read unavailable")
        return [str(self.rows[number - 2].get(h, "")) for h in self.headers]

    def find(self, key, *, in_column):
        for number, row in enumerate(self.rows, start=2):
            if str(row.get(self.headers[in_column - 1], "")) == str(key):
                return SimpleNamespace(row=number)
        return None

    def batch_update(self, ranges, *, value_input_option):
        self.calls += 1
        self.write_modes.append(value_input_option)
        if not self.ignore_write:
            for item in ranges:
                row, col = a1_to_rowcol(item["range"])
                self.rows[row - 2][self.headers[col - 1]] = str(item["values"][0][0])
        if self.fail_after_write:
            raise TimeoutError("ack lost after Sheets mutation")

    def append_row(self, values, *, value_input_option):
        self.append_calls += 1
        self.write_modes.append(value_input_option)
        self.rows.append(dict(zip(self.headers, values)))
        if self.fail_after_write:
            raise TimeoutError("append accepted, ack lost")


def client_for(ws: Worksheet, *, dry_run=False):
    client = object.__new__(SheetsClient)
    client.dry_run = dry_run
    client._ws = lambda logical: ws
    client._call_with_rate_limit_retry = lambda label, fn: fn()
    return client


class OperationalQueueWriteSafety(unittest.TestCase):
    def test_bulk_verified_once_and_raw_string_payload(self):
        ws = Worksheet()
        client = client_for(ws)
        count = client.bulk_update_queue_items([
            ("q1", {"status": "READY", "public_post_text": "=HYPERLINK(unsafe)"}),
        ])
        self.assertEqual(count, 1)
        self.assertEqual(ws.calls, 1)
        self.assertEqual(ws.write_modes, ["RAW"])
        self.assertEqual(ws.rows[0]["status"], "READY")
        self.assertEqual(ws.rows[0]["public_post_text"], "=HYPERLINK(unsafe)")

    def test_bulk_accepted_but_response_lost_is_not_replayed(self):
        ws = Worksheet()
        ws.fail_after_write = True
        client = client_for(ws)
        with self.assertRaisesRegex(SheetsMutationOutcomeUnknown, "manual_reconciliation"):
            client.bulk_update_queue_items([("q1", {"status": "READY"})])
        self.assertEqual(ws.calls, 1)
        self.assertEqual(ws.rows[0]["status"], "READY")

    def test_bulk_without_confirmed_readback_fails_closed(self):
        for cause in ("ignore_write", "fail_readback"):
            ws = Worksheet()
            setattr(ws, cause, True)
            with self.subTest(cause=cause), self.assertRaises(SheetsMutationOutcomeUnknown):
                client_for(ws).bulk_update_queue_items([("q1", {"status": "READY"})])
            self.assertEqual(ws.calls, 1)

    def test_bulk_duplicate_queue_ids_and_stale_status_blocked_before_write(self):
        baseline = Worksheet().rows[0]
        for rows, updates in (
            ([baseline, dict(baseline)], [("q1", {"status": "READY"})]),
            ([baseline], [("q1", {"status": "READY"}), ("q1", {"status": "READY"})]),
            ([{**baseline, "status": "POSTED"}], [("q1", {"status": "READY"})]),
        ):
            ws = Worksheet(rows=rows)
            with self.subTest(rows=rows, updates=updates), self.assertRaises(PermissionError):
                client_for(ws).bulk_update_queue_items(updates)
            self.assertEqual(ws.calls, 0)

    def test_single_queue_update_is_one_raw_write_with_verified_readback(self):
        ws = Worksheet()
        client_for(ws).update_queue_item("q1", status="READY")
        self.assertEqual(ws.rows[0]["status"], "READY")
        self.assertEqual(ws.calls, 1)
        self.assertEqual(ws.write_modes, ["RAW"])

    def test_single_queue_unknown_and_mismatch_never_retry(self):
        for cause in ("fail_after_write", "ignore_write", "fail_readback"):
            ws = Worksheet()
            setattr(ws, cause, True)
            with self.subTest(cause=cause), self.assertRaises(SheetsMutationOutcomeUnknown):
                client_for(ws).update_queue_item("q1", status="READY")
            self.assertEqual(ws.calls, 1)

    def test_publisher_append_unknown_is_single_attempt(self):
        ws = Worksheet()
        ws.fail_after_write = True
        client = client_for(ws)
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            publisher_queue.append_row(client, "posted_results", {
                "queue_id": "q2", "account_id": "night_scout",
            })
        self.assertEqual(ws.append_calls, 1)
        self.assertEqual(ws.write_modes, ["RAW"])

    def test_publisher_queue_mutation_no_retry_and_dry_run_denied(self):
        ws = Worksheet()
        ws.fail_after_write = True
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            publisher_queue.update_row(
                client_for(ws), "queue", "queue_id", "q1", {"status": "PROCESSING"},
            )
        self.assertEqual(ws.calls, 1)
        dry = client_for(ws, dry_run=True)
        with self.assertRaises(PermissionError):
            publisher_queue.append_row(dry, "posted_results", {"queue_id": "q2"})
        with self.assertRaises(PermissionError):
            publisher_queue.update_row(
                dry, "queue", "queue_id", "q1", {"status": "PROCESSING"},
            )
        self.assertEqual(ws.calls, 1)
        self.assertEqual(ws.append_calls, 0)

    def test_failed_auto_ready_never_logs_false_success(self):
        class Fake:
            _queue = [{
                "queue_id": "q1", "account_id": "night_scout",
                "platform": "threads", "status": "WAITING_REVIEW",
            }]
            _drafts = []
            _derivatives = []
            def __init__(self):
                self.logs = []
            def bulk_update_queue_items(self, updates):
                raise SheetsMutationOutcomeUnknown("queue_bulk_update_outcome_unknown_manual_reconciliation")
            def log(self, **kwargs):
                self.logs.append(kwargs)
        client = Fake()
        plan = {"results": [{
            "status": "APPROVABLE", "queue_id": "q1", "account_id": "night_scout",
            "quality_score": 90, "safety_score": 100, "risk_score": 0, "score_total": 190,
        }]}
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            auto_ready.apply_ready(client, plan)
        self.assertEqual(client.logs, [])


if __name__ == "__main__":
    unittest.main()
