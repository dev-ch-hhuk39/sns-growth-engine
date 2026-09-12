#!/usr/bin/env python3
"""Preparation success is not publication success, and neither may be faked."""
import contextlib
import io
import unittest
from unittest.mock import patch

import run_media_production_pipeline as pipeline


class ClipQueueExitTests(unittest.TestCase):
    def test_caption_regeneration_flag_is_preparation_only(self):
        from unittest.mock import Mock
        for preparing in (False, True):
            with self.subTest(preparing=preparing), \
                 patch.dict(pipeline.os.environ, {"BLOCK_MEDIA_SLOT": "false"}), \
                 patch.object(pipeline, '_load', return_value={'media_public_post_auto_enabled': True}), \
                 patch.object(pipeline, 'managed_account', return_value={'scheduled_routes': ['approved_source_clip']}), \
                 patch.object(pipeline, '_records', return_value=[]), \
                 patch.object(pipeline, 'select_saved_media_candidate', return_value=(None, None, None, [])) as select:
                result = pipeline.build_plan(apply=False, confirm=False, client=Mock(),
                    post_saved_media=True, prepare_saved_media_queue=preparing)
            self.assertEqual(select.call_args.kwargs['allow_caption_regeneration'], preparing)
            self.assertFalse(result['would_post_video'])

    def test_numeric_zero_start_is_valid_but_invalid_ranges_are_not(self):
        source = {'source_video_id': 'sv', 'platform': 'youtube',
                  'canonical_video_url': 'https://www.youtube.com/watch?v=8Xmkojfw90Q'}
        clip = {'source_video_id': 'sv', 'transcript_grounded': True,
                'transcript_excerpt': 'Source excerpt for this exact time range.',
                'start_seconds': 0, 'end_seconds': 15, 'duration_seconds': 15}
        bundle, _, reasons = pipeline._build_final_caption_bundle(
            clip=clip, source_video=source, account_id='liver_manager')
        self.assertIsNotNone(bundle)
        self.assertEqual(reasons, [])
        for start, end in [(-1, 15), (0, 0), (15, 8), ('nan', 15), (0, 'inf'), ('bad', 15)]:
            with self.subTest(start=start, end=end):
                bundle, _, reasons = pipeline._build_final_caption_bundle(
                    clip={**clip, 'start_seconds': start, 'end_seconds': end},
                    source_video=source, account_id='liver_manager')
                self.assertIsNone(bundle)
                self.assertIn('final_clip_time_range_invalid', reasons)
        bundle, _, reasons = pipeline._build_final_caption_bundle(
            clip={**clip, 'start_seconds': None}, source_video=source, account_id='liver_manager')
        self.assertIsNone(bundle)
        self.assertIn('final_clip_time_range_missing', reasons)

    def ready_row(self, index=0):
        return {'queue_id': f'q{index}', 'account_id': 'liver_manager', 'platform': 'threads',
                'status': 'READY', 'public_post_text': 'approved', 'validator_status': 'PASS',
                'internal_leak_status': 'PASS', 'account_fit_status': 'PASS',
                'media_asset_id': f'asset{index}', 'generation_mode': 'saved_approved_source_clip'}

    def test_full_buffer_needs_no_acquisition_or_review(self):
        from unittest.mock import Mock
        with patch('sheets_record_reader.read_records_safely', return_value=[self.ready_row(i) for i in range(3)]), \
             patch.object(pipeline, 'process_one', return_value={'status': 'DRY_RUN'}), \
             patch.object(pipeline, 'build_plan') as planner, \
             patch.object(pipeline, 'execute') as execute:
            result = pipeline.maintain_ready_clip_inventory(Mock(), account_id='liver_manager', slot_id='lm_1800_clip_media', minimum=3)
        self.assertEqual(result['ready_count'], 3)
        planner.assert_not_called()
        execute.assert_not_called()

    def test_saved_asset_is_reviewed_before_any_new_download(self):
        from unittest.mock import Mock
        with patch('sheets_record_reader.read_records_safely', side_effect=[[], [self.ready_row()]]), \
             patch.object(pipeline, 'process_one', return_value={'status': 'DRY_RUN'}), \
             patch.object(pipeline, 'build_plan', return_value={'status': 'PLAN_ONLY', 'selected_clip_candidate_id': 'clip'}), \
             patch.object(pipeline, 'prepare_saved_media_queue', return_value={'status': 'QUEUED_WAITING_REVIEW', 'queue_id': 'q0'}), \
             patch.object(pipeline.subprocess, 'run') as review, \
             patch.object(pipeline, 'execute') as execute:
            review.return_value.returncode = 0
            result = pipeline.maintain_ready_clip_inventory(Mock(), account_id='liver_manager', slot_id='lm_1800_clip_media', minimum=1)
        self.assertEqual(result['status'], 'READY_INVENTORY_OK')
        self.assertIn('--autonomous-low-risk', review.call_args.args[0])
        self.assertEqual(review.call_args.kwargs['env']['PUBLISH_ENABLED'], 'false')
        execute.assert_not_called()

    def invoke(self, result):
        with patch('sys.argv', ['runner', '--account-id', 'liver_manager', '--use-sheets',
                               '--apply', '--confirm-production-media', '--prepare-saved-media-queue']), \
             patch.object(pipeline, 'get_config', return_value={'sheet_id': 'test', 'sa_dict': {}}), \
             patch.object(pipeline, 'SheetsClient'), \
             patch.object(pipeline, 'build_plan', return_value={'status': 'PLAN_ONLY'}), \
             patch.object(pipeline, 'prepare_saved_media_queue', return_value=result), \
             patch.object(pipeline, 'execute') as execute, \
             contextlib.redirect_stdout(io.StringIO()):
            code = pipeline.main()
        execute.assert_not_called()
        return code

    def test_verified_preparation_can_continue_to_hybrid_review(self):
        self.assertEqual(self.invoke({'status': 'QUEUED_WAITING_REVIEW', 'queue_id': 'q',
            'read_after_write': True, 'would_post_video': False}), 0)

    def test_missing_readback_is_failure(self):
        self.assertEqual(self.invoke({'status': 'QUEUED_WAITING_REVIEW', 'queue_id': 'q',
            'read_after_write': False, 'would_post_video': False}), 1)

    def test_incomplete_and_publication_results_are_not_preparation_success(self):
        for status in ('FAILED', 'QUEUE_ALREADY_EXISTS', 'POSTED', 'NO_ELIGIBLE_CLIP'):
            with self.subTest(status=status):
                self.assertEqual(self.invoke({'status': status}), 1)


if __name__ == '__main__':
    unittest.main()
