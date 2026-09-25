#!/usr/bin/env python3
"""Actual local generation/quality gate tests. Provider access is prohibited."""
from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import HybridAiGate, hybrid_ai_gate_passed, merge_gate_audit  # noqa: E402
from offline_original_catalog import ACCOUNTS, catalog, evidence, select_original  # noqa: E402
from learning.feature_attribution import build_observations  # noqa: E402
from maintain_text_ready_inventory import _generation_commands, replenish  # noqa: E402
from generate_threads_ideas_from_references import (  # noqa: E402
    build_fallback_generation_rows, offline_history_context, run_offline_original_generation,
)
from public_post_quality import final_public_post_validator  # noqa: E402
from generation_quality_gates import evaluate_generation_quality, _topic_scores  # noqa: E402
from auto_approve_queue import near_duplicate, evaluate_item, load_rules, rules_for_account  # noqa: E402
import run_hybrid_ai_queue_gate as queue_gate  # noqa: E402


class NoProvider:
    def generate_json(self, **_kwargs):
        raise AssertionError("offline original must never call an AI provider")


class MemorySheet:
    def __init__(self, headers):
        self.headers, self.rows = list(headers), []

    def row_values(self, number):
        assert number == 1
        return self.headers

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def get_all_values(self):
        return [self.headers] + [[row.get(h, '') for h in self.headers] for row in self.rows]

    def append_rows(self, rows, **kwargs):
        assert kwargs['value_input_option'] == 'RAW'
        self.rows.extend(dict(zip(self.headers, row)) for row in rows)


class MemoryClient:
    def __init__(self):
        self.tables = {}

    def _ensure_tab(self, name, headers):
        return self.tables.setdefault(name, MemorySheet(headers))

    def _ws(self, name):
        return self.tables.setdefault(name, MemorySheet([]))


class OfflineReserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {}
        for account in ACCOUNTS:
            post = select_original(account, [])
            assert post, account
            text = post["public_post_text"]
            cls.rows[account] = {
                "queue_id": f"q_{account}_offline", "account_id": account,
                "target_account_id": account, "platform": "threads", "status": "WAITING_REVIEW",
                "content_type": "original_text", "generation_mode": "original_text",
                "public_post_text": text,
                "generation_policy_json": json.dumps({"offline_original": evidence(account, text)}),
            }

    def test_all_accounts_pass_without_provider_or_credentials(self):
        for account, row in self.rows.items():
            with self.subTest(account=account), patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
                result = HybridAiGate(NoProvider()).evaluate(row, {}, recent_posts=[])
                self.assertEqual(result.status, "PASS", result.blocked_reasons)
                self.assertEqual(result.actual_requests, 0)
                self.assertEqual(result.provider_status, "NOT_REQUESTED")
                self.assertEqual(result.provider_mode, "offline_original_strict")
                persisted = {**row, "generation_policy_json": merge_gate_audit(row["generation_policy_json"], result)}
                self.assertEqual(hybrid_ai_gate_passed(persisted, {}), (True, "pass"))
                self.assertEqual(row["status"], "WAITING_REVIEW")

    def test_scope_and_text_tampering_block(self):
        row = self.rows["night_scout"]
        for update in (
            {"public_post_text": row["public_post_text"] + "今すぐ応募"},
            {"source_id": "external_source"}, {"media_url": "https://example.com/video.mp4"},
            {"media_required": "true"}, {"platform": "x"},
            {"content_type": "pdca_text"}, {"generation_mode": "reference_text"},
            {"target_account_id": "beauty_account"}, {"repost_prohibited": "true"},
            {"validator_status": "BLOCKED"},
        ):
            with self.subTest(update=update):
                result = HybridAiGate(NoProvider()).evaluate({**row, **update}, {}, recent_posts=[])
                self.assertEqual(result.status, "BLOCKED")

    def test_missing_history_and_duplicate_block(self):
        row = self.rows["liver_manager"]
        gate = HybridAiGate(NoProvider())
        self.assertEqual(gate.evaluate(row, {}).status, "BLOCKED")
        self.assertEqual(gate.evaluate(row, {}, recent_posts=[row]).status, "BLOCKED")

    def test_semantic_rejection_cannot_be_laundered(self):
        row = copy.deepcopy(self.rows["night_scout"])
        policy = json.loads(row["generation_policy_json"])
        policy["hybrid_ai_gate"] = {"provider_mode": "gemini", "status": "BLOCKED"}
        row["generation_policy_json"] = json.dumps(policy)
        result = HybridAiGate(NoProvider()).evaluate(row, {}, recent_posts=[])
        self.assertIn("offline_semantic_rejection_not_overridable", result.blocked_reasons)

    def test_generation_builds_only_waiting_review(self):
        for account in ACCOUNTS:
            rows = build_fallback_generation_rows(account_id=account, top_n=1,
                post_type="original_text", offline_original=True)
            self.assertEqual(len(rows["queue"]), 1, account)
            row = rows["queue"][0]
            self.assertEqual(row["status"], "WAITING_REVIEW")
            self.assertEqual(row["auto_publish"], "false")
            self.assertEqual(row["feature_schema_version"], "post_features_v1", account)
            self.assertTrue(row["primary_topic"], account)
            self.assertTrue(row["structure_variant"], account)
            self.assertFalse(row["media_asset_id"])
            result = HybridAiGate(NoProvider()).evaluate(row, {}, recent_posts=[])
            self.assertEqual(result.status, "PASS", result.blocked_reasons)
            row['generation_policy_json'] = merge_gate_audit(row['generation_policy_json'], result)
            approval = evaluate_item(queue=row, draft=rows['drafts'][0], derivative=rows['social_derivatives'][0],
                scores_by_ref={}, existing_texts=[], rules=rules_for_account(load_rules(), account), source_context={})
            self.assertEqual(approval['status'], 'APPROVABLE', approval['reasons'])

    def test_beauty_measured_metrics_can_enter_account_scoped_pdca(self):
        queue = build_fallback_generation_rows(
            account_id="beauty_account", top_n=1, post_type="original_text", offline_original=True,
        )["queue"][0]
        posted = {
            **queue,
            "result_id": "beauty_measured_result",
            "status": "POSTED",
            "posted_at": "2026-09-24T10:00:00Z",
        }
        measured = {
            "result_id": "beauty_measured_result",
            "account_id": "beauty_account",
            "platform": "threads",
            "metrics_status": "MEASURED",
            "collection_window_hours": "24",
            "views": "240",
            "likes": "18",
            "comments": "3",
        }
        observations = build_observations([posted], [measured], account_id="beauty_account")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["account_id"], "beauty_account")
        self.assertEqual(observations[0]["metrics"]["views"], 240)
        self.assertEqual(observations[0]["features"]["primary_topic"], queue["primary_topic"])
        self.assertEqual(build_observations([posted], [measured], account_id="night_scout"), [])

    def test_canonical_persistence_and_readback_failure(self):
        client = MemoryClient()
        def read(client, table, **kwargs):
            if kwargs.get('preserve_strings'):
                from sheets_record_reader import records_from_values
                return records_from_values(client.tables[table].get_all_values())
            return client.tables[table].get_all_records() if table in client.tables else []
        with patch('sheets_record_reader.read_records_safely', side_effect=read):
            plan = run_offline_original_generation('night_scout', 1, apply=False, slot_id='ns_1600_original',
                schedule_date_jst='2026-09-16', client=client)
            self.assertEqual(plan['status'], 'PLAN_ONLY')
            self.assertEqual(client.tables, {})
            saved = run_offline_original_generation('night_scout', 1, apply=True, slot_id='ns_1600_original',
                schedule_date_jst='2026-09-16', client=client)
            self.assertTrue(saved['read_after_write'])
            self.assertEqual(set(client.tables), {'drafts', 'social_derivatives', 'queue'})
            self.assertEqual(client.tables['queue'].rows[0]['status'], 'WAITING_REVIEW')
        broken = MemoryClient()
        def corrupt_read(client, table, **kwargs):
            rows = read(client, table, **kwargs)
            return [{**row, 'public_post_text': 'corrupted'} for row in rows] if table == 'queue' else rows
        with patch('sheets_record_reader.read_records_safely', side_effect=corrupt_read):
            with self.assertRaisesRegex(RuntimeError, 'read_after_write_failed:queue'):
                run_offline_original_generation('night_scout', 1, apply=True, slot_id='ns_1600_original',
                    schedule_date_jst='2026-09-16', client=broken)

    def test_thirty_independent_safe_originals_per_account(self):
        for account in ACCOUNTS:
            accepted = []
            for text in catalog(account)[:30]:
                self.assertEqual(final_public_post_validator(text, account)["status"], "PASS", (account, text))
                quality = evaluate_generation_quality(account, text, accepted)
                self.assertEqual(quality["status"], "PASS", (account, quality))
                self.assertFalse(near_duplicate(text, accepted), account)
                accepted.append(text)
            self.assertEqual(len(accepted), 30)
            rows = build_fallback_generation_rows(account_id=account, top_n=3,
                post_type="original_text", offline_original=True)["queue"]
            self.assertEqual(len(rows), 3, account)

    def test_literal_readback_preserves_ids_scores_and_ignores_cache(self):
        from sheets_record_reader import read_records_safely, enable_readonly_record_cache
        client = MemoryClient()
        sheet = client._ensure_tab('queue', ['queue_id', 'similarity_score', 'public_post_text'])
        sheet.rows = [{'queue_id': '001234567890123456789', 'similarity_score': '0.0',
                       'public_post_text': '=original text'}]
        enable_readonly_record_cache(client)
        client._readonly_sheet_record_cache['queue'] = [{'queue_id': 'stale'}]
        self.assertEqual(read_records_safely(client, 'queue', preserve_strings=True), sheet.rows)
        sheet.rows[0]['public_post_text'] = 'changed'
        self.assertEqual(read_records_safely(client, 'queue', preserve_strings=True)[0]['public_post_text'], 'changed')

    def test_compound_topics_not_counted_twice_and_real_mix_blocks(self):
        self.assertNotIn("skincare_routine", _topic_scores("beauty_account", "ヘアケア"))
        self.assertNotIn("beauty_choice", _topic_scores("beauty_account", "美容家電"))
        mixed = "ヘアケアは毛先から丁寧に整えたい\n\nスキンケアでは乾燥と赤みに注意したい\n\n髪のヘアケアは毛先から見直したい"
        self.assertEqual(evaluate_generation_quality("beauty_account", mixed, [])["status"], "BLOCKED")
        text = catalog("beauty_account")[0]
        self.assertEqual(evaluate_generation_quality("beauty_account", text, [],
            visual_text="ヘアケアの毛先と頭皮のオイル")["status"], "BLOCKED")

    def test_exhaustion_does_not_recycle_catalog_text(self):
        self.assertEqual(select_original("beauty_account", list(catalog("beauty_account"))), {})

    def test_old_post_is_exactly_deduped_but_not_semantically_scored(self):
        old_text = catalog("liver_manager")[0]
        posted = [{"account_id": "liver_manager", "posted_text": old_text,
                   "posted_at": "2025-01-01T00:00:00Z"}]
        queue = [{"account_id": "liver_manager", "status": "POSTED",
                  "public_post_text": "previous posted queue copy"}]
        semantic, exact = offline_history_context(
            posted, queue, account_id="liver_manager", now=datetime(2026, 9, 25, tzinfo=timezone.utc),
            recent_days=30,
        )
        self.assertEqual(semantic, [])
        self.assertEqual(exact, [old_text, "previous posted queue copy"])
        selected = select_original("liver_manager", semantic, used_texts=exact)
        self.assertTrue(selected)
        self.assertNotEqual(selected["public_post_text"], old_text)

    def test_recent_and_active_queue_remain_semantic_protection(self):
        posted = [
            {"account_id": "night_scout", "posted_text": "recent post", "posted_at": "2026-09-10T00:00:00Z"},
            {"account_id": "liver_manager", "posted_text": "other account", "posted_at": "2026-09-24T00:00:00Z"},
        ]
        queue = [
            {"account_id": "night_scout", "status": "WAITING_REVIEW", "public_post_text": "active review"},
            {"account_id": "night_scout", "status": "POSTED", "public_post_text": "old queue"},
        ]
        semantic, exact = offline_history_context(
            posted, queue, account_id="night_scout", now=datetime(2026, 9, 25, tzinfo=timezone.utc),
            recent_days=30,
        )
        self.assertEqual(semantic, ["recent post", "active review"])
        self.assertEqual(exact, ["recent post", "active review", "old queue"])

    def test_stale_scheduled_queue_stays_exactly_deduped_but_not_semantically_active(self):
        queue = [
            {"account_id": "liver_manager", "status": "WAITING_REVIEW",
             "business_date_jst": "2026-09-25", "public_post_text": "expired review"},
            {"account_id": "liver_manager", "status": "READY",
             "schedule_date_jst": "2026-09-20", "public_post_text": "expired ready"},
            {"account_id": "liver_manager", "status": "READY",
             "business_date_jst": "2026-09-27", "public_post_text": "future ready"},
            {"account_id": "liver_manager", "status": "WAITING_REVIEW",
             "created_at": "2026-09-20T00:00:00Z", "public_post_text": "recent unscheduled"},
            {"account_id": "liver_manager", "status": "WAITING_REVIEW",
             "created_at": "2026-08-01T00:00:00Z", "public_post_text": "old unscheduled"},
        ]
        semantic, exact = offline_history_context(
            [], queue, account_id="liver_manager", now=datetime(2026, 9, 26, tzinfo=timezone.utc),
            recent_days=30,
        )
        self.assertEqual(semantic, ["future ready", "recent unscheduled"])
        self.assertEqual(exact, [row["public_post_text"] for row in queue])

    def test_old_lifetime_catalog_usage_does_not_exhaust_bounded_topup(self):
        old_texts = list(catalog("liver_manager")[:80])
        rows = build_fallback_generation_rows(
            account_id="liver_manager", top_n=3, post_type="original_text",
            history=[], used_texts=old_texts, offline_original=True,
        )
        self.assertEqual(len(rows["queue"]), 3)
        generated = [row["public_post_text"] for row in rows["queue"]]
        self.assertEqual(len(set(generated)), 3)
        self.assertFalse(set(generated) & set(old_texts))

    def test_queue_cli_without_provider_key_and_cached_evidence(self):
        row = self.rows['night_scout']
        for selected, skipped in ([[(row, {})], []], [[], [{"queue_id": row['queue_id'], "gate_status": "pass"}]]):
            stdout = io.StringIO()
            with patch.object(sys, 'argv', ['gate', '--account-id', 'night_scout', '--max-candidates', '1',
                    '--dry-run', '--use-sheets']), \
                 patch.dict('os.environ', {'GEMINI_API_KEY': ''}), \
                 patch.object(queue_gate, 'get_config', return_value={'sheet_id': 'test', 'sa_dict': {}}), \
                 patch.object(queue_gate, 'SheetsClient'), \
                 patch.object(queue_gate, 'candidate_rows', return_value=(selected, skipped)), \
                 patch.object(queue_gate, 'records', side_effect=lambda client, name: [row] if name == 'queue' else []), \
                 patch.object(queue_gate, 'GeminiHybridClient', side_effect=AssertionError('no provider')), \
                 contextlib.redirect_stdout(stdout):
                self.assertEqual(queue_gate.main(), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result['actual_request_count'], 0)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['skipped_current_count'], len(skipped))

    def test_budget_exhaustion_reaches_offline_generation(self):
        slot = {"slot_id": "night_1600", "post_type": "original_text", "business_date_jst": "2026-09-15"}
        calls = []
        def run(command):
            calls.append(command)
            if "scripts/generate_threads_ideas_from_references.py" in command:
                return 0, {"queue_ids": ["q_offline" if "--offline-original" in command else "q_remote"]}
            if "q_remote" in command:
                return 2, {"runtime_errors": [{"reason": "HYBRID_AI_DAILY_LIMIT_EXCEEDED"}]}
            return 0, {"status": "READY"}
        with patch("maintain_text_ready_inventory._run", side_effect=run):
            result = replenish("night_scout", slot, apply=True)
        self.assertEqual(result["status"], "READY_REPLENISHED")
        self.assertEqual(result["queue_ids"], ["q_offline"])
        self.assertTrue(any("--offline-original" in command for command in calls))
        self.assertFalse(result["would_post"])
        for account in ACCOUNTS:
            commands = _generation_commands(account, slot, offline_only=True)
            self.assertEqual(len(commands), 1)
            self.assertIn("--offline-original", commands[0][1])


if __name__ == "__main__":
    unittest.main()
