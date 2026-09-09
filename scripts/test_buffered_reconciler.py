#!/usr/bin/env python3
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import reconcile_due_production_slots as runner
from content_slot_runs import build_slot_run
from evergreen_inventory import admit_bank_batch, bank_record
from production_inventory import JST, has_media, policy, scheduled_slots


class BufferedReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 9, 18, tzinfo=JST)
        self.slot = {"account_id": "night_scout", "slot_id": "ns_1800_direct_media",
                     "business_date_jst": "2026-09-09", "post_type": "direct_reference_media"}
        self.row = {"queue_id": "q", "account_id": "night_scout", "platform": "threads",
                    "status": "READY", "public_post_text": "approved text", "validator_status": "PASS",
                    "internal_leak_status": "PASS", "account_fit_status": "PASS",
                    "slot_id": self.slot["slot_id"], "business_date_jst": "2026-09-09",
                    "schedule_date_jst": "2026-09-09"}

    def test_media_primary_text_reserve(self):
        media = {**self.row, "queue_id": "m", "media_asset_id": "asset", "generation_mode": "direct_reference_media"}
        self.assertEqual([r["queue_id"] for r in runner.candidates([self.row, media], self.slot, policy())], ["m", "q"])
        self.assertEqual(runner.candidates([self.row], self.slot, {**policy(), "media_shortage_text_fallback": False}), [])

    def test_wrong_media_route_blocked(self):
        self.assertEqual(runner.candidates([{**self.row, "media_asset_id": "a", "generation_mode": "approved_source_clip"}], self.slot, policy()), [])

    def test_beauty_media_uses_evening_slot_without_adding_posts(self):
        slots = scheduled_slots("beauty_account", self.now, self.now + timedelta(days=2))
        self.assertEqual(len(slots), 4)
        evening = [s for s in slots if s["slot_id"] == "beauty_2030"]
        self.assertEqual({s['post_type'] for s in evening}, {"direct_reference_media", "approved_source_clip"})
        slot = evening[0]
        row = {**self.row, "account_id": "beauty_account", "generation_mode": slot['post_type'],
               "media_asset_id": "beauty_asset", "business_date_jst": "", "schedule_date_jst": "",
               "slot_id": "beauty_direct_media_review"}
        self.assertEqual(runner.candidates([row], slot, policy()), [row])

    def test_duplicate_queue_identity_blocked(self):
        self.assertEqual(runner.candidates([self.row, self.row], self.slot, policy()), [])

    def test_old_media_can_carry_forward_but_not_future_or_posted(self):
        media = {**self.row, "media_asset_id": "a", "generation_mode": "direct_reference_media",
                 "business_date_jst": "2026-09-08", "schedule_date_jst": "2026-09-08"}
        self.assertEqual(runner.candidates([media], self.slot, policy()), [media])
        assigned = runner.assigned_queue(media, self.slot)
        self.assertEqual(assigned['queue_id'], media['queue_id'])
        self.assertEqual(assigned['public_post_text'], media['public_post_text'])
        self.assertEqual(assigned['business_date_jst'], '2026-09-09')
        self.assertEqual(runner.candidates([media], self.slot, policy(), [{"queue_id": "q"}]), [])
        self.assertEqual(runner.candidates([{**media, "business_date_jst": "2026-09-10"}], self.slot, policy()), [])

    def test_original_fallback_is_not_mislabeled_pdca_or_reference(self):
        self.assertEqual(runner.actual_route({**self.row, "generation_mode": "original_text"}, self.slot), "original_text")
        self.assertEqual(runner.actual_route({**self.row, "generation_mode": "metrics_pdca_v1"}, self.slot), "pdca_text")

    def test_cross_account_and_stale_slot_blocked(self):
        for key, value in [("account_id", "liver_manager"), ("business_date_jst", "2026-09-08"), ("status", "POSTED")]:
            self.assertEqual(runner.candidates([{**self.row, key: value}], self.slot, policy()), [])

    def test_empty_media_arrays_are_text(self):
        self.assertFalse(has_media({"media_asset_ids_json": "[]", "media_urls": []}))
        self.assertTrue(has_media({"media_urls_json": '["https://example.com/media.mp4"]'}))
        self.assertTrue(has_media({"media_asset_ids_json": "invalid"}))

    def test_limits_per_account(self):
        post = {"account_id": "night_scout", "real_post": "true", "posted_at": self.now.isoformat()}
        self.assertEqual(runner.delivery_limit("night_scout", [post], self.now), "COOLDOWN_ACTIVE")
        self.assertEqual(runner.delivery_limit("liver_manager", [post], self.now), "")
        posts = [{**post, "posted_at": (self.now-timedelta(hours=3)).isoformat()} for _ in range(5)]
        self.assertEqual(runner.delivery_limit("night_scout", posts, self.now), "DAILY_CAP_REACHED")

    def test_overnight_recovery_uses_original_slot_date(self):
        row = build_slot_run("night_scout", "ns_2500_pdca", now=self.now,
                             schedule_date_jst="2026-09-08", status="POSTED_PRIMARY")
        self.assertEqual(row["slot_run_id"], "slot_20260908_night_scout_ns_2500_pdca")
        self.assertEqual(row["scheduled_target_at"], "2026-09-09T01:00:00+09:00")
        self.assertEqual(row["actual_started_at"], self.now.isoformat())

    def test_bank_preserves_identity_and_rejects_media_or_bad_gate(self):
        record = bank_record(self.row, now=self.now, runtime_check=lambda row: True)
        self.assertEqual(record["queue_id"], self.row["queue_id"])
        self.assertEqual(record["text"], self.row["public_post_text"])
        with self.assertRaises(ValueError):
            bank_record(self.row, now=self.now, runtime_check=lambda row: False)
        with self.assertRaises(ValueError):
            bank_record({**self.row, "media_asset_id": "a"}, now=self.now, runtime_check=lambda row: True)

    def test_dry_run_never_claims_or_posts(self):
        tables = {"queue": [self.row], "posted_results": [], "content_slot_runs": []}
        with patch.object(runner, "records", side_effect=lambda _, name: tables[name]), \
             patch.object(runner, "process_one", return_value={"status": "DRY_RUN"}) as worker, \
             patch.object(runner, "claim_slot_run") as claim:
            result = runner.reconcile(SimpleNamespace(), accounts=["night_scout"], now=self.now)
        self.assertTrue(any(r["status"] == "DRY_RUN" for r in result["results"]))
        self.assertTrue(all(c.kwargs["dry_run"] and not c.kwargs["confirm_real_post"] for c in worker.call_args_list))
        claim.assert_not_called()

    def test_uncertain_publish_is_not_retried(self):
        tables = {"queue": [self.row], "posted_results": [], "content_slot_runs": []}
        with patch.object(runner, "policy", return_value={**policy(), "activation_enabled": True}), \
             patch.object(runner, "records", side_effect=lambda _, name: tables[name]), \
             patch.object(runner, "process_one", side_effect=[{"status": "DRY_RUN"}, {"status": "DRY_RUN"}, {"status": "PUBLISH_OUTCOME_UNVERIFIED"}]) as worker, \
             patch.object(runner.subprocess, "run") as gate, \
             patch.object(runner, "claim_slot_run", return_value={"status": "CLAIMED"}), \
             patch.object(runner, "upsert_slot_run") as save:
            gate.return_value.returncode = 0
            result = runner.reconcile(SimpleNamespace(), accounts=["night_scout"], now=self.now, apply=True)
        self.assertEqual(worker.call_count, 3)
        self.assertEqual(save.call_args.args[1]["status"], "RECOVERY_REQUIRED")
        self.assertEqual(result["status"], "FAILED")

    def test_saved_post_without_slot_columns_stops_replay(self):
        posts = runner.enrich_posts([{"queue_id": "q", "account_id": "night_scout"}], [self.row])
        self.assertEqual(posts[0]["slot_id"], self.slot["slot_id"])

    def test_second_reconcile_does_not_repeat_verified_delivery(self):
        tables = {"queue": [dict(self.row)], "posted_results": [], "content_slot_runs": [],
                  "metrics_collection_jobs": []}
        publish_calls = []

        def worker(client, row, *, dry_run, confirm_real_post):
            if dry_run:
                return {"status": "DRY_RUN"}
            self.assertTrue(confirm_real_post)
            publish_calls.append(row['queue_id'])
            tables['queue'][0]['status'] = 'POSTED'
            post = {"queue_id": row['queue_id'], "result_id": "r1", "account_id": row['account_id'],
                    "posted_text": row['public_post_text'], "real_post": "true",
                    "external_post_id": "123456", "post_url": "https://www.threads.com/@test/post/example",
                    "verification_status": "READ_AFTER_WRITE_PASS", "posted_at": self.now.isoformat()}
            tables['posted_results'].append(post)
            tables['metrics_collection_jobs'] = [{"result_id": "r1", "account_id": row['account_id'],
                                                  "window_hours": str(window)} for window in (24, 72, 168)]
            return {"status": "POSTED", "result_id": "r1"}

        with patch.object(runner, 'policy', return_value={**policy(), 'activation_enabled': True}), \
             patch.object(runner, 'records', side_effect=lambda _, name: [dict(r) for r in tables[name]]), \
             patch.object(runner, 'process_one', side_effect=worker), \
             patch.object(runner, 'due_slots', wraps=runner.due_slots), \
             patch.object(runner.subprocess, 'run') as gate, \
             patch.object(runner, 'claim_slot_run', return_value={'status': 'CLAIMED'}), \
             patch.object(runner, 'upsert_slot_run', side_effect=lambda _, row: tables['content_slot_runs'].append(row)):
            gate.return_value.returncode = 0
            first = runner.reconcile(SimpleNamespace(), accounts=['night_scout'], now=self.now,
                                     slot_id=self.slot['slot_id'], apply=True)
            second = runner.reconcile(SimpleNamespace(), accounts=['night_scout'], now=self.now,
                                      slot_id=self.slot['slot_id'], apply=True)
        self.assertEqual(first['status'], 'PASS')
        self.assertEqual(first['results'][0]['status'], 'POSTED')
        self.assertEqual(second['results'], [])
        self.assertEqual(publish_calls, ['q'])
        self.assertEqual(len(tables['metrics_collection_jobs']), 3)
        self.assertEqual(tables['content_slot_runs'][0]['actual_post_type'], 'text_fallback')

    def test_missing_metrics_is_not_verified_delivery(self):
        post = {'queue_id': 'q', 'account_id': 'night_scout', 'result_id': 'r',
                'posted_text': self.row['public_post_text'], 'real_post': 'true',
                'verification_status': 'READ_AFTER_WRITE_PASS', 'external_post_id': '123',
                'post_url': 'https://www.threads.com/@test/post/example'}
        tables = {'posted_results': [post], 'queue': [{**self.row, 'status': 'POSTED'}],
                  'metrics_collection_jobs': []}
        with patch.object(runner, 'records', side_effect=lambda _, name: tables[name]), \
             self.assertRaisesRegex(RuntimeError, 'DELIVERY_METRICS_UNVERIFIED'):
            runner.verify_delivery(None, self.row, {'result_id': 'r'})

    def test_bank_batch_has_constant_reads_and_is_idempotent(self):
        from copy import deepcopy
        from gspread.utils import a1_to_rowcol
        from sheets_client import TAB_DEFINITIONS

        class Worksheet:
            def __init__(self, values):
                self.values = deepcopy(values)
                self.reads = self.appends = 0

            def get_all_values(self):
                self.reads += 1
                return deepcopy(self.values)

            def batch_update(self, ranges, *, value_input_option):
                self.assert_raw(value_input_option)
                for item in ranges:
                    row, col = a1_to_rowcol(item['range'])
                    self.values[row-1][col-1] = item['values'][0][0]

            def append_rows(self, values, *, value_input_option):
                self.assert_raw(value_input_option)
                self.appends += 1
                self.values.extend(deepcopy(values))

            @staticmethod
            def assert_raw(value):
                assert value == "RAW"

        rows = [{**self.row, "queue_id": f"q{i}", "public_post_text": f"candidate {i}"} for i in range(20)]
        qheaders = list(self.row)
        sheets = {"queue": Worksheet([qheaders, *[[r[k] for k in qheaders] for r in rows]]),
                  "evergreen_bank": Worksheet([TAB_DEFINITIONS['evergreen_bank']])}
        from unittest.mock import Mock
        client = Mock()
        client._ws.side_effect = sheets.__getitem__
        with patch.object(runner, "records", return_value=[]):
            # The helper uses the canonical reader, patched only at the I/O edge.
            with patch("process_threads_queue.records", return_value=[]):
                result = admit_bank_batch(client, rows, now=self.now, runtime_check=lambda row: True, apply=True)
                repeated = admit_bank_batch(client, rows, now=self.now, runtime_check=lambda row: True, apply=True)
        self.assertEqual(result['created'], 20)
        self.assertEqual(repeated['created'], 0)
        self.assertEqual(sheets['queue'].reads, 4)
        self.assertEqual(sheets['evergreen_bank'].reads, 4)
        self.assertEqual(sheets['evergreen_bank'].appends, 1)


if __name__ == "__main__":
    unittest.main()
