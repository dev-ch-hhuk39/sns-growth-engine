#!/usr/bin/env python3
"""Mock/Sheets shared queue identity and patch preflight regression.

No credentials or network access. Historical duplicate-ID rows are injected
only into synthetic test fixtures, never accepted by the normal append API.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from sheets_client import MockSheetsClient  # noqa: E402
from test_legacy_queue_write_safety import Worksheet, client_for  # noqa: E402


class QueueIdentityPreflightTests(unittest.TestCase):
    def test_single_update_refuses_cross_account_and_route_rewrites(self):
        for field, replacement in (
            ("account_id", "liver_manager"),
            ("platform", "x"), ("slot_id", "other-slot"),
            ("draft_id", "other-draft"),
        ):
            ws = Worksheet(status="WAITING_REVIEW")
            with self.subTest(field=field), self.assertRaisesRegex(
                PermissionError, "queue_immutable_identity_change",
            ):
                client_for(ws).update_queue_item("q1", **{field: replacement})
            self.assertEqual(ws.calls, 0)

    def test_queue_id_named_parameter_cannot_be_overwritten(self):
        ws = Worksheet()
        with self.assertRaises(TypeError):
            client_for(ws).update_queue_item("q1", queue_id="other-id")
        self.assertEqual(ws.calls, 0)

    def test_single_allows_identical_account_fields(self):
        ws = Worksheet(status="WAITING_REVIEW")
        client_for(ws).update_queue_item(
            "q1", account_id="night_scout", status="READY",
        )
        self.assertEqual(ws.calls, 1)
        self.assertEqual(ws.rows[0]["status"], "READY")
        self.assertEqual(ws.rows[0]["account_id"], "night_scout")

    def test_terminal_and_uncertain_ready_promotions_fail_closed(self):
        for status in (
            "PROCESSING", "POSTED", "REJECTED", "SUPERSEDED",
            "FAILED", "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED",
            "PUBLISH_OUTCOME_UNVERIFIED", "",
        ):
            ws = Worksheet(status=status)
            with self.subTest(status=status), self.assertRaisesRegex(
                PermissionError, "queue_ready_invalid_prior_state",
            ):
                client_for(ws).update_queue_item("q1", status="READY")
            self.assertEqual(ws.calls, 0)

    def test_bulk_missing_one_target_blocks_all_other_updates(self):
        ws = Worksheet()
        with self.assertRaisesRegex(PermissionError, "queue_bulk_missing_target"):
            client_for(ws).bulk_update_queue_items([
                ("q1", {"status": "READY"}),
                ("q2", {"status": "READY"}),
            ])
        self.assertEqual(ws.calls, 0)
        self.assertEqual(ws.rows[0]["status"], "WAITING_REVIEW")

    def test_bulk_identity_change_or_unrecognized_fields_no_write(self):
        for patches in (
            [("q1", {"account_id": "liver_manager", "status": "READY"})],
            [("q1", {"platform": "x"})],
            [("q1", {"unknown_field_only": "bogus"})],
        ):
            ws = Worksheet()
            with self.subTest(patches=patches), self.assertRaises(PermissionError):
                client_for(ws).bulk_update_queue_items(patches)
            self.assertEqual(ws.calls, 0)

    def test_bulk_duplicate_header_is_not_accepted(self):
        ws = Worksheet()
        ws.headers = list(ws.headers) + ["queue_id"]
        with self.assertRaisesRegex(PermissionError, "queue_bulk_header"):
            client_for(ws).bulk_update_queue_items([("q1", {"status": "READY"})])
        self.assertEqual(ws.calls, 0)

    def test_mock_mutation_has_same_identity_and_ready_rules(self):
        c = MockSheetsClient(dry_run=False)
        c.append_queue_item({
            "queue_id": "q_mock", "draft_id": "d1", "account_id": "night_scout",
            "platform": "threads", "slot_id": "ns_1600_original",
            "status": "WAITING_REVIEW",
        })
        for patch in (
            {"account_id": "liver_manager"},
            {"status": "POSTED", "account_id": "liver_manager"},
            {"slot_id": "another"},
            {"platform": "x"},
            {"draft_id": "d2"},
        ):
            with self.subTest(patch=patch), self.assertRaises(PermissionError):
                c.update_queue_item("q_mock", **patch)
        c.update_queue_item("q_mock", status="POSTED")
        with self.assertRaisesRegex(PermissionError, "queue_ready_invalid_prior_state"):
            c.update_queue_item("q_mock", status="READY")
        self.assertEqual(c.get_queue_item("q_mock")["status"], "POSTED")
        self.assertEqual(c.get_queue_item("q_mock")["account_id"], "night_scout")

    def test_mock_readers_fail_on_colliding_queue_or_draft_ids(self):
        c = MockSheetsClient(dry_run=False)
        c.append_queue_item({
            "queue_id": "q1", "draft_id": "d1", "account_id": "night_scout",
            "platform": "threads", "status": "WAITING_REVIEW",
        })
        c._queue.append({
            "queue_id": "q1", "draft_id": "d2", "account_id": "liver_manager",
            "platform": "threads", "status": "WAITING_REVIEW",
        })
        with self.assertRaisesRegex(PermissionError, "queue_lookup_ambiguous_identity"):
            c.get_queue_item("q1")
        with self.assertRaises(PermissionError):
            c.update_queue_item("q1", status="READY")
        c._queue.append({
            "queue_id": "q3", "draft_id": "d1", "account_id": "night_scout",
            "platform": "threads", "status": "WAITING_REVIEW",
        })
        with self.assertRaisesRegex(PermissionError, "queue_draft_identity_ambiguous"):
            c.find_queue_item("d1", "threads", account_id="night_scout")


if __name__ == "__main__":
    unittest.main()
