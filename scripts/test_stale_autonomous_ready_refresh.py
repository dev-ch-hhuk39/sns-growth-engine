#!/usr/bin/env python3
"""Stale automatic approvals are withdrawn, never silently bypassed."""
import copy
import unittest
from unittest.mock import patch

import run_hybrid_ai_queue_gate as gate
from run_hybrid_ready_pipeline import gate_command
import run_scheduled_text_slot_pipeline as scheduled


class Client:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.writes = []

    def get_queue_items(self, **filters):
        return [dict(r) for r in self.rows if all(r.get(k) == v for k, v in filters.items())]

    def update_queue_item(self, queue_id, **fields):
        self.writes.append(queue_id)
        next(r for r in self.rows if r["queue_id"] == queue_id).update(fields)

    def log(self, **kwargs):
        pass


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(queue_id="auto", account_id="liver_manager", platform="threads",
                        status="READY", auto_publish="true", slot_id="lm_1600_direct_media")

    def refresh(self, client, apply=True):
        with patch.object(gate, "account_allows_autonomous_ready", return_value=True), \
             patch.object(gate, "requires_hybrid_ai_gate", return_value=True), \
             patch.object(gate, "build_source_context", return_value={}), \
             patch.object(gate, "hybrid_ai_gate_current", return_value=(False, "schema_stale")):
            return gate.refresh_stale_autonomous_ready(client, "liver_manager", 1, apply=apply)

    def test_withdrawal_and_readback(self):
        client = Client([self.row, {**self.row, "queue_id": "second"}])
        self.assertEqual(self.refresh(client), ["auto"])
        self.assertEqual(client.rows[0]["status"], "WAITING_REVIEW")
        self.assertEqual(client.rows[0]["auto_publish"], "false")
        self.assertEqual(client.rows[1]["status"], "READY")
        self.assertEqual(self.refresh(Client([client.rows[0]])), [])

    def test_dry_run_writes_nothing(self):
        client = Client([self.row])
        self.assertEqual(self.refresh(client, False), ["auto"])
        self.assertEqual(client.writes, [])

    def test_protected_rows(self):
        for fields in ({"status": "POSTED"}, {"human_review_decision": "OK"},
                       {"approval_source": "human_review"}, {"auto_publish": "false"},
                       {"account_id": "night_scout"}, {"target_account_id": "beauty_account"},
                       {"excluded_from_activation": "true"}, {"repost_prohibited": "true"}):
            with self.subTest(fields=fields):
                client = Client([{**self.row, **fields}])
                self.assertEqual(self.refresh(client), [])
                self.assertEqual(client.writes, [])

    def test_current_gate_not_withdrawn(self):
        client = Client([self.row])
        with patch.object(gate, "account_allows_autonomous_ready", return_value=True), \
             patch.object(gate, "requires_hybrid_ai_gate", return_value=True), \
             patch.object(gate, "build_source_context", return_value={}), \
             patch.object(gate, "hybrid_ai_gate_current", return_value=(True, "PASS")):
            self.assertEqual(gate.refresh_stale_autonomous_ready(client, "liver_manager", 1, apply=True), [])
        self.assertEqual(client.writes, [])

    def test_only_autonomous_command_requests_refresh(self):
        self.assertIn("--refresh-stale-autonomous-ready",
                      gate_command("liver_manager", "lm_1600_direct_media", 1, True,
                                   approval_mode="media", autonomous_low_risk=True))
        self.assertNotIn("--refresh-stale-autonomous-ready",
                         gate_command("liver_manager", "lm_1600_direct_media", 1, True,
                                      approval_mode="media"))

    def test_delayed_recovery_does_not_select_other_slot(self):
        with patch("backfill_missed_content_slots._runtime_activation_gate", return_value=(True, [])), \
             patch("backfill_missed_content_slots.missing_slots", return_value=[{"slot_id": "lm_1300_reference"}]), \
             patch.object(scheduled, "dispatch_prepared_text") as dispatch:
            result = scheduled.recover_delayed_prepared_text(object(), "liver_manager", "lm_1000_original")
        self.assertEqual(result["reason"], "NO_RECOVERABLE_EXACT_SLOT")
        dispatch.assert_not_called()

    def test_delayed_recovery_requires_activation(self):
        with patch("backfill_missed_content_slots._runtime_activation_gate", return_value=(False, ["kill_switch"])), \
             patch.object(scheduled, "dispatch_prepared_text") as dispatch:
            result = scheduled.recover_delayed_prepared_text(object(), "liver_manager", "lm_1000_original")
        self.assertEqual(result["status"], "BLOCKED")
        dispatch.assert_not_called()

    def test_delayed_recovery_consumes_prepared_exact_slot_only(self):
        with patch("backfill_missed_content_slots._runtime_activation_gate", return_value=(True, [])), \
             patch("backfill_missed_content_slots.missing_slots", return_value=[{"slot_id": "lm_1000_original"}]), \
             patch.object(scheduled, "dispatch_prepared_text", return_value={"status": "PUBLISH_OUTCOME_UNVERIFIED"}) as dispatch:
            result = scheduled.recover_delayed_prepared_text(object(), "liver_manager", "lm_1000_original")
        self.assertEqual(result["status"], "PUBLISH_OUTCOME_UNVERIFIED")
        dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
