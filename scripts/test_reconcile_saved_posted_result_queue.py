#!/usr/bin/env python3
"""Offline proof that reconciling an existing POSTED result never republishes."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts import recover_orphan_threads_post as recovery


class ReconcileExistingResultTests(unittest.TestCase):
    def setUp(self):
        self.queue = {
            "queue_id": "q_liver_manager_fallback_20260915140951_1_threads",
            "account_id": "liver_manager",
            "draft_id": "idea_01",
            "public_post_text": "掲載済みの文章。重複投稿しない。",
            "status": "POSTED_SAVE_FAILED",
            "processed_at": "2026-09-27T12:03:25+00:00",
            "error": "posted_results save failed",
            "result_id": "",
        }
        self.saved = {
            "result_id": "existing_threads_result",
            "queue_id": self.queue["queue_id"],
            "account_id": self.queue["account_id"],
            "draft_id": self.queue["draft_id"],
            "platform": "threads",
            "posted_text": self.queue["public_post_text"],
            "status": "POSTED",
            "verification_status": "READ_AFTER_WRITE_PASS",
            "external_post_id": "123456789012345678",
            "post_url": "https://www.threads.net/@creator/post/AbC123",
            "posted_at": "2026-09-27T12:01:43+00:00",
            "real_post": "true",
        }
        self.provider = {
            "id": self.saved["external_post_id"],
            "permalink": self.saved["post_url"],
            "text": self.saved["posted_text"],
            "timestamp": self.saved["posted_at"],
        }
        self.tabs = {"queue": [self.queue], "posted_results": [self.saved]}
        self.client = object()
        self.read = patch.object(recovery, "_get_records", side_effect=self._read)
        self.update = patch("process_threads_queue.update_row", side_effect=self._update)
        self.read.start()
        self.update_mock = self.update.start()
        self.addCleanup(self.read.stop)
        self.addCleanup(self.update.stop)

    def _read(self, _client, logical):
        return copy.deepcopy(self.tabs[logical])

    def _update(self, _client, logical, key, value, data):
        if logical != "queue" or key != "queue_id":
            raise AssertionError("attempted writes outside exact queue")
        matches = [row for row in self.tabs["queue"] if row.get(key) == value]
        if len(matches) != 1:
            return False
        matches[0].update(data)
        return True

    def reconcile(self, apply=False):
        return recovery.reconcile_saved_result_queue(
            self.client, copy.deepcopy(self.queue), copy.deepcopy(self.provider),
            apply=apply,
        )

    def test_default_plan_is_read_only_and_redacted(self):
        plan = self.reconcile()
        self.assertEqual(plan["status"], "PLAN_ONLY")
        self.assertFalse(plan["would_post"])
        self.assertFalse(plan["would_append_posted_results"])
        self.assertEqual(plan["metrics_reservation"], "NOT_VERIFIED_BY_THIS_ACTION")
        self.update_mock.assert_not_called()
        self.assertEqual(self.queue["status"], "POSTED_SAVE_FAILED")
        self.assertNotIn(self.saved["posted_text"], str(plan))
        self.assertNotIn(self.saved["post_url"], str(plan))
        self.assertNotIn(self.saved["external_post_id"], str(plan))

    def test_exact_provider_proof_allows_queue_only_update_with_readback(self):
        outcome = self.reconcile(apply=True)
        self.assertEqual(outcome["status"], "RECONCILED_QUEUE_ONLY")
        self.assertTrue(outcome["queue_readback_verified"])
        self.assertFalse(outcome["would_post"])
        self.assertFalse(outcome["would_append_posted_results"])
        self.assertEqual(self.queue["status"], "POSTED")
        self.assertEqual(self.queue["result_id"], self.saved["result_id"])
        self.assertEqual(self.queue["error"], "")
        self.assertEqual(len(self.tabs["posted_results"]), 1)
        self.update_mock.assert_called_once()

    def test_provider_identity_conflict_blocks_without_update(self):
        self.provider["id"] = "999999999999"
        self.assertEqual(self.reconcile(apply=True)["reason"], "LIVE_PROVIDER_EXACT_MATCH_REQUIRED")
        self.update_mock.assert_not_called()

    def test_provider_url_conflict_blocks_without_update(self):
        self.provider["permalink"] = "https://www.threads.net/@other/post/Different"
        self.assertEqual(self.reconcile(apply=True)["reason"], "LIVE_PROVIDER_EXACT_MATCH_REQUIRED")
        self.update_mock.assert_not_called()

    def test_provider_timestamp_conflict_blocks_without_update(self):
        self.provider["timestamp"] = "2026-09-28T12:01:43+00:00"
        self.assertEqual(self.reconcile(apply=True)["reason"], "LIVE_PROVIDER_EXACT_MATCH_REQUIRED")
        self.update_mock.assert_not_called()

    def test_existing_post_not_verified_blocks(self):
        self.saved["verification_status"] = "UNVERIFIED"
        self.assertEqual(self.reconcile(apply=True)["reason"], "SAVED_RESULT_PROOF_INCOMPLETE")
        self.update_mock.assert_not_called()

    def test_different_content_blocks(self):
        self.queue["public_post_text"] = "別の記事"
        self.assertEqual(self.reconcile(apply=True)["reason"], "SAVED_RESULT_PROOF_INCOMPLETE")
        self.update_mock.assert_not_called()

    def test_duplicate_result_or_external_id_blocks(self):
        self.tabs["posted_results"].append(copy.deepcopy(self.saved))
        self.assertEqual(self.reconcile(apply=True)["reason"], "EXACT_EXISTING_RESULT_REQUIRED")
        self.update_mock.assert_not_called()

    def test_wrong_account_or_queue_state_blocks(self):
        self.queue["account_id"] = "beauty_account"
        self.assertEqual(self.reconcile(apply=True)["reason"], "EXACT_FAILED_QUEUE_REQUIRED")
        self.update_mock.assert_not_called()

    def test_current_queue_changed_since_read_blocks(self):
        self.tabs["queue"][0] = {**self.queue, "status": "POSTED"}
        self.assertEqual(self.reconcile(apply=True)["reason"], "PREWRITE_SOURCE_CHANGED_NO_RETRY")
        self.update_mock.assert_not_called()

    def test_external_failure_never_retries_writes(self):
        self.update_mock.side_effect = lambda *_args, **_kwargs: False
        out = self.reconcile(apply=True)
        self.assertEqual(out["status"], "PARTIAL_SAVE_UNVERIFIED_NO_RETRY")
        self.update_mock.assert_called_once()

    def test_exact_provider_read_uses_get_not_post(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"id": "123456789012345678"}

        with patch.object(recovery, "resolve_credentials", return_value={
            "access_token": "PRIVATE_TOKEN", "user_id": "12345678"
        }):
            with patch("requests.get", return_value=Response()) as read:
                row = recovery._fetch_exact_threads_post("liver_manager", "123456789012345678")
        self.assertEqual(row["id"], "123456789012345678")
        read.assert_called_once()
        self.assertEqual(read.call_args.args[0],
                         "https://graph.threads.net/v1.0/123456789012345678")


if __name__ == "__main__":
    unittest.main()
