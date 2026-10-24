#!/usr/bin/env python3
"""No-network postcommit bank cache refresh and identity verification."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import maintain_text_ready_inventory as inventory


def candidate():
    return {
        "queue_id": "q_new_safe", "account_id": "beauty_account",
        "slot_id": "beauty_1130", "status": "READY",
        "business_date_jst": "", "schedule_date_jst": "",
    }


def bank_entry():
    return {
        "queue_id": "q_new_safe", "account_id": "beauty_account",
        "fallback_id": "f_safe", "status": "VALIDATED",
    }


class PostcommitLiteralBankCacheTests(unittest.TestCase):
    def snapshot(self):
        return SimpleNamespace(_readonly_sheet_record_cache={
            "queue": [{"queue_id": "q_previous"}],
            "evergreen_bank": [{"queue_id": "q_previous"}],
            "posted_results": [{"queue_id": "q_posted"}],
        })

    def test_literal_read_recovers_new_append_hidden_from_earlier_batch(self):
        snapshot = self.snapshot()
        q = candidate()
        b = bank_entry()

        def read(_client, logical, *, preserve_strings=False):
            self.assertIs(_client, snapshot)
            self.assertTrue(preserve_strings)
            return [q] if logical == "queue" else [b]

        with patch.object(inventory, "read_records_safely", side_effect=read) as reader:
            inventory.refresh_verified_bank_cache_from_literal(snapshot, [q])

        self.assertEqual(reader.call_count, 2)
        cache = snapshot._readonly_sheet_record_cache
        self.assertEqual(cache["queue"], [q])
        self.assertEqual(cache["evergreen_bank"], [b])
        self.assertEqual(cache["posted_results"], [{"queue_id": "q_posted"}])
        self.assertIsNot(cache["queue"][0], q)

    def test_duplicate_or_missing_literal_results_cannot_increase_inventory(self):
        q = candidate()
        b = bank_entry()
        for queue_rows, bank_rows in (
            ([], [b]),
            ([q, q], [b]),
            ([q], []),
            ([q], [b, b]),
            ([{**q, "slot_id": "other"}], [b]),
            ([{**q, "status": "WAITING_REVIEW"}], [b]),
            ([{**q, "business_date_jst": "2026-11-01"}], [b]),
            ([q], [{**b, "account_id": "other"}]),
        ):
            with self.subTest(queue_count=len(queue_rows), bank_count=len(bank_rows)):
                snapshot = self.snapshot()
                before = dict(snapshot._readonly_sheet_record_cache)
                with patch.object(inventory, "read_records_safely", side_effect=[
                    queue_rows, bank_rows,
                ]):
                    with self.assertRaisesRegex(
                        RuntimeError, "EVERGREEN_POSTCOMMIT_LITERAL_READBACK_UNVERIFIED",
                    ):
                        inventory.refresh_verified_bank_cache_from_literal(snapshot, [q])
                self.assertEqual(snapshot._readonly_sheet_record_cache, before)

    def test_provider_exception_is_redacted_and_cache_is_unchanged(self):
        snapshot = self.snapshot()
        before = dict(snapshot._readonly_sheet_record_cache)
        with patch.object(inventory, "read_records_safely",
                          side_effect=RuntimeError("PRIVATE_SHEETS_SECRET")):
            with self.assertRaisesRegex(
                RuntimeError, "EVERGREEN_POSTCOMMIT_LITERAL_READBACK_UNVERIFIED",
            ) as outcome:
                inventory.refresh_verified_bank_cache_from_literal(snapshot, [candidate()])
        self.assertNotIn("PRIVATE_SHEETS_SECRET", str(outcome.exception))
        self.assertEqual(snapshot._readonly_sheet_record_cache, before)

    def test_ambiguous_or_oversized_admission_fails_before_external_read(self):
        with patch.object(inventory, "read_records_safely") as read:
            for admissions in ([], [candidate()] * 31):
                with self.assertRaisesRegex(ValueError, "EVERGREEN_POSTCOMMIT_SCOPE_INVALID"):
                    inventory.refresh_verified_bank_cache_from_literal(
                        self.snapshot(), admissions,
                    )
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
