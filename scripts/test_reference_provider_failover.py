#!/usr/bin/env python3
"""Availability fallback preserves source, account and semantic review."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generation import reference_source_rewriter as rewriter  # noqa: E402


class FailoverTests(unittest.TestCase):
    def call(self):
        return rewriter.rewrite_reference_post(account_id="night_scout", source={"text": "source"},
                                               source_score={"value": 90}, model="primary")

    def test_retryable_provider_only_once(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status), patch.dict(os.environ, {"REFERENCE_GEMINI_FALLBACK_MODEL": "secondary"}), \
                 patch.object(rewriter, "_rewrite_reference_post_once", side_effect=[
                     rewriter.ReferenceRewriteError(f"Gemini API returned HTTP {status}"),
                     {"public_post_text": "new text", "generation_model": "secondary"},
                 ]) as once:
                result = self.call()
                self.assertEqual(once.call_count, 2)
                first, second = [c.kwargs for c in once.call_args_list]
                self.assertEqual({k: v for k, v in first.items() if k != "model"},
                                 {k: v for k, v in second.items() if k != "model"})
                self.assertEqual(result["generation_model"], "secondary")

    def test_rejection_or_auth_never_fails_over(self):
        for reason in ("semantic fidelity blocked: mismatch", "generated draft is too short",
                       "Gemini API returned HTTP 401", "Gemini API returned HTTP 403"):
            with self.subTest(reason=reason), patch.object(rewriter, "_rewrite_reference_post_once",
                  side_effect=rewriter.ReferenceRewriteError(reason)) as once:
                with self.assertRaises(rewriter.ReferenceRewriteError):
                    self.call()
                self.assertEqual(once.call_count, 1)

    def test_secondary_semantic_rejection_propagates(self):
        with patch.dict(os.environ, {"REFERENCE_GEMINI_FALLBACK_MODEL": "secondary"}), \
             patch.object(rewriter, "_rewrite_reference_post_once", side_effect=[
                 rewriter.ReferenceRewriteError("Gemini API returned HTTP 429"),
                 rewriter.ReferenceRewriteError("semantic fidelity blocked: mismatch"),
             ]) as once:
            with self.assertRaisesRegex(rewriter.ReferenceRewriteError, "semantic fidelity"):
                self.call()
            self.assertEqual(once.call_count, 2)

    def test_no_repeat_same_model(self):
        with patch.dict(os.environ, {"REFERENCE_GEMINI_FALLBACK_MODEL": "primary"}), \
             patch.object(rewriter, "_rewrite_reference_post_once",
                          side_effect=rewriter.ReferenceRewriteError("Gemini API returned HTTP 429")) as once:
            with self.assertRaises(rewriter.ReferenceRewriteError):
                self.call()
            self.assertEqual(once.call_count, 1)


if __name__ == "__main__":
    unittest.main()
