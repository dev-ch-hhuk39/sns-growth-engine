#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / 'src')]
from run_content_quality_v2_vision_smoke import SmokeGeminiClient
from gemini_hybrid_client import GeminiHttpError
from test_gemini_quota_diagnostics import quota

class SmokeCaptionTests(unittest.TestCase):
    def test_daily_caption_single_attempt_safe_evidence(self):
        transport = Mock(side_effect=GeminiHttpError(429, quota('GenerateRequestsPerDayPerProject-FreeTier')))
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key='SECRET_KEY', transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaises(GeminiHttpError):
                client.generate_json(model='gemini-3.5-flash', prompt='fixture', schema={}, operation='direct_reference_caption_generation', account_id='night_scout')
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(client.caption_evidence['rate_limit_class'], 'DAILY_QUOTA_EXHAUSTED')
            self.assertEqual(len(client.caption_evidence['attempt_history']), 1)
            self.assertNotIn('SECRET_KEY', json.dumps(client.caption_evidence))

    def test_caption_transient_success_history(self):
        transport = Mock(side_effect=[GeminiHttpError(503, ''), {'candidates':[{'content':{'parts':[{'text':'{}'}]}}]}])
        with tempfile.TemporaryDirectory() as tmp, patch('gemini_hybrid_client.time.sleep') as sleep:
            client = SmokeGeminiClient(api_key='fixture', transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            client.generate_json(model='gemini-3.5-flash', prompt='fixture', schema={}, operation='direct_reference_caption_generation', account_id='night_scout')
            sleep.assert_called_once_with(5)
            self.assertEqual([h['http_status'] for h in client.caption_evidence['attempt_history']], [503,200])

    def test_structured_quote_is_bound_and_claims_are_actual_caption(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "採用基準狙い目、ただ入店後の競争率は高いというイメージ"}
        source = {"target_account_id": "night_scout", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        quote = "採用基準狙い目、ただ入店後の競争率は高い"
        for candidate_quote in (quote, "存在しない採用条件や給与の保証の文章です"):
            payload = {"quote_choice": 0 if candidate_quote == quote else 99, "reader_takeaway": "僕なら採用基準だけでなく、入店後の競争率という視点も分けて考えたい。"}
            response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
            with tempfile.TemporaryDirectory() as tmp:
                client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
                args = dict(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False), schema={}, operation="direct_reference_caption_generation", account_id="night_scout")
                if candidate_quote != quote:
                    with self.assertRaises(RuntimeError): client.generate_json(**args)
                else:
                    result = client.generate_json(**args)["data"]
                    for support in result["claim_support"]:
                        self.assertIn(support["caption_claim"], result["public_post_text"])
                        self.assertEqual(support["anchor_fact_ids"], ["VF1"])
                    self.assertEqual(result["internal_analysis"]["main_claims"], [s["caption_claim"] for s in result["claim_support"]])

    def test_current_model_quota_allows_one_explicit_model_fallback(self):
        transport = Mock(side_effect=[GeminiHttpError(429, quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier', delay='3600s')),
                                     {'candidates':[{'content':{'parts':[{'text':'{}'}]}}]},
                                     {'candidates':[{'content':{'parts':[{'text':'{}'}]}}]}])
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key='fixture', transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            client.quota_basis = {}
            client.generate_json(model='gemini-3.5-flash', prompt='fixture', schema={}, operation='direct_reference_caption_generation', account_id='night_scout')
            self.assertEqual(transport.call_count, 2)
            self.assertTrue(client.caption_evidence['fallback_used'])
            self.assertEqual(client.caption_evidence['model'], 'gemini-3.1-flash-lite')
            self.assertEqual(client.caption_evidence['primary_attempt_history'][0]['http_status'], 429)
            client.generate_json(model='gemini-3.5-flash', prompt='another caption', schema={}, operation='direct_reference_caption_generation', account_id='night_scout')
            self.assertEqual(transport.call_count, 3)
            self.assertIn('gemini-3.1-flash-lite', transport.call_args.args[0])

if __name__ == '__main__':
    unittest.main()
