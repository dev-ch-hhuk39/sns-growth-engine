#!/usr/bin/env python3
"""Generation rejects duplicate Beauty drafts before spending Hybrid approval."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import prepare_beauty_review_candidates as prepare


class BeautyNoveltyTests(unittest.TestCase):
    def setUp(self):
        self.texts = list(prepare.SAFE_TOPIC_FALLBACKS.values())

    def generate(self, history, responses):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(prepare.os.environ, {"GEMINI_API_KEY": "test-placeholder"}))
            stack.enter_context(patch.object(prepare, "select_beauty_route", return_value="new_text_generation"))
            stack.enter_context(patch.object(prepare, "load_route_context", return_value={
                "status": "PASS", "source_ids": [], "novelty_history": history,
            }))
            provider = stack.enter_context(patch.object(prepare, "call_gemini_json", side_effect=responses))
            result = prepare.generate_candidate(slot_index=0, sequence_number=1, schedule_date_jst="2026-09-13")
        return result, provider

    def test_history_is_account_scoped_and_public_only(self):
        posted = [
            {"account_id": "beauty_account", "posted_text": "own", "internal_analysis": "private"},
            {"account_id": "night_scout", "posted_text": "night"},
            {"account_id": "liver_manager", "posted_text": "liver"},
            {"account_id": "beauty_account", "target_account_id": "liver_manager", "posted_text": "wrong-target"},
            {"account_id": "beauty_account", "real_post": False, "posted_text": "mock"},
        ]
        queue = [{"account_id": "beauty_account", "status": state, "public_post_text": state}
                 for state in ("READY", "WAITING_REVIEW", "PROCESSING", "SUPERSEDED", "REJECTED")]
        queue += [{"account_id": "liver_manager", "status": "READY", "public_post_text": "other"}]
        self.assertEqual(prepare.beauty_novelty_history(posted, queue), ["own", "READY", "WAITING_REVIEW", "PROCESSING"])

    def test_duplicate_is_regenerated_and_history_not_logged_in_candidate(self):
        result, provider = self.generate([self.texts[0]], [
            {"public_post_text": self.texts[0]}, {"public_post_text": self.texts[1]},
        ])
        self.assertEqual(result["status"], "WAITING_REVIEW")
        self.assertEqual(result["public_post_text"], self.texts[1])
        self.assertEqual(provider.call_count, 2)
        self.assertIn("duplicate_or_near_duplicate", provider.call_args_list[1].args[0])
        self.assertNotIn("novelty_history", result["route_context"])

    def test_repeated_duplicates_exhaust_without_ready_or_static_success(self):
        result, provider = self.generate([self.texts[0]], [{"public_post_text": self.texts[0]}] * 15)
        self.assertEqual(result["status"], "QUALITY_EXHAUSTED")
        self.assertIn("duplicate_or_near_duplicate", result["blocked_reasons"])
        self.assertLessEqual(provider.call_count, 15)
        self.assertNotIn("queue_id", result)

    def test_provider_fallback_cannot_reuse_posted_template(self):
        result, _ = self.generate(self.texts, [{"_error": "HTTP 429"}] * 5)
        self.assertEqual(result["status"], "QUALITY_EXHAUSTED")
        self.assertIn("duplicate_or_near_duplicate", result["blocked_reasons"])

    def test_all_text_routes_load_history_once_without_cross_account(self):
        for route in ("new_text_generation", "reference_text_generation", "pdca_text_generation"):
            reads = []
            def read(client, tab):
                reads.append(tab)
                return [{"account_id": "beauty_account", "posted_text": "own"}] if tab == "posted_results" else []
            with patch("config_loader.get_config", return_value={"sheet_id": "test", "sa_dict": {}}), \
                 patch("sheets_client.SheetsClient"), \
                 patch("sheets_record_reader.read_records_safely", side_effect=read):
                result = prepare.load_route_context(route, prepare.TOPICS[0])
            self.assertEqual(result["novelty_history"], ["own"])
            self.assertEqual(reads.count("posted_results"), 1)
            self.assertEqual(reads.count("queue"), 1)

    def test_history_read_failure_blocks_generation_context(self):
        with patch("config_loader.get_config", return_value={"sheet_id": "test", "sa_dict": {}}), \
             patch("sheets_client.SheetsClient"), \
             patch("sheets_record_reader.read_records_safely", side_effect=RuntimeError("private response")):
            result = prepare.load_route_context("new_text_generation")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("private response", str(result))


if __name__ == "__main__":
    unittest.main()
