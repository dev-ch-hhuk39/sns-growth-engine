#!/usr/bin/env python3
"""Exact live identity repair never invokes a publisher."""
import copy
import unittest
from unittest.mock import patch

import process_threads_queue as worker
from recover_orphan_threads_post import repair_existing_save


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.queue = dict(queue_id="q", account_id="liver_manager", public_post_text="approved text",
                          status="POSTED_SAVE_UNVERIFIED", error="EXTERNAL_POST_ID_MISMATCH")
        self.row = dict(queue_id="q", result_id="r", account_id="liver_manager", status="POSTED",
                        posted_text="approved text", post_url="https://www.threads.com/@ran.liver_pro/post/example",
                        posted_at="2026-09-07T17:26:46+00:00", external_post_id=1.80665e16)
        self.remote = dict(id="18066462212730000", text=self.row["posted_text"], permalink=self.row["post_url"],
                           timestamp="2026-09-07T17:26:39+0000")
        self.tables = {"posted_results": [self.row], "queue": [self.queue], "metrics_collection_jobs": []}

    def run_repair(self, apply=False):
        def update(client, tab, key, value, fields):
            for row in self.tables[tab]:
                if row[key] == value:
                    row.update(fields)
                    return True
            return False

        def metrics(client, result_id):
            self.tables["metrics_collection_jobs"] = [dict(result_id=result_id, account_id="liver_manager",
                window_hours=h, status="SCHEDULED") for h in (24, 72, 168)]

        with patch.object(worker, "records", side_effect=lambda c, tab: copy.deepcopy(self.tables[tab])), \
             patch.object(worker, "update_row", side_effect=update) as writes, \
             patch.object(worker, "schedule_metrics_after_post", side_effect=metrics):
            result = repair_existing_save(object(), self.queue, [self.remote], apply=apply)
            if not apply:
                writes.assert_not_called()
            return result

    def test_dry_run_no_write(self):
        self.assertEqual(self.run_repair()["status"], "PLAN_ONLY")

    def test_repair_and_reentry_do_not_repost(self):
        result = self.run_repair(True)
        self.assertEqual(result["status"], "RECOVERED")
        self.assertFalse(result["would_post"])
        self.assertEqual(self.row["external_post_id"], self.remote["id"])
        self.assertEqual(self.queue["status"], "POSTED")
        self.assertEqual(result["metrics_reservation_count"], 3)
        self.assertEqual(self.run_repair(True)["status"], "BLOCKED")

    def test_wrong_account_blocked(self):
        self.row["account_id"] = "night_scout"
        self.assertEqual(self.run_repair()["status"], "BLOCKED")

    def test_ambiguous_result_blocked(self):
        self.tables["posted_results"].append(copy.deepcopy(self.row))
        self.assertEqual(self.run_repair()["status"], "BLOCKED")

    def test_text_mismatch_blocked(self):
        self.remote["text"] += "different"
        self.assertEqual(self.run_repair()["status"], "BLOCKED")

    def test_url_mismatch_blocked(self):
        self.remote["permalink"] += "different"
        self.assertEqual(self.run_repair()["status"], "BLOCKED")

    def test_time_mismatch_blocked(self):
        self.remote["timestamp"] = "2026-09-06T17:26:39+0000"
        self.assertEqual(self.run_repair()["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
