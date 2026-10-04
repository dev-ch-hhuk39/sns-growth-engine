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
        transport = Mock(side_effect=GeminiHttpError(429, quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier')))
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

if __name__ == '__main__':
    unittest.main()
