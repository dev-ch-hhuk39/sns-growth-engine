#!/usr/bin/env python3
"""No evergreen inventory operation may change an approved queue's slot ID."""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from evergreen_inventory import (  # noqa: E402
    admit_bank_batch,
    allocate_bank_candidate,
    bank_record,
)
from maintain_text_ready_inventory import release_temporary_bank_allocations  # noqa: E402
from production_inventory import hashes  # noqa: E402


NOW = datetime(2026, 10, 18, 1, 0, tzinfo=timezone.utc)
SLOT_ID = "ns_1600_original"


def ready_queue(slot_id: str = SLOT_ID, *, date: str = "") -> dict:
    return {
        "queue_id": "q-bank-001", "slot_id": slot_id,
        "account_id": "night_scout", "target_account_id": "night_scout",
        "platform": "threads", "status": "READY",
        "generation_mode": "original_text",
        "public_post_text": "実際の投稿はしない検証用テキストです。",
        "validator_status": "PASS", "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "business_date_jst": date, "schedule_date_jst": date,
    }


class FakeInventory:
    def __init__(self, queue: dict):
        self.queues = [queue]
        exact, normalized = hashes(queue["public_post_text"])
        self.bank = [{
            "fallback_id": f"evergreen_{queue['queue_id']}",
            "queue_id": queue["queue_id"], "account_id": queue["account_id"],
            "status": "VALIDATED", "text_hash": exact,
            "normalized_hash": normalized, "use_count": "0",
        }]
        self.posted = []
        self.writes = []

    def records(self, _client, logical: str):
        return copy.deepcopy({
            "queue": self.queues,
            "evergreen_bank": self.bank,
            "posted_results": self.posted,
        }[logical])

    def update_row(self, _client, logical: str, key: str, value: str, fields: dict):
        if logical != "queue" or key != "queue_id":
            raise AssertionError("unexpected target")
        self.writes.append(copy.deepcopy(fields))
        matches = [row for row in self.queues if row[key] == value]
        if len(matches) != 1:
            return False
        matches[0].update(fields)
        return True


class EvergreenSlotIdentityTests(unittest.TestCase):
    def allocate(self, state: FakeInventory, slot_id: str = SLOT_ID,
                 date: str = "2026-10-19", *, apply: bool = True) -> dict:
        with patch("process_threads_queue.records", side_effect=state.records), patch(
            "process_threads_queue.update_row", side_effect=state.update_row
        ):
            return allocate_bank_candidate(
                object(), account="night_scout",
                slot={"slot_id": slot_id, "business_date_jst": date},
                now=NOW, runtime_check=lambda row: True,
                similar=lambda old, text: False, apply=apply,
            )

    def test_exact_same_slot_allocates_dates_only(self):
        state = FakeInventory(ready_queue())
        result = self.allocate(state)
        self.assertEqual(result["status"], "ALLOCATED")
        self.assertEqual(result["read_after_write"], "PASS")
        self.assertEqual(state.queues[0]["slot_id"], SLOT_ID)
        self.assertEqual(state.queues[0]["business_date_jst"], "2026-10-19")
        self.assertEqual(state.writes, [{
            "business_date_jst": "2026-10-19",
            "schedule_date_jst": "2026-10-19",
        }])

    def test_cross_slot_bank_candidate_is_not_reassigned(self):
        state = FakeInventory(ready_queue("ns_1400_reference"))
        result = self.allocate(state)
        self.assertEqual(result["status"], "NO_ELIGIBLE_EVERGREEN")
        self.assertEqual(result["reason"], "NO_APPROVED_BANK_IN_EXACT_IMMUTABLE_SLOT")
        self.assertEqual(state.queues[0]["slot_id"], "ns_1400_reference")
        self.assertFalse(state.writes)

    def test_missing_slot_does_not_authorize_identity_creation(self):
        state = FakeInventory(ready_queue(""))
        result = self.allocate(state)
        self.assertEqual(result["status"], "NO_ELIGIBLE_EVERGREEN")
        self.assertFalse(state.writes)

    def test_missing_target_identity_blocks_without_write(self):
        state = FakeInventory(ready_queue())
        for slot_id, date in (("", "2026-10-19"), (SLOT_ID, "")):
            result = self.allocate(state, slot_id, date)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"], "EVERGREEN_TARGET_SLOT_IDENTITY_MISSING")
        self.assertFalse(state.writes)

    def test_previous_allocated_date_not_reassigned(self):
        state = FakeInventory(ready_queue(date="2026-10-20"))
        result = self.allocate(state)
        self.assertEqual(result["status"], "NO_ELIGIBLE_EVERGREEN")
        self.assertEqual(state.queues[0]["business_date_jst"], "2026-10-20")
        self.assertFalse(state.writes)

    def test_dry_run_never_writes_even_for_eligible_bank(self):
        state = FakeInventory(ready_queue())
        result = self.allocate(state, apply=False)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertNotIn("slot_id", result["allocation"])
        self.assertFalse(state.writes)

    def test_temporary_bank_release_drops_dates_but_keeps_slot(self):
        state = FakeInventory(ready_queue(date="2026-10-25"))
        with patch("process_threads_queue.records", side_effect=state.records), patch(
            "process_threads_queue.update_row", side_effect=state.update_row
        ):
            release_temporary_bank_allocations(object(), copy.deepcopy(state.queues))
        self.assertEqual(state.queues[0]["slot_id"], SLOT_ID)
        self.assertEqual(state.queues[0]["business_date_jst"], "")
        self.assertEqual(state.queues[0]["schedule_date_jst"], "")
        self.assertEqual(state.writes, [{
            "business_date_jst": "", "schedule_date_jst": "",
        }])

    def test_temporary_release_refuses_missing_slot_identity(self):
        state = FakeInventory(ready_queue(""))
        with patch("process_threads_queue.records", side_effect=state.records), patch(
            "process_threads_queue.update_row", side_effect=state.update_row
        ):
            with self.assertRaisesRegex(RuntimeError, "EVERGREEN_TEMPORARY_SLOT_IDENTITY_MISSING"):
                release_temporary_bank_allocations(object(), copy.deepcopy(state.queues))
        self.assertFalse(state.writes)

    def test_batch_admission_retains_slot_id_and_clears_dates(self):
        import gspread.utils
        from sheets_record_reader import records_from_values

        candidate = ready_queue(date="2026-10-25")
        expected_record = bank_record(candidate, now=NOW, runtime_check=lambda _: True)
        qheaders = list(candidate)
        bheaders = list(expected_record)

        class Worksheet:
            def __init__(self, headers, initial=None):
                self.data = [headers] + ([list(initial)] if initial else [])
                self.edits = []

            def get_all_values(self):
                return copy.deepcopy(self.data)

            def batch_update(self, items, *, value_input_option):
                self.edits += list(items)
                for item in items:
                    row, col = gspread.utils.a1_to_rowcol(item["range"])
                    self.data[row - 1][col - 1] = item["values"][0][0]

            def append_rows(self, rows, *, value_input_option):
                self.data.extend(copy.deepcopy(rows))

        qws = Worksheet(qheaders, [candidate.get(h, "") for h in qheaders])
        bws = Worksheet(bheaders)
        client = type("Client", (), {"_ws": lambda _self, name:
                         qws if name == "queue" else bws})()
        with patch("process_threads_queue.records", return_value=[]):
            result = admit_bank_batch(client, [candidate], now=NOW,
                                      runtime_check=lambda _: True, apply=True)
        self.assertEqual(result["status"], "SAVED")
        stored = records_from_values(qws.get_all_values())[0]
        self.assertEqual(stored["slot_id"], SLOT_ID)
        self.assertEqual(stored["business_date_jst"], "")
        self.assertEqual(stored["schedule_date_jst"], "")
        self.assertEqual(len(qws.edits), 2)
        self.assertTrue(all(
            gspread.utils.a1_to_rowcol(item["range"])[1]
            in {qheaders.index("business_date_jst") + 1,
                qheaders.index("schedule_date_jst") + 1}
            for item in qws.edits
        ))
        self.assertEqual(len(bws.data), 2)


if __name__ == "__main__":
    unittest.main()
