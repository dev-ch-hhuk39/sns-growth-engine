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
from gemini_hybrid_client import GeminiHybridClient, GeminiHttpError, GeminiProviderUnavailableError
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
        sleeper = patch('gemini_hybrid_client.time.sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

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
        for changes in ({'visual_summary': ''}, {'visible_action': None}, {'key_moment': ''},
                        {'visual_facts': []}, {'visual_facts': [{}]}, {'main_claims': 'wrong'},
                        {'visual_summary': 'SECRET_TEST_KEY'}):
            data = {**observation(), **changes}
            self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': json.dumps(data)}]}}]}
            result = self.provider.understand([self.frame], media_type='video')
            self.assertEqual(result['status'], 'UNAVAILABLE', changes)
            self.assertEqual(result['http_status'], 200)
            self.assertEqual(result['response_schema_status'], 'INVALID')
            self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))

    def respond(self, value):
        self.transport.side_effect = None
        self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': value}]}}]}
        return self.provider.understand([self.frame], media_type='video')

    def test_fenced_json_and_safe_alias(self):
        data = observation()
        data['visible_actions'] = [data.pop('visible_action')]
        result = self.respond('```json\n' + json.dumps(data) + '\n```')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['visible_action'], observation()['visible_action'])
        self.assertEqual(result['normalizations'], ['visible_actions->visible_action'])
        self.assertEqual(result['parse_stage'], 'complete')
        self.sleep.assert_not_called()

    def test_missing_facts_diagnostic_without_retry(self):
        data = observation()
        del data['visual_facts']
        result = self.respond(json.dumps(data))
        self.assertEqual(result['failure_class'], 'schema_missing_field')
        self.assertEqual(result['missing_fields'], ['visual_facts'])
        self.assertEqual(result['parse_stage'], 'schema_validation')
        self.assertEqual(result['attempt_count'], 1)
        self.sleep.assert_not_called()

    def test_wrong_type_diagnostic_without_values(self):
        result = self.respond(json.dumps({**observation(), 'visual_action': 'UNKNOWN_SECRET', 'visual_facts': 'PRIVATE_VALUE'}))
        self.assertEqual(result['failure_class'], 'invalid_response')
        self.assertNotIn('UNKNOWN_SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE_VALUE', json.dumps(result))
        result = self.respond(json.dumps({**observation(), 'visual_facts': 'PRIVATE_VALUE'}))
        self.assertEqual(result['schema_error'], 'TYPE_MISMATCH')
        self.assertEqual(result['field'], 'visual_facts')
        self.assertEqual(result['expected_type'], 'array')
        self.assertEqual(result['raw_response_type'], 'string')
        self.sleep.assert_not_called()

    def test_prose_truncated_json_and_conflicting_alias_rejected(self):
        for text in ('Here is JSON: ' + json.dumps(observation()), '```json\n{}', '[1,2]', '{invalid}'):
            result = self.respond(text)
            self.assertEqual(result['failure_class'], 'invalid_response')
            self.assertEqual(result['parse_stage'], 'json_parse')
        result = self.respond(json.dumps({**observation(), 'visible_actions': 'different'}))
        self.assertEqual(result['schema_error'], 'CONFLICTING_ALIAS')
        self.sleep.assert_not_called()

    def test_503_then_success_and_retry_cap(self):
        good = self.transport.return_value
        self.transport.side_effect = [GeminiHttpError(503, 'PRIVATE'), good]
        result = self.provider.understand([self.frame], media_type='video')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['attempt_count'], 2)
        self.sleep.assert_called_once_with(5)
        self.sleep.reset_mock()
        self.transport.reset_mock()
        self.transport.side_effect = GeminiHttpError(503, 'PRIVATE')
        result = self.provider.understand([self.frame], media_type='video')
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['attempt_count'], 3)
        self.assertEqual(self.transport.call_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 15])

    def test_transient_transport_and_nonretryable_http(self):
        good = self.transport.return_value
        self.transport.side_effect = [GeminiProviderUnavailableError('TIMEOUT'), good]
        self.assertEqual(self.provider.understand([self.frame], media_type='video')['status'], 'PASS')
        for status in (400, 401, 403, 404, 500):
            self.transport.reset_mock()
            self.sleep.reset_mock()
            self.transport.side_effect = GeminiHttpError(status, 'PRIVATE')
            self.provider.understand([self.frame], media_type='video')
            self.assertEqual(self.transport.call_count, 1)
            self.sleep.assert_not_called()

    def test_empty_field_and_duplicate_fact_diagnostics(self):
        result = self.respond(json.dumps({**observation(), 'visual_summary': ' '}))
        self.assertEqual(result['empty_fields'], ['visual_summary'])
        self.assertEqual(result['parse_stage'], 'visual_evidence')
        data = observation()
        data['visual_facts'] *= 2
        result = self.respond(json.dumps(data))
        self.assertEqual(result['schema_error'], 'DUPLICATE_FACT_IDS')
        self.sleep.assert_not_called()

    def test_only_required_fields_can_pass(self):
        data = observation()
        data = {k: data[k] for k in ('visual_summary', 'visible_action', 'key_moment', 'visual_facts')}
        result = self.respond(json.dumps(data))
        self.assertEqual(result['status'], 'PASS')
        self.assertNotIn('main_topic', result)

    def static_media(self):
        data = observation()
        data['visible_action'] = ''
        data['visual_summary'] = '条件の料金表が表示された静止画面'
        data['key_moment'] = '料金表の全体が表示されたフレーム'
        data['visual_facts'] = [{'id': 'VF1', 'type': 'visible_text', 'text': '時給の条件が画面に表示されている'}]
        vision = self.respond(json.dumps(data))
        row = {**asset(), **vision, 'vision_status': vision['status'], 'strict_relevance_review': True}
        row['visual_evidence']['provider'] = 'gemini'
        return row

    def test_empty_action_valid_at_all_vision_boundaries(self):
        row = self.static_media()
        self.assertEqual(row['vision_status'], 'PASS')
        ctx = quality.prepare_media_context(row, account_id='liver_manager')
        self.assertEqual(ctx['visual_status'], 'VISUAL_VERIFIED')
        self.assertEqual(ctx['visible_action'], '')
        self.assertEqual(ctx['visual_facts'][0]['type'], 'visible_text')
        for action in (None, [], 1):
            self.assertEqual(quality.prepare_media_context({**row, 'visible_action': action},
                account_id='liver_manager')['visual_status'], 'VISUAL_UNVERIFIED')

    def review_data(self):
        return {'status': 'PASS', 'account_id': 'liver_manager', 'reason': '配信UIのコメント表示を比較できる',
                'audience_need': 'コメントの読みやすさ', 'content_pillar': '配信環境',
                'anchor_fact_types': ['visible_text']}

    def evaluate_review(self, row, review):
        row = {**row, 'account_relevance_review': review}
        context = quality.prepare_media_context(row, account_id='liver_manager')
        return quality.evaluate_media_relevance(context, {}), context

    def test_strict_text_fact_anchor_and_unknown_types(self):
        row = self.static_media()
        review = self.review_data()
        result, context = self.evaluate_review(row, review)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['anchor_fact_ids'], [context['visual_facts'][0]['id']])
        self.assertEqual(result['evidence'], context['visual_facts'][0]['text'])
        angles = quality.select_media_angles(context, result)
        self.assertEqual(angles['selected']['anchor_fact_ids'], result['anchor_fact_ids'])
        for types in (['visible_action'], ['invented'], ['visible_text', 'visible_action'], [], None):
            result, _ = self.evaluate_review(row, {**review, 'anchor_fact_types': types})
            self.assertEqual(result['status'], 'RELEVANCE_UNVERIFIED')
            self.assertEqual(result['anchor_fact_ids'], [])
        for key in ('reason', 'audience_need', 'content_pillar'):
            self.assertEqual(self.evaluate_review(row, {**review, key: ' '})[0]['status'], 'RELEVANCE_UNVERIFIED')
        self.assertEqual(self.evaluate_review(row, {**review, 'account_id': 'beauty_account'})[0]['status'], 'RELEVANCE_UNVERIFIED')

    def test_semantic_relevance_reason_preserved_in_review(self):
        row = self.static_media()
        data = {**self.review_data(), 'status': 'RELEVANCE_UNVERIFIED', 'reason': '具体的判断材料が不足'}
        self.transport.return_value = {'candidates': [{'content': {'parts': [{'text': json.dumps(data)}]}}]}
        review = relevance_review(row, {}, self.client)
        result, _ = self.evaluate_review(row, review)
        self.assertEqual(result['decision_class'], 'SEMANTIC_UNVERIFIED')
        self.assertEqual(result['reason'], data['reason'])
        self.assertEqual(result['provider_status'], 'PASS')
        self.assertEqual(result['provider_http_status'], 200)
        self.assertEqual(result['attempt_count'], 1)
        from run_content_quality_v2_vision_smoke import render
        package = {'account_id': 'liver_manager', 'media_asset_id': 'asset1', 'preview_url': 'fixture',
                   'vision': {}, 'frames': [], 'style': {}, 'failure_class': '', 'result': {'account_relevance': result}}
        markdown = render([package])
        self.assertIn('RELEVANCE_REASON=\n\n具体的判断材料が不足', markdown)
        self.assertIn('SEMANTIC_UNVERIFIED', markdown)
        self.assertIn('RELEVANCE_PROVIDER_HTTP_STATUS=\n\n200', markdown)

    def test_vision_429_retries_bounded(self):
        good = self.transport.return_value
        for failures in (1, 2, 3):
            self.transport.reset_mock()
            self.sleep.reset_mock()
            self.transport.side_effect = [GeminiHttpError(429, 'SECRET_TEST_KEY')] * failures + [good]
            result = self.provider.understand([self.frame], media_type='video')
            self.assertEqual(result['attempt_count'], min(3, failures + 1))
            self.assertEqual(self.transport.call_count, min(3, failures + 1))
            self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 15][:failures])
            self.assertEqual(result['status'], 'PASS' if failures < 3 else 'UNAVAILABLE')
            if failures == 3:
                self.assertEqual(result['failure_class'], 'rate_limited')
            self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))

    def test_relevance_429_retry_and_provider_failure_separation(self):
        row = self.static_media()
        good = {'candidates': [{'content': {'parts': [{'text': json.dumps(self.review_data())}]}}]}
        for failures in (1, 2, 3):
            self.transport.reset_mock()
            self.sleep.reset_mock()
            self.transport.side_effect = [GeminiHttpError(429, 'SECRET_TEST_KEY')] * failures + [good]
            # Separate successful caches so each scenario exercises transport.
            self.client.cache_dir = Path(self.temp.name) / str(failures)
            review = relevance_review(row, {}, self.client)
            result, _ = self.evaluate_review(row, review)
            self.assertEqual(review['attempt_count'], min(3, failures + 1))
            self.assertEqual(self.transport.call_count, min(3, failures + 1))
            self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 15][:failures])
            if failures < 3:
                self.assertEqual(result['status'], 'PASS')
            else:
                self.assertEqual(result['decision_class'], 'PROVIDER_UNAVAILABLE')
                self.assertEqual(result['provider_http_status'], 429)
                self.assertEqual(result['review_status'], 'NOT_RUN')
                self.assertEqual(result['reason'], '')
            self.assertNotIn('SECRET_TEST_KEY', json.dumps(result))

    def test_relevance_503_transport_and_nonretryable_errors(self):
        row = self.static_media()
        good = {'candidates': [{'content': {'parts': [{'text': json.dumps(self.review_data())}]}}]}
        for index, error in enumerate((GeminiHttpError(503, ''), GeminiProviderUnavailableError('TIMEOUT'),
                                      GeminiHttpError(400, ''), GeminiHttpError(401, ''), GeminiHttpError(403, ''),
                                      GeminiHttpError(404, ''), GeminiHttpError(500, ''), RuntimeError('schema invalid'))):
            self.client.cache_dir = Path(self.temp.name) / ('case' + str(index))
            self.transport.reset_mock()
            self.sleep.reset_mock()
            self.transport.side_effect = [error, good]
            review = relevance_review(row, {}, self.client)
            self.assertEqual(review['attempt_count'], 2 if index < 2 else 1)
            self.assertEqual(self.transport.call_count, 2 if index < 2 else 1)
            if index < 2:
                self.assertEqual(review['status'], 'PASS')
            else:
                self.sleep.assert_not_called()

    def test_smoke_keeps_static_vision_and_semantic_reason(self):
        from run_content_quality_v2_vision_smoke import build_package, render
        row = self.static_media()
        inspected = {'status': 'PREVIEW_READ_OK', 'vision': row, 'content_hash': row['content_hash'],
                     'frames': [{'sha256': 'b' * 64}]}
        review = {**self.review_data(), 'status': 'RELEVANCE_UNVERIFIED', 'reason': '用途不明',
                  'provider_status': 'PASS', 'provider_http_status': 200, 'attempt_count': 1}
        with patch('run_content_quality_v2_vision_smoke.inspect_preview', return_value=inspected), \
             patch('run_content_quality_v2_vision_smoke.relevance_review', return_value=review), \
             patch('run_content_quality_v2_vision_smoke.SourceGroundedCaptionService') as caption:
            package = build_package({'account_id': 'liver_manager', 'media_asset_id': row['media_asset_id'],
                                     'preview_url': row['storage_url']}, Path(self.temp.name))
        self.assertEqual(package['vision']['status'], 'PASS')
        self.assertEqual(package['result']['media_context']['visual_status'], 'VISUAL_VERIFIED')
        caption.return_value.generate_media_context.assert_not_called()
        markdown = render([package])
        self.assertIn('RELEVANCE_REASON=\n\n用途不明', markdown)
        self.assertIn('VISION_ATTEMPT_COUNT=\n\n1', markdown)
        self.assertIn('RELEVANCE_ATTEMPT_COUNT=\n\n1', markdown)

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
        self.assertEqual(result['status'], 'NOT_RUN')

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
