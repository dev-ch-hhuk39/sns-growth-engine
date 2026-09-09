#!/usr/bin/env python3
"""Offline contracts for bounded generation, never production evidence."""
import os
import unittest
from unittest.mock import patch

from gemini_hybrid_client import GeminiHttpError
from generate_threads_ideas_from_references import buffered_original_candidate


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


if __name__ == "__main__":
    unittest.main()
