#!/usr/bin/env python3
"""Smoke-only relevance transport evidence, with no real provider calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from gemini_hybrid_client import GeminiHybridClient, GeminiHttpError
from test_gemini_quota_diagnostics import quota
import run_content_quality_v2_vision_smoke as smoke

SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'string'}}, 'required': ['ok']}
GOOD = {'candidates': [{'content': {'parts': [{'text': '{"ok":"yes"}'}]}}]}


class RelevanceQuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transport = Mock(return_value=GOOD)
        self.client = GeminiHybridClient(api_key='SECRET_KEY', transport=self.transport,
                                         reserve_request=Mock(), cache_dir=Path(self.tmp.name))
        self.args = dict(model='gemini-3.5-flash', prompt='fixture', schema=SCHEMA,
                         operation='vision_smoke_relevance', account_id='night_scout')
        patcher = patch('gemini_hybrid_client.time.sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def run_error(self, body):
        self.transport.side_effect = GeminiHttpError(429, body)
        with self.assertRaises(GeminiHttpError) as raised:
            self.client.generate_json(**self.args, retry_profile='vision_relevance')
        return raised.exception

    def test_daily_diagnostics_one_attempt(self):
        exc = self.run_error(quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier'))
        self.assertEqual(exc.attempt_count, 1)
        self.assertEqual(exc.quota_diagnostics['rate_limit_class'], 'DAILY_QUOTA_EXHAUSTED')
        self.assertEqual(exc.attempt_history[0]['retry_status'], 'NO_RETRY')
        self.sleep.assert_not_called()

    def test_minute_then_success_and_cache_history(self):
        self.transport.side_effect = [GeminiHttpError(429, quota('GenerateRequestsPerMinutePerProjectPerModel-FreeTier', delay='34s')), GOOD]
        r = self.client.generate_json(**self.args, retry_profile='vision_relevance')
        self.assertEqual(r['actual_requests'], 2)
        self.assertEqual([x['http_status'] for x in r['attempt_history']], [429, 200])
        self.assertEqual(r['attempt_history'][0]['rate_limit_class'], 'PER_MINUTE_RATE_LIMIT')
        self.sleep.assert_called_once_with(34)
        cached = self.client.generate_json(**self.args, retry_profile='vision_relevance')
        self.assertEqual((cached['actual_requests'], cached['attempt_history']), (0, []))
        self.assertNotIn('attempt_history', self.client.generate_json(**self.args))

    def test_unknown_final_bounded_and_evidence_safe(self):
        exc = self.run_error('raw SECRET_KEY private-project billing-secret')
        self.assertEqual(exc.attempt_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 15])
        self.assertEqual(len(exc.attempt_history), 3)
        self.assertEqual(exc.quota_diagnostics['rate_limit_class'], 'RATE_LIMIT_UNKNOWN')
        for secret in ('SECRET_KEY', 'private-project', 'billing-secret'):
            self.assertNotIn(secret, str(exc) + repr(vars(exc)))

    def test_503_then_success(self):
        self.transport.side_effect = [GeminiHttpError(503, 'private-body'), GOOD]
        r = self.client.generate_json(**self.args, retry_profile='vision_relevance')
        self.assertEqual(r['actual_requests'], 2)
        self.assertEqual([x['http_status'] for x in r['attempt_history']], [503, 200])
        self.sleep.assert_called_once_with(5)

    def test_deferred_and_zero(self):
        for qid, limit, delay, decision in [
            ('GenerateSpendPerProject', '10', None, 'RETRY_DEFERRED'),
            ('GenerateRequestsPerMinutePerProjectPerModel', '10', '61s', 'RETRY_DEFERRED'),
            ('GenerateRequestsPerModel', '0', None, 'NO_RETRY'),
        ]:
            with self.subTest(qid=qid):
                self.transport.reset_mock()
                exc = self.run_error(quota(qid, limit=limit, delay=delay))
                self.assertEqual((exc.attempt_count, exc.retry_status), (1, decision))
                self.assertEqual(self.transport.call_count, 1)
        self.sleep.assert_not_called()

    def test_normal_profile_retains_two_attempts_and_two_second_wait(self):
        self.transport.side_effect = GeminiHttpError(429, quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier'))
        with self.assertRaises(GeminiHttpError) as raised:
            self.client.generate_json(**self.args)
        self.assertEqual(self.transport.call_count, 2)
        self.sleep.assert_called_once_with(2)
        self.assertFalse(hasattr(raised.exception, 'attempt_history'))

    def test_schema_failure_history_and_no_retry(self):
        self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': '{}'}]}}]}
        with self.assertRaises(RuntimeError) as raised:
            self.client.generate_json(**self.args, retry_profile='vision_relevance')
        self.assertEqual(raised.exception.attempt_history, [{'attempt': 1, 'http_status': 200}])
        self.sleep.assert_not_called()

    def test_transport_history_bounded(self):
        self.transport.side_effect = TimeoutError('SECRET_KEY')
        with self.assertRaises(RuntimeError) as raised:
            self.client.generate_json(**self.args, retry_profile='vision_relevance')
        self.assertEqual(len(raised.exception.attempt_history), 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 15])
        self.assertNotIn('SECRET_KEY', str(raised.exception))

    def test_smoke_failure_and_success_evidence_rendered(self):
        context = {'visual_status': 'VISUAL_VERIFIED', 'visual_facts': []}
        for error in (True, False):
            with self.subTest(error=error):
                self.transport.side_effect = GeminiHttpError(429, quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier')) if error else None
                data = {'account_id': 'night_scout', 'status': 'RELEVANCE_UNVERIFIED', 'reason': 'insufficient_visual_evidence_for_account', 'audience_need': '', 'content_pillar': '', 'anchor_fact_types': []}
                self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': json.dumps(data)}]}}]}
                with patch.object(smoke, 'prepare_media_context', return_value=context):
                    review = smoke.relevance_review({'account_id': 'night_scout'}, {}, self.client)
                self.assertEqual(review['attempt_count'], 1)
                self.assertEqual(review['attempt_history'][0]['http_status'], 429 if error else 200)
                self.assertEqual(review['provider_status'], 'UNAVAILABLE' if error else 'PASS')
                if error:
                    self.assertEqual(review['rate_limit_class'], 'DAILY_QUOTA_EXHAUSTED')
                package = {'account_id': 'night_scout', 'media_asset_id': 'fixture', 'preview_url': 'fixture',
                           'vision': {}, 'frames': [], 'style': {}, 'failure_class': '',
                           'relevance_provider_evidence': review, 'result': {'account_relevance': review}}
                report = smoke.render([package])
                for key in ('RATE_LIMIT_CLASS', 'QUOTA_METRIC', 'QUOTA_ID', 'QUOTA_MODEL', 'QUOTA_LOCATION',
                            'QUOTA_LIMIT_VALUE', 'RETRY_DELAY_SECONDS', 'RETRY_STATUS', 'QUOTA_VIOLATIONS', 'ATTEMPT_HISTORY', 'DECISION_CLASS'):
                    self.assertIn('RELEVANCE_' + key + '=', report)
                for secret in ('SECRET_KEY', 'private-project', 'private-user', '123456789012', 'billing-secret'):
                    self.assertNotIn(secret, report)


if __name__ == '__main__':
    unittest.main()
