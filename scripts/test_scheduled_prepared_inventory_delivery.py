#!/usr/bin/env python3
"""Prebuilt inventory is consumed without generation and never retried ambiguously."""
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from types import SimpleNamespace

import run_scheduled_text_slot_pipeline as scheduled
import run_direct_reference_media_pipeline as direct
import maintain_text_ready_inventory as maintenance


class PreparedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(queue_id="prebuilt", account_id="night_scout", platform="threads",
                        slot_id="ns_1600_original", schedule_date_jst="2026-09-07", status="READY",
                        public_post_text="safe public text", validator_status="PASS",
                        internal_leak_status="PASS", account_fit_status="PASS")

    def selected(self, row):
        return scheduled.prepared_text_candidates([row], "night_scout", "ns_1600_original", "2026-09-07")

    def test_both_date_columns(self):
        self.assertTrue(self.selected(self.row))
        self.assertTrue(self.selected({**self.row, "schedule_date_jst": "", "business_date_jst": "2026-09-07"}))

    def test_account_date_slot_status_and_media_boundaries(self):
        for key, value in [("account_id", "liver_manager"), ("target_account_id", "beauty_account"),
                           ("slot_id", "ns_1400_reference"), ("schedule_date_jst", "2026-09-08"),
                           ("status", "POSTED"), ("status", "WAITING_REVIEW"),
                           ("media_required", "true"), ("media_asset_id", "asset"),
                           ("validator_status", "BLOCKED")]:
            with self.subTest(key=key, value=value):
                self.assertFalse(self.selected({**self.row, key: value}))

    def test_text_provenance_is_not_media(self):
        self.assertTrue(self.selected({**self.row, "source_post_id": "reference"}))

    def test_prepared_publish_stops_on_ambiguous_outcome(self):
        with patch("content_slot_runs.business_date", return_value="2026-09-07"), \
             patch("content_slot_runs.existing_slot_status", return_value=""), \
             patch("content_slot_runs.claim_slot_run", return_value={"status": "CLAIMED"}) as claim, \
             patch("process_threads_queue.records", return_value=[self.row, {**self.row, "queue_id": "other"}]), \
             patch("process_threads_queue.process_one", side_effect=[{"status": "DRY_RUN"}, {"status": "PUBLISH_OUTCOME_UNVERIFIED"}]) as worker, \
             patch.object(scheduled, "run_stage", return_value=(0, {"status": "ALLOW"})):
            result = scheduled.dispatch_prepared_text(SimpleNamespace(), "night_scout", "ns_1600_original", apply=True)
        self.assertEqual(result["status"], "PUBLISH_OUTCOME_UNVERIFIED")
        self.assertEqual(worker.call_count, 2)
        claim.assert_called_once()

    def test_activation_blocks_prepared_publish(self):
        with patch("content_slot_runs.business_date", return_value="2026-09-07"), \
             patch("content_slot_runs.existing_slot_status", return_value=""), \
             patch("content_slot_runs.claim_slot_run") as claim, \
             patch("process_threads_queue.records", return_value=[self.row]), \
             patch("process_threads_queue.process_one", return_value={"status": "DRY_RUN"}) as worker, \
             patch.object(scheduled, "run_stage", return_value=(1, {"status": "BLOCKED"})):
            result = scheduled.dispatch_prepared_text(SimpleNamespace(), "night_scout", "ns_1600_original", apply=True)
        self.assertEqual(result["reason"], "RUNTIME_ACTIVATION_GATE_BLOCKED")
        claim.assert_not_called()
        worker.assert_called_once()

    def test_preview_snapshot_never_reused_for_real_publish(self):
        client = SimpleNamespace()
        seen = []
        def worker(target, row, *, dry_run, **kwargs):
            seen.append(target)
            if dry_run:
                cache = target._readonly_sheet_record_cache
                if not cache:
                    cache['posted_results'] = []
                    return {"status": "DRY_RUN_BLOCKED"}
                return {"status": "DRY_RUN"}
            self.assertIs(target, client)
            self.assertFalse(hasattr(target, '_readonly_sheet_record_cache'))
            return {"status": "PUBLISH_OUTCOME_UNVERIFIED"}
        with patch("content_slot_runs.business_date", return_value="2026-09-07"), \
             patch("content_slot_runs.existing_slot_status", return_value=""), \
             patch("content_slot_runs.claim_slot_run", return_value={"status": "CLAIMED"}), \
             patch("content_slot_runs.release_unpublished_claim") as release, \
             patch("process_threads_queue.records", return_value=[self.row, {**self.row, "queue_id": "next"}]), \
             patch("process_threads_queue.process_one", side_effect=worker), \
             patch.object(scheduled, "run_stage", return_value=(0, {})):
            scheduled.dispatch_prepared_text(client, "night_scout", "ns_1600_original", apply=True)
        self.assertEqual(len(seen), 3)
        self.assertIs(seen[0], seen[1])
        self.assertIsNot(seen[1], seen[2])
        release.assert_not_called()

    def test_only_confirmed_pre_publish_failure_releases_claim(self):
        for result, expected in [({"status": "PRE_PUBLISH_SHEETS_FAILED", "publish_attempted": False}, 1),
                                 ({"status": "PRE_PUBLISH_SHEETS_FAILED"}, 0),
                                 ({"status": "POSTED_SAVE_FAILED"}, 0)]:
            with self.subTest(result=result), \
                 patch("content_slot_runs.business_date", return_value="2026-09-07"), \
                 patch("content_slot_runs.existing_slot_status", return_value=""), \
                 patch("content_slot_runs.claim_slot_run", return_value={"status": "CLAIMED"}), \
                 patch("content_slot_runs.release_unpublished_claim", return_value={"status": "RELEASED"}) as release, \
                 patch("process_threads_queue.records", return_value=[self.row]), \
                 patch("process_threads_queue.process_one", side_effect=[{"status": "DRY_RUN"}, result]), \
                 patch.object(scheduled, "run_stage", return_value=(0, {})):
                scheduled.dispatch_prepared_text(SimpleNamespace(), "night_scout", "ns_1600_original", apply=True)
                self.assertEqual(release.call_count, expected)

    def test_unused_media_carries_forward_not_future_or_expired(self):
        self.assertTrue(direct.prepared_media_date_eligible({"business_date_jst": "2026-09-06"}, "2026-09-07"))
        self.assertTrue(direct.prepared_media_date_eligible({"schedule_date_jst": "2026-09-07"}, "2026-09-07"))
        for row in [{}, {"business_date_jst": "invalid"}, {"business_date_jst": "2026-09-08"},
                    {"business_date_jst": "2026-09-01", "expires_at": "invalid"},
                    {"business_date_jst": "2026-09-01", "expires_at": (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}]:
            self.assertFalse(direct.prepared_media_date_eligible(row, "2026-09-07"))

    def test_provider_error_is_categorized_without_response(self):
        completed = subprocess.CompletedProcess([], 1, '{"status":"NO_DATA"}', 'HTTP 429 private response')
        with patch.object(maintenance.subprocess, "run", return_value=completed):
            code, payload = maintenance._run(["unused"])
        self.assertEqual(code, 1)
        self.assertEqual(payload["failure_category"], "PROVIDER_RATE_LIMITED")
        self.assertNotIn("private", str(payload))


if __name__ == "__main__":
    unittest.main()
