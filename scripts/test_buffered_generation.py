#!/usr/bin/env python3
"""Offline contracts for bounded generation, never production evidence."""
import os
import unittest
from unittest.mock import patch

from gemini_hybrid_client import GeminiHttpError
from generate_threads_ideas_from_references import buffered_original_candidate
from maintain_text_ready_inventory import approval_budget_exhausted, replenish
from run_hybrid_ai_queue_gate import safe_runtime_reason


class BufferedGenerationTests(unittest.TestCase):
    def generate(self, account="night_scout"):
        return buffered_original_candidate(account, recent=["previous approved post"],
            excluded_topics=[], batch_id="test_batch", attempt=0)

    def test_transport_fallback_retains_topic_and_unapproved_status(self):
        with patch.dict(os.environ, {"DRY_RUN": "false", "MOCK_LLM": "false"}), \
             patch("gemini_hybrid_client.GeminiHybridClient") as factory:
            client = factory.return_value
            client.generate_json.side_effect = [GeminiHttpError(429, "rate limited"),
                {"data": {"public_post_text": "candidate", "primary_topic": "provider free text",
                          "structure_variant": "contrast"}}]
            result = self.generate()
            calls = client.generate_json.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0].kwargs["model"], calls[1].kwargs["model"])
        self.assertEqual(calls[1].kwargs["account_id"], "night_scout")
        topic = result["grounding_summary"]["quality_topic"]
        self.assertNotEqual(topic, "provider free text")
        self.assertIn(topic, calls[0].kwargs["prompt"])
        self.assertNotIn("status", result)
        self.assertNotIn("validator_status", result)

    def test_auth_and_budget_errors_do_not_hop_models(self):
        for error in (GeminiHttpError(401, "unauthorized"), RuntimeError("budget_exhausted")):
            with self.subTest(error=type(error).__name__), \
                 patch.dict(os.environ, {"DRY_RUN": "false", "MOCK_LLM": "false"}), \
                 patch("gemini_hybrid_client.GeminiHybridClient") as factory:
                factory.return_value.generate_json.side_effect = error
                with self.assertRaises(type(error)):
                    self.generate()
                self.assertEqual(factory.return_value.generate_json.call_count, 1)

    def test_dry_run_does_not_call_provider(self):
        with patch.dict(os.environ, {"DRY_RUN": "true"}), \
             patch("gemini_hybrid_client.GeminiHybridClient") as factory:
            self.assertEqual(self.generate(), {})
            factory.assert_not_called()

    def test_local_budget_exhaustion_returns_no_approval_and_does_not_hop(self):
        with patch.dict(os.environ, {"DRY_RUN": "false", "MOCK_LLM": "false"}), \
             patch("gemini_hybrid_client.GeminiHybridClient") as factory:
            factory.return_value.generate_json.side_effect = RuntimeError(
                'hybrid_ai_budget_blocked:{"reasons":["daily_limit_exceeded"]}')
            self.assertEqual(self.generate(), {})
            self.assertEqual(factory.return_value.generate_json.call_count, 1)

    def test_beauty_keeps_its_dedicated_voice_generation(self):
        with patch("gemini_hybrid_client.GeminiHybridClient") as factory:
            self.assertEqual(self.generate("beauty_account"), {})
            factory.assert_not_called()

    def test_budget_reason_is_explicit_but_unknown_errors_are_redacted(self):
        for limit in ('execution', 'daily', 'monthly'):
            reason = safe_runtime_reason(RuntimeError(f'hybrid_ai_{limit}_limit_exceeded'))
            self.assertEqual(reason, f'HYBRID_AI_{limit.upper()}_LIMIT_EXCEEDED')
            self.assertTrue(approval_budget_exhausted({'runtime_errors': [{'reason': reason}]}))
        self.assertEqual(safe_runtime_reason(RuntimeError('sensitive response detail')),
                         'HYBRID_AI_GATE_RUNTIME_ERROR')
        self.assertFalse(approval_budget_exhausted({'status': 'BLOCKED', 'reason': 'quality_rejection'}))

    def test_budget_exhaustion_stops_extra_generation_without_approval(self):
        slot = {'slot_id': 'test_buffer', 'business_date_jst': '2026-09-10', 'post_type': 'original_text'}
        review = {'stages': [{'payload': {'runtime_errors': [{'reason': 'HYBRID_AI_DAILY_LIMIT_EXCEEDED'}]}}]}
        with patch('maintain_text_ready_inventory._generation_commands', return_value=[('primary', ['generator']), ('fallback', ['generator'])]), \
             patch('maintain_text_ready_inventory._run', side_effect=[(0, {'queue_ids': ['q1', 'q2']}), (1, review)]) as run, \
             patch('maintain_text_ready_inventory.Path') as path:
            path.return_value.exists.return_value = False
            result = replenish('night_scout', slot, apply=True, required=2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result['failure_category'], 'AI_APPROVAL_BUDGET_EXHAUSTED')
        self.assertEqual(result['queue_ids'], [])
        self.assertEqual(result['status'], 'QUALITY_EXHAUSTED')
        self.assertFalse(result['would_post'])


if __name__ == "__main__":
    unittest.main()
