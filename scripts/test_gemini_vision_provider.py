#!/usr/bin/env python3
"""Multimodal transport, secret-safe errors and asset-bound Vision contracts."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from gemini_hybrid_client import GeminiHybridClient, GeminiHttpError
from media.gemini_vision import GeminiVisionProvider
from media.direct_content_understanding import vision_summary
from generation import content_quality_v2 as quality
from test_media_first_pipeline import asset
from run_content_quality_v2_vision_smoke import relevance_review
from evidence_context_caption import PrivacyBoundedGeminiGroundedProvider
from generation.source_grounded_caption import SourceGroundedCaptionService
from acquisition.models import SourcePostBundle


def observation():
    return dict(visual_summary='人物がカードを持ち上げる', visible_text='',
                visible_people_or_objects='人物と青いカード', visible_action='青いカードを持ち上げる',
                key_moment='机の前でカードを掲げた場面', main_topic='カードの提示',
                visual_facts=[{'id': 'VF1', 'type': 'visible_action', 'text': '青いカードを持ち上げる'}],
                main_claims=[], uncertain_claims=[], safety_flags=[])


class GeminiVisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.frame = Path(self.temp.name) / 'frame.jpg'
        self.frame.write_bytes(b'jpeg-test-bytes')
        self.transport = Mock(return_value={'candidates': [{'content': {'parts': [{'text': json.dumps(observation())}]}}]})
        self.client = GeminiHybridClient(api_key='SECRET_TEST_KEY', transport=self.transport,
                                         reserve_request=Mock(), cache_dir=Path(self.temp.name) / 'cache')
        self.provider = GeminiVisionProvider(self.client)

    def test_inline_images_and_no_persistence(self):
        result = self.provider.understand([self.frame] * 4, media_type='video')
        self.assertEqual(result['status'], 'PASS', result)
        url, body, timeout = self.transport.call_args.args
        self.assertIn('generativelanguage.googleapis.com', url)
        self.assertNotIn('github', url)
        parts = body['contents'][0]['parts']
        self.assertEqual(len([p for p in parts if 'inlineData' in p]), 3)
        self.assertEqual(parts[1]['inlineData']['mimeType'], 'image/jpeg')
        self.assertTrue(parts[1]['inlineData']['data'])
        self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
        self.assertIn('responseJsonSchema', body['generationConfig'])
        self.assertEqual(result['http_status'], 200)
        self.assertEqual(result['response_schema_status'], 'PASS')
        self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))
        self.assertFalse((Path(self.temp.name) / 'cache').exists())

    def test_metadata_transcript_account_never_sent_and_retired_not_selected(self):
        with patch('media.gemini_vision.GeminiHybridClient', return_value=self.client), \
             patch('requests.post', side_effect=AssertionError('retired request')):
            result = vision_summary([self.frame], media_type='video',
                                    source_metadata={'secret_marker': 'METADATA_MARKER'},
                                    transcript={'text': 'TRANSCRIPT_MARKER'},
                                    account_content_contract={'purpose': 'STRATEGY_MARKER'})
        self.assertEqual(result['provider'], 'gemini')
        sent = json.dumps(self.transport.call_args.args[1])
        for marker in ('METADATA_MARKER', 'TRANSCRIPT_MARKER', 'STRATEGY_MARKER'):
            self.assertNotIn(marker, sent)

    def test_errors_secret_safe_and_http_observable(self):
        for status, expected in ((400, 'invalid_response'), (401, 'auth_rejected'), (403, 'auth_rejected'),
                                 (429, 'rate_limited'), (404, 'model_unavailable'), (503, 'provider_internal_error')):
            self.transport.side_effect = GeminiHttpError(status, 'SECRET_TEST_KEY private body')
            result = self.provider.understand([self.frame], media_type='video')
            self.assertEqual(result['http_status'], status)
            self.assertEqual(result['failure_class'], expected)
            self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))
            self.assertNotIn('private body', json.dumps(result))

    def test_invalid_schema_empty_and_key_echo_rejected(self):
        for changes in ({'visual_summary': ''}, {'visible_action': ' '}, {'key_moment': ''},
                        {'visual_facts': []}, {'visual_facts': [{}]}, {'main_claims': 'wrong'},
                        {'visual_summary': 'SECRET_TEST_KEY'}):
            data = {**observation(), **changes}
            self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': json.dumps(data)}]}}]}
            result = self.provider.understand([self.frame], media_type='video')
            self.assertEqual(result['status'], 'UNAVAILABLE', changes)
            self.assertEqual(result['http_status'], 200)
            self.assertEqual(result['response_schema_status'], 'INVALID')
            self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))

    def test_no_frame_no_request(self):
        self.assertEqual(self.provider.understand([], media_type='video')['failure_class'], 'no_frames')
        self.transport.assert_not_called()

    def test_gemini_contract_bound_and_frame_only_invalid(self):
        vision = self.provider.understand([self.frame], media_type='video')
        row = {**asset(), **vision, 'vision_status': 'PASS'}
        row['visual_evidence']['provider'] = 'gemini'
        ctx = quality.prepare_media_context(row, account_id='liver_manager')
        self.assertEqual(ctx['visual_status'], 'VISUAL_VERIFIED')
        self.assertEqual(ctx['visual_facts'][0]['text'], observation()['visual_facts'][0]['text'])
        for change in ({'visual_facts': []}, {'visual_summary': ''}, {'http_status': 400},
                       {'response_schema_status': 'INVALID'}, {'content_hash': 'foreign'}, {'media_asset_id': 'foreign'}):
            result = quality.prepare_media_context({**row, **change}, account_id='liver_manager')
            self.assertEqual(result['visual_status'], 'VISUAL_UNVERIFIED', change)
        other = copy.deepcopy(row)
        other['visual_evidence']['status'] = 'EXTRACTED_ONLY'
        self.assertEqual(quality.prepare_media_context(other, account_id='liver_manager')['visual_status'], 'VISUAL_UNVERIFIED')
        other['visual_evidence']['status'] = 'UNDERSTOOD'
        other['visual_evidence']['provider'] = 'github_models_vision'
        self.assertEqual(quality.prepare_media_context(other, account_id='liver_manager')['visual_status'], 'VISUAL_UNVERIFIED')

    def test_relevance_never_called_before_vision(self):
        client = Mock()
        result = relevance_review({**asset(), 'vision_status': 'UNAVAILABLE'}, {}, client)
        client.generate_json.assert_not_called()
        self.assertEqual(result['status'], 'RELEVANCE_UNVERIFIED')

    def test_existing_gemini_caption_receives_fact_ids(self):
        client = Mock(api_key='fixture')
        client.generate_json.return_value = {'data': {}, 'model': 'gemini-3.5-flash'}
        provider = PrivacyBoundedGeminiGroundedProvider(client)
        row = asset()
        ctx = quality.prepare_media_context(row, account_id='liver_manager')
        angle = quality.select_media_angles(ctx, quality.evaluate_media_relevance(ctx, {}))['selected']
        post = SourcePostBundle(source_post_id='', source_id='', target_account_id='liver_manager',
                                platform='', profile_url='', canonical_post_url='', external_post_id='',
                                original_post_text='HISTORICAL_MARKER', published_at='')
        service = SourceGroundedCaptionService(provider, allow_deterministic_fallback=False,
                                               retry_primary_on_alignment_failure=False)
        service.generate_media_context(post, media_context=ctx, selected_post_angle=angle,
                                       account_content_contract={}, recent_posts=[])
        sent = client.generate_json.call_args.kwargs
        self.assertIn(ctx['visual_facts'][0]['id'], sent['prompt'])
        self.assertNotIn('HISTORICAL_MARKER', sent['prompt'])
        self.assertIn('anchor_fact_ids', sent['schema']['properties']['claim_support']['items']['required'])
        self.assertEqual(client.generate_json.call_count, 1)


if __name__ == '__main__':
    unittest.main()
