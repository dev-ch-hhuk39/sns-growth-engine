#!/usr/bin/env python3
"""Clip discovery shares caption failover without spending on off-topic clips."""
import unittest
from unittest.mock import patch

import run_media_growth_engine as engine
from evidence_context_caption import DirectCaptionProviderFailover
from media_growth_test_fixtures import fixture_caption_service, liver_video_and_transcript


class ClipCaptionTests(unittest.TestCase):
    def test_initial_stage_has_same_bounded_failover_as_final_caption(self):
        service = engine._default_growth_caption_service(25)
        self.assertIsInstance(service.generation_provider, DirectCaptionProviderFailover)

    def test_unsuitable_excerpt_does_not_consume_remote_budget(self):
        video, transcript = liver_video_and_transcript()
        unrelated = {**video, 'source_video_id': 'sv_bad', 'video_id': 'badabcdefgh',
                     'canonical_video_url': 'https://www.youtube.com/watch?v=badabcdefgh'}
        unrelated_transcript = {**transcript, 'source_video_id': 'sv_bad', 'transcript_id': 'tr_bad'}
        good = '配信で初見が入りやすくなるには、入室時に今の話題を短く伝え、コメントしやすい質問を置くことが大事です。'
        bad = '週末の旅行では、雨の日にも歩きやすい靴を選び、荷物を少なくすると移動が楽になります。'
        def specs(row, *_args, **_kwargs):
            return [{'start': 1, 'end': 20, 'excerpt': bad if row['source_video_id'] == 'sv_bad' else good}]
        service = fixture_caption_service()
        with patch.object(engine, '_default_growth_caption_service', return_value=service), \
             patch.object(engine, '_clip_specs_from_transcript', side_effect=specs), \
             patch.object(service, 'generate', wraps=service.generate) as generation:
            plan = engine.build_media_growth_plan('liver_manager',
                existing_source_videos=[unrelated, video], existing_transcripts=[unrelated_transcript, transcript])
        self.assertEqual(generation.call_count, 1)
        self.assertEqual(generation.call_args.args[0].source_post_id, video['source_video_id'])
        self.assertEqual(plan['caption_generation_budget']['remote_caption_generations_used'], 1)
        self.assertTrue(any('clip_account_evidence_insufficient' in row['blockers'] for row in plan['rejected_clip_candidates']))


if __name__ == '__main__':
    unittest.main()
