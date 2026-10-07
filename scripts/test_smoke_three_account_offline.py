#!/usr/bin/env python3
"""Synthetic provider replay of real editorial gates; never live E2E evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'src')]
import run_content_quality_v2_vision_smoke as smoke

class OfflineSmokeTests(unittest.TestCase):
    def test_three_accounts_keep_real_quality_gates(self):
        fixtures = [
            ('night_scout','採用基準だけでなく入店後に戦っていける強みがあるかどうかも考える', '僕なら、店選びに迷う子は採用基準だけでなく入店後に戦っていける強みがあるかどうかも分けて見るのが大事だと思う。'),
            ('liver_manager','初見の名前を呼んでから質問を一つ返しコメントを待つ', '初見への声かけって迷うよね。私ならまず、初見の名前を呼んでから質問を一つ返しコメントを待つ。次の配信で一つだけ試してみてね。'),
            ('beauty_account','リップを手の甲に三本並べて同じ照明で色の違いを見せる', 'リップを手の甲に三本並べて同じ照明で色の違いを見せる比べ方なんだけど、色選びで迷うときに見たいかも🥺✨\n\n三本を並べた色の違いから好きな色を考えるのもいい気がする'),
        ]
        for account,quote,takeaway in fixtures:
            with self.subTest(account=account), tempfile.TemporaryDirectory() as tmp:
                vision={'provider':'gemini','model':'gemini-3.5-flash','status':'PASS','http_status':200,'response_schema_status':'PASS',
                        'visual_summary':quote,'visible_action':'','key_moment':quote,'visible_text':quote,'main_topic':quote,
                        'frame_hashes':['b'*64], 'visual_facts':[{'id':'VF1','type':'visible_text','text':quote}]}
                inspected={'status':'PREVIEW_READ_OK','content_hash':'a'*64,'vision':vision,'frames':[{'sha256':'b'*64}]}
                row={'account_id':account,'media_asset_id':'offline-'+account,'preview_url':'https://example.invalid/offline.mp4'}
                def transport(url,body,timeout):
                    schema=body['generationConfig']['responseJsonSchema']
                    if 'quote_choice' in schema['properties']:
                        result={'quote_choice':0,'reader_takeaway':takeaway}
                        if account == 'beauty_account':
                            result['beauty_followup']='同じ照明で見比べるのって結構大事だよね🤍'
                    else:
                        result={'account_id':account,'status':'PASS','reason':'fixtureの具体的な比較・判断が対象読者に有用',
                                'audience_need':'具体的な行動の比較','content_pillar':'fixture','anchor_fact_types':['visible_text']}
                    return {'candidates':[{'content':{'parts':[{'text':json.dumps(result,ensure_ascii=False)}]}}]}
                client=smoke.SmokeGeminiClient(api_key='fixture',transport=transport,reserve_request=Mock(),cache_dir=Path(tmp))
                client.quota_basis={}
                with patch.object(smoke,'inspect_preview',return_value=inspected),patch.object(smoke,'SmokeGeminiClient',return_value=client):
                    package=smoke.build_package(row,Path(tmp))
                result=package['result']
                self.assertEqual(result['status'],'PASS',result.get('blocked_reasons'))
                self.assertEqual(result['remove_media_test']['status'],'PASS')
                self.assertEqual(result['fabricated_experience_check']['status'],'PASS')
                self.assertEqual(package['style']['status'],'PASS',package['style'])
                self.assertEqual(result['publish_eligibility']['status'],'BLOCKED')
                self.assertEqual(smoke.summary([package])['EDITORIAL_E2E_PASS_COUNT'],1)

    def test_provider_failure_cannot_exit_success(self):
        package={'account_id':'night_scout','vision':{'status':'PASS'},'result':{'media_context':{'visual_status':'VISUAL_VERIFIED'},'account_relevance':{'status':'RELEVANCE_UNVERIFIED'}},
                 'relevance_provider_evidence':{'provider_status':'UNAVAILABLE'}}
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'GITHUB_ACTIONS':'true','RUNNER_TEMP':tmp},clear=True), \
             patch.object(sys,'argv',['smoke','--target-account','night_scout','--output',tmp+'/review.md']), \
             patch.object(smoke,'build_package',return_value=package),patch.object(smoke,'render',return_value='fixture'),patch('builtins.print'):
            self.assertEqual(smoke.main(),1)

if __name__=='__main__': unittest.main()
