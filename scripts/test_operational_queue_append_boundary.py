#!/usr/bin/env python3
"""Offline adversarial cases for the operational queue append boundary.

No Google API, secrets, paid AI, social posting or other external access.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from sheets_client import (  # noqa: E402
    MockSheetsClient, SheetsClient, SheetsMutationOutcomeUnknown,
)


class FakeQueueWorksheet:
    headers = ["queue_id", "account_id", "platform", "status", "draft_id",
               "public_post_text", "created_at", "media_asset_id"]
    def __init__(self, records=None):
        self.headers = list(type(self).headers)
        self.rows = [dict(row) for row in (records or [])]
        self.append_count = 0
        self.read_count = 0
        self.lose_ack = False
        self.persist = True
        self.readback_fails = False
        self.duplicate_on_append = False
        self.append_modes = []

    def row_values(self, n):
        return list(self.headers)

    def get_all_values(self):
        self.read_count += 1
        if self.readback_fails and self.read_count > 1:
            raise ConnectionError("untrusted provider trace, never print")
        return [list(self.headers)] + [
            [str(r.get(h, "")) for h in self.headers] for r in self.rows
        ]

    def append_row(self, values, *, value_input_option):
        self.append_count += 1
        self.append_modes.append(value_input_option)
        if self.persist:
            row = dict(zip(self.headers, values))
            self.rows.append(row)
            if self.duplicate_on_append:
                self.rows.append(dict(row))
        if self.lose_ack:
            raise TimeoutError("sheets accepted mutation but response lost")


def make_client(ws, *, dry_run=False):
    client = object.__new__(SheetsClient)
    client._ws = lambda name: ws
    client.dry_run = dry_run
    client._call_with_rate_limit_retry = lambda _, fn: fn()
    return client


class OperationalAppendBoundaryTests(unittest.TestCase):
    def item(self, **overrides):
        return {
            "queue_id": "q-canonical-001",
            "account_id": "night_scout",
            "platform": "threads",
            "status": "WAITING_REVIEW",
            "draft_id": "d-001",
            "public_post_text": "=HYPERLINK(bad)",
            **overrides,
        }

    def test_append_is_raw_and_verified(self):
        ws = FakeQueueWorksheet()
        identity = make_client(ws).append_queue_item(self.item())
        self.assertEqual(identity, "q-canonical-001")
        self.assertEqual(ws.append_count, 1)
        self.assertEqual(ws.append_modes, ["RAW"])
        self.assertEqual(ws.rows[0]["public_post_text"], "=HYPERLINK(bad)")
        self.assertGreaterEqual(ws.read_count, 2)

    def test_preexisting_identity_rejected_without_mutating(self):
        ws = FakeQueueWorksheet([self.item(account_id="liver_manager")])
        with self.assertRaisesRegex(PermissionError, "identity_exists"):
            make_client(ws).append_queue_item(self.item())
        self.assertEqual(ws.append_count, 0)

    def test_same_id_rerun_after_ack_is_not_duplicate(self):
        ws = FakeQueueWorksheet()
        client = make_client(ws)
        client.append_queue_item(self.item())
        with self.assertRaises(PermissionError):
            client.append_queue_item(self.item())
        self.assertEqual(len(ws.rows), 1)
        self.assertEqual(ws.append_count, 1)

    def test_lost_ack_requires_operator_reconciliation_no_retry(self):
        ws = FakeQueueWorksheet()
        ws.lose_ack = True
        with self.assertRaisesRegex(SheetsMutationOutcomeUnknown, "manual_reconciliation"):
            make_client(ws).append_queue_item(self.item())
        self.assertEqual(ws.append_count, 1)
        self.assertEqual(len(ws.rows), 1)

    def test_stale_missing_or_duplicate_readback_is_never_success(self):
        for cause in ("readback_fails", "duplicate_on_append"):
            ws = FakeQueueWorksheet()
            setattr(ws, cause, True)
            with self.subTest(cause=cause), self.assertRaisesRegex(
                SheetsMutationOutcomeUnknown, "manual_reconciliation",
            ):
                make_client(ws).append_queue_item(self.item())
            self.assertEqual(ws.append_count, 1)

    def test_success_ack_without_persistence_is_not_success(self):
        ws = FakeQueueWorksheet()
        ws.persist = False
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            make_client(ws).append_queue_item(self.item())
        self.assertEqual(ws.append_count, 1)

    def test_media_ready_rejected_before_any_provider_io(self):
        ws = FakeQueueWorksheet()
        with self.assertRaisesRegex(PermissionError, "trusted_media_review"):
            make_client(ws).append_queue_item(self.item(
                status="READY", media_asset_id="restricted-asset",
            ))
        self.assertEqual(ws.read_count, 0)
        self.assertEqual(ws.append_count, 0)

    def test_missing_account_or_schema_denied_before_append(self):
        ws = FakeQueueWorksheet()
        with self.assertRaises(PermissionError):
            make_client(ws).append_queue_item(self.item(account_id=""))
        self.assertEqual(ws.append_count, 0)
        ws.headers.remove("status")
        with self.assertRaisesRegex(PermissionError, "schema_incomplete"):
            make_client(ws).append_queue_item(self.item())
        self.assertEqual(ws.append_count, 0)

    def test_dry_run_has_no_network_access(self):
        ws = FakeQueueWorksheet()
        self.assertEqual(make_client(ws, dry_run=True).append_queue_item(
            self.item(),
        ), "q-canonical-001")
        self.assertEqual(ws.read_count, 0)
        self.assertEqual(ws.append_count, 0)

    def test_queue_builder_calls_account_scoped_duplicate_lookup(self):
        from queue_builder import build_queue
        from unittest.mock import Mock, patch
        mock = Mock()
        mock.get_social_derivatives.return_value = [{
            "draft_id": "shared_draft", "account_id": "liver_manager",
            "platform": "threads", "status": "READY",
        }]
        mock.find_queue_item.return_value = {"queue_id": "existing_liver"}
        with patch("queue_builder.should_queue") as route, patch(
            "queue_builder._find_draft",
        ):
            self.assertEqual(build_queue(
                mock, account_id="liver_manager", platforms=["threads"],
            ), [])
        mock.find_queue_item.assert_called_once_with(
            "shared_draft", "threads", account_id="liver_manager",
        )
        route.assert_not_called()

    def test_account_scoped_queue_lookup_does_not_block_second_account(self):
        mock = MockSheetsClient(dry_run=False)
        mock.append_queue_item(self.item())
        for account, expected in (
            ("night_scout", "q-canonical-001"),
            ("liver_manager", None),
        ):
            got = mock.find_queue_item("d-001", "threads", account_id=account)
            self.assertEqual(got["queue_id"] if got else None, expected)
        mock.append_queue_item(self.item(
            queue_id="q-another", account_id="liver_manager",
        ))
        self.assertEqual(
            mock.find_queue_item("d-001", "threads",
                                 account_id="liver_manager")["queue_id"],
            "q-another",
        )
        # The publisher and queue_builder call the same account-scoped API.
        self.assertEqual(
            mock.find_queue_item("d-001", "threads",
                                 account_id="night_scout")["queue_id"],
            "q-canonical-001",
        )


if __name__ == "__main__":
    unittest.main()
