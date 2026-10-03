#!/usr/bin/env python3
"""Quota decisions and safe evidence through the real Vision provider (mock transport)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from gemini_hybrid_client import GeminiHybridClient, GeminiHttpError
from gemini_quota_diagnostics import safe_quota_diagnostics
from media.gemini_vision import GeminiVisionProvider
from test_gemini_vision_provider import observation
import run_content_quality_v2_vision_smoke as smoke


def quota(quota_id='', limit='10', delay=None, **extra):
    violation = {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests',
                 'quotaId': quota_id, 'quotaValue': limit,
                 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global',
                                     'project': 'private-project', 'user': 'private-user'}, **extra}
    details = [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [violation]}]
    if delay is not None:
        details.append({'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': delay})
    return json.dumps({'error': {'status': 'RESOURCE_EXHAUSTED', 'message': 'SECRET_KEY private-project 123456789012 billing-secret', 'details': details}})


class QuotaTests(unittest.TestCase):
    def run_vision(self, body, success=False):
        with tempfile.TemporaryDirectory() as tmp, patch('gemini_hybrid_client.time.sleep') as sleep:
            frame = Path(tmp) / 'f.jpg'
            frame.write_bytes(b'jpeg')
            good = {'candidates': [{'content': {'parts': [{'text': json.dumps(observation())}]}}]}
            error = GeminiHttpError(429, body)
            transport = Mock(side_effect=[error, good] if success else error)
            reserve = Mock()
            client = GeminiHybridClient(api_key='SECRET_KEY', transport=transport, reserve_request=reserve)
            result = GeminiVisionProvider(client).understand([frame], media_type='video')
            self.assertEqual(reserve.call_count, transport.call_count)
            return result, transport.call_count, [call.args[0] for call in sleep.call_args_list]

    def test_daily_one_attempt(self):
        r, count, sleeps = self.run_vision(quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier', delay='34s'))
        self.assertEqual((r['rate_limit_class'], count, sleeps), ('DAILY_QUOTA_EXHAUSTED', 1, []))
        self.assertEqual(r['failure_class'], 'daily_quota_exhausted')

    def test_minute_retry_info_and_success_history(self):
        r, count, sleeps = self.run_vision(quota('GenerateRequestsPerMinutePerProjectPerModel-FreeTier', delay='34s'), True)
        self.assertEqual((r['status'], count, sleeps), ('PASS', 2, [34]))
        self.assertEqual(r['attempt_history'][0]['rate_limit_class'], 'PER_MINUTE_RATE_LIMIT')
        self.assertEqual(r['attempt_history'][1], {'attempt': 2, 'http_status': 200})

    def test_zero_limit_one_attempt(self):
        r, count, sleeps = self.run_vision(quota('GenerateRequestsPerMinutePerProjectPerModel-FreeTier', limit='0'))
        self.assertEqual((r['rate_limit_class'], count, sleeps), ('MODEL_QUOTA_EXHAUSTED', 1, []))
        r, count, sleeps = self.run_vision(quota('', limit='0', quotaDimensions={}))
        self.assertEqual((count, sleeps), (1, []))

    def test_spend_deferred(self):
        r, count, sleeps = self.run_vision(quota('GenerateSpendPerProject'))
        self.assertEqual((r['rate_limit_class'], r['retry_status'], count, sleeps), ('SPEND_RATE_LIMIT', 'RETRY_DEFERRED', 1, []))

    def test_unknown_bounded_three(self):
        r, count, sleeps = self.run_vision('not JSON SECRET_KEY')
        self.assertEqual((r['rate_limit_class'], count, sleeps), ('RATE_LIMIT_UNKNOWN', 3, [5, 15]))
        self.assertEqual(len(r['attempt_history']), 3)
        self.assertEqual(r['attempt_history'][-1]['retry_status'], 'ATTEMPTS_EXHAUSTED')

    def test_token_and_delay_boundaries(self):
        for delay, attempts, waits in [('60s', 3, [60, 60]), ('60.1s', 1, []), (None, 3, [5, 15])]:
            with self.subTest(delay=delay):
                r, count, sleeps = self.run_vision(quota('GenerateInputTokensPerMinutePerProjectPerModel-FreeTier', delay=delay))
                self.assertEqual((r['rate_limit_class'], count, sleeps), ('TOKEN_RATE_LIMIT', attempts, waits))

    def test_diagnostics_and_exception_never_contain_private_fields(self):
        body = quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier',
                     subject='projects/123456789012', description='SECRET_KEY billing-secret')
        error = GeminiHttpError(429, body)
        r, _, _ = self.run_vision(body)
        evidence = str(error) + repr(vars(error)) + json.dumps(r)
        for secret in ('SECRET_KEY', 'private-project', '123456789012', 'billing-secret', 'private-user'):
            self.assertNotIn(secret, evidence)
        self.assertEqual(r['quota_model'], 'gemini-3.5-flash')
        self.assertEqual(r['quota_location'], 'global')
        self.assertEqual(r['provider_error_status'], 'RESOURCE_EXHAUSTED')
        poisoned = quota('GenerateRequestsPerDay-private-project', quotaMetric='projects/123456789012',
                         quotaDimensions={'model': 'SECRET_KEY', 'location': 'billing-secret'}, quotaValue='private-user')
        safe = json.dumps(safe_quota_diagnostics(429, poisoned))
        for secret in ('SECRET_KEY', 'private-project', '123456789012', 'billing-secret', 'private-user'):
            self.assertNotIn(secret, safe)

    def test_malformed_and_prose_not_classified(self):
        for body in ('null', '[]', '{}', '{"error":null}', '{"error":{"details":{}}}',
                     '{"error":{"message":"daily quota exhausted"}}'):
            self.assertEqual(safe_quota_diagnostics(429, body)['rate_limit_class'], 'RATE_LIMIT_UNKNOWN')

    def test_multiple_violations_daily_wins(self):
        body = json.loads(quota('GenerateRequestsPerMinutePerProjectPerModel-FreeTier'))
        body['error']['details'][0]['violations'] += json.loads(quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier'))['error']['details'][0]['violations']
        r, count, _ = self.run_vision(json.dumps(body))
        self.assertEqual((r['rate_limit_class'], count), ('DAILY_QUOTA_EXHAUSTED', 1))
        self.assertEqual(len(r['quota_violations']), 2)

    def test_single_account_cli_and_fail_closed(self):
        document = (ROOT / 'docs/CONTENT_QUALITY_V2_REVIEW_PACK.md').read_text()
        self.assertEqual([r['account_id'] for r in smoke.smoke_previews(document, 'night_scout')], ['night_scout'])
        self.assertEqual(len(smoke.smoke_previews(document, 'all')), 3)
        with self.assertRaises(ValueError):
            smoke.smoke_previews(document, 'invalid')
        for relevance, caption_status, expected in [('RELEVANCE_UNVERIFIED', 'BLOCKED', 0), ('PASS', 'BLOCKED', 1), ('PASS', 'PASS', 0)]:
            with tempfile.TemporaryDirectory() as tmp:
                result = {'media_context': {'visual_status': 'VISUAL_VERIFIED'},
                          'account_relevance': {'status': relevance}, 'status': caption_status}
                package = {'account_id': 'night_scout', 'vision': {'status': 'PASS'}, 'result': result}
                with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'RUNNER_TEMP': tmp}, clear=True), \
                     patch.object(sys, 'argv', ['smoke', '--target-account', 'night_scout', '--output', tmp + '/review.md']), \
                     patch.object(smoke, 'build_package', return_value=package) as build, \
                     patch.object(smoke, 'render', return_value='review'), patch('builtins.print'):
                    self.assertEqual(smoke.main(), expected)
                    build.assert_called_once()
                    self.assertEqual(build.call_args.args[0]['account_id'], 'night_scout')
                self.assertEqual(smoke.summary([package])['VISION_TARGET_COUNT'], 1)
                self.assertEqual(smoke.summary([package])['TARGET_ACCOUNTS'], ['night_scout'])

    def test_report_preserves_safe_quota_history(self):
        vision, _, _ = self.run_vision(quota('GenerateRequestsPerDayPerProjectPerModel-FreeTier'))
        package = {'account_id': 'night_scout', 'media_asset_id': 'fixture', 'preview_url': 'fixture',
                   'vision': vision, 'frames': [], 'result': {}, 'style': {},
                   'failure_class': vision['failure_class']}
        report = smoke.render([package])
        for field in ('PROVIDER_HTTP_STATUS', 'PROVIDER_ERROR_STATUS', 'RATE_LIMIT_CLASS',
                      'QUOTA_METRIC', 'QUOTA_ID', 'QUOTA_MODEL', 'QUOTA_LOCATION',
                      'QUOTA_LIMIT_VALUE', 'RETRY_DELAY_SECONDS', 'VISION_ATTEMPT_HISTORY'):
            self.assertIn(field + '=', report)
        self.assertIn('DAILY_QUOTA_EXHAUSTED', report)
        self.assertIn('VISION_TARGET_COUNT=1', report)
        for secret in ('SECRET_KEY', 'private-project', 'billing-secret'):
            self.assertNotIn(secret, report)

    def test_workflow_passes_existing_input_safely(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/direct-media-preparation.yml').read_text())
        job = workflow['jobs']['content-quality-v2-vision-smoke']
        step = next(step for step in job['steps'] if 'run_content_quality_v2_vision_smoke.py' in step.get('run', ''))
        self.assertEqual(step['env']['SMOKE_TARGET_ACCOUNT'], '${{ github.event.inputs.target_account }}')
        self.assertIn('--target-account "$SMOKE_TARGET_ACCOUNT"', step['run'])
        self.assertNotIn('environment', job)
        for name, other in workflow['jobs'].items():
            if name != 'content-quality-v2-vision-smoke':
                self.assertIn("content_quality_v2_vision_smoke != 'true'", other['if'])


if __name__ == '__main__':
    unittest.main()
