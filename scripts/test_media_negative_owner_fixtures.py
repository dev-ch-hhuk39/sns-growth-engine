#!/usr/bin/env python3
"""Owner's historical negative captions stay rejected; offline fixtures only."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'src')]
from generation import content_quality_v2 as quality
from test_media_first_pipeline import asset

class OwnerNegativeFixtures(unittest.TestCase):
    def test_ns_m03_unverified_garbled_never_generates(self):
        row=asset('night_scout');row.pop('visual_evidence')
        generator=Mock(return_value={'status':'PASS','public_post_text':'僕なら、ニルスるなちゃんYouTubeの顔面ケーキしてた痛客実はオオハタでしたと思うんだよね。'})
        result=quality.generate_media_first_caption(media=row,account_id='night_scout',account_content_contract={},recent_posts=[],caption_generator=generator,editorial_draft=True)
        generator.assert_not_called()
        self.assertEqual(result['public_post_text'],'')

    def test_lm_m02_generic_advice_has_no_fact_support(self):
        ctx=quality.prepare_media_context(asset(),account_id='liver_manager')
        angle=quality.select_media_angles(ctx,quality.evaluate_media_relevance(ctx,{'audience':'配信者'}))['selected']
        text='配信中に「あれ、これ前にも言ったかな？」とふと不安になること、ありませんか。皆さんは、話のネタや話題の切り出し方にどんな工夫をしていますか。悩み事があればいつでも聞かせてくださいね。'
        self.assertEqual(quality.remove_media_test(text,ctx,angle)['generic_caption_risk'],'HIGH')

    def test_ba_m01_omitted_first_person_experience_blocked(self):
        text='最近肌のざらつきが気になってたんだけど、皮脂や角質を浮かせてケアできるパックを試してみたの🥺✨これ結構大事なステップかも。1週間くらい使い続けたら、気になっていたザラつきが意外と落ち着いてきてほんとに嬉しい🫶🏻'
        self.assertEqual(quality.fabricated_media_experience(text)['status'],'BLOCKED')
        self.assertEqual(quality.fabricated_media_experience('投稿者は「使い続けたら嬉しい変化があった」と話している。')['status'],'PASS')
        self.assertEqual(quality.fabricated_media_experience('投稿者は商品を紹介している。使ってみたら嬉しい変化があった。')['status'],'BLOCKED')

if __name__=='__main__': unittest.main()
