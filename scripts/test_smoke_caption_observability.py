#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / 'src')]
from run_content_quality_v2_vision_smoke import SmokeGeminiClient, rebind_style_repair_claims
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

    def test_night_prompt_is_account_isolated(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "採用基準狙い目、ただ入店後の競争率は高いというイメージ"}
        source = {"target_account_id": "night_scout", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0, "reader_takeaway": "僕なら採用基準と入店後の競争率を分けて、自分の強みも一緒に見るのが大事だと思う。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        transport = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                 schema={}, operation="direct_reference_caption_generation", account_id="night_scout")
        sent = transport.call_args.args[1]["contents"][0]["parts"][0]["text"]
        self.assertIn("男性の夜職・キャバクラ専門スカウト", sent)
        self.assertIn("配信文脈は禁止", sent)
        self.assertNotIn("Liverは", sent)
        self.assertNotIn("Beautyは", sent)
        self.assertNotIn("🥺", sent)

    def test_night_rejects_cross_account_live_context_and_beauty_emoji(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "採用基準狙い目、ただ入店後の競争率は高いというイメージ"}
        source = {"target_account_id": "night_scout", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        cases = [
            ("僕なら採用基準と競争率を分けて見るよ。次の配信では強みを整理してみてね。", "night_cross_account_live_context"),
            ("僕なら採用基準と入店後の競争率を分けて、自分の強みも一緒に見るのが大事だと思う🥺", "night_cross_account_beauty_emoji"),
        ]
        for takeaway, expected in cases:
            with self.subTest(expected=expected):
                payload = {"quote_choice": 0, "reader_takeaway": takeaway}
                response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
                with tempfile.TemporaryDirectory() as tmp:
                    client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
                    with self.assertRaisesRegex(RuntimeError, expected):
                        client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                             schema={}, operation="direct_reference_caption_generation", account_id="night_scout")
                    self.assertEqual(client.caption_evidence.get("validation_error"), expected)

    def test_night_rejects_unobserved_judgement_axis(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "採用基準狙い目、ただ入店後の競争率は高いというイメージ"}
        source = {"target_account_id": "night_scout", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "僕なら採用基準と入店後の競争率を分けて見るよ。君が環境に馴染めるかも確認するのが大事だと思う。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "night_unobserved_context_added"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="night_scout")
            self.assertEqual(client.caption_evidence.get("validation_error"), "night_unobserved_context_added")

    def test_beauty_prompt_prefers_visible_use_scene_without_fake_experience(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "スポイトから透明な液体を手の甲に垂らす"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "スポイトで透明な液体を手の甲へ垂らす場面が見えると、出し方も意外と想像しやすいかも✨",
                   "beauty_followup": "購入前にこういう使い方が動画で見えるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        transport = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                 schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
        sent = transport.call_args.args[1]["contents"][0]["parts"][0]["text"]
        for phrase in ("自分が使用した体験", "気に入ってる", "肌の調子がいい", "使いやすい",
                       "濃度", "配合量", "数字や商品名の意味を推測しない",
                       "スポイトから垂らす", "両方でquote全文を繰り返さない", "同じ長い表現を2段落で反復しない",
                       "公式サイト確認や文字列照合を目的にしない",
                       "1行44文字程度", "🥺✨🤍🫶🏻😭💭"):
            self.assertIn(phrase, sent)
        data = client.caption_candidate["public_post_text"]
        self.assertEqual(len(data.split("\n\n")), 3)
        self.assertIn("スポイト", data)
        self.assertNotIn("公式", data)
        from public_post_quality import voice_persona_validation
        self.assertEqual(voice_persona_validation(data, "beauty_account")["status"], "VOICE_PERSONA_PASS")

    def test_non_text_visual_fact_is_not_split_into_english_words(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "A dropper dispenses a clear liquid onto skin."}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "スポイトから透明な液体を肌へ垂らす場面が見えると、使う流れも意外と想像しやすいかも✨",
                   "beauty_followup": "購入前にこういう使い方が動画で見えるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                 schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
        public = client.caption_candidate["public_post_text"]
        self.assertIn(fact["text"], public)
        self.assertNotIn("この動画では、dispenses\n", public)

    def test_liver_prompt_requires_next_stream_action(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "配信中の入室通知は読み上げますか？ 枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0, "reader_takeaway": "次の配信では、今の枠の規模に合わせて入室通知を読むか読まないか決めて試してみてね。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
        transport = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                 schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
        sent = transport.call_args.args[1]["contents"][0]["parts"][0]["text"]
        self.assertIn("次の配信では", sent)
        self.assertIn("一つの具体行動", sent)
        self.assertIn("allowed_action_terms", sent)
        self.assertIn("入室通知", sent)
        self.assertIn("枠の規模", sent)
        self.assertIn("みんなで共有", sent)


    def test_liver_repairs_weak_self_directed_action_ending(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "枠の規模に合った運用って迷うよね、次の配信では枠の規模に合う運用を決めてみるかも😊"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            result = client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                          schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
        self.assertIn("決めてみてね😊", result["data"]["public_post_text"])
        self.assertNotIn("決めてみるかも", result["data"]["public_post_text"])

    def test_style_repair_rebinds_claim_support_to_final_text(self):
        result = {
            "public_post_text": "一段目💄\n\n二段目",
            "claim_support": [
                {"caption_claim": "一段目💄", "source_evidence": "一段目", "anchor_fact_ids": ["VF1"]},
                {"caption_claim": "二段目", "source_evidence": "二段目", "anchor_fact_ids": ["VF2"]},
            ],
            "internal_analysis": {"main_claims": ["一段目💄", "二段目"]},
        }
        rebound = rebind_style_repair_claims(result, "一段目💭\n\n二段目")
        self.assertEqual([x["caption_claim"] for x in rebound["claim_support"]], ["一段目💭", "二段目"])
        self.assertEqual(rebound["internal_analysis"]["main_claims"], ["一段目💭", "二段目"])

    def test_liver_rejects_source_person_as_viewer_action(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "一休さんに質問 配信中の入室通知は読み上げますか？ 枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0, "reader_takeaway": "次の配信では一休さんに質問してから通知を読むか決めて試してみてね。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "liver_source_person_contact_not_actionable"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
            self.assertEqual(client.caption_evidence.get("validation_error"),
                             "liver_source_person_contact_not_actionable")
            self.assertEqual(client.caption_candidate.get("selected_quote"),
                             "配信中の入室通知は読み上げますか？")
            self.assertIn("一休さんに質問", client.caption_candidate.get("reader_takeaway", ""))


    def test_liver_rejects_unobserved_reading_direction(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "配信中の入室通知は読み上げますか？ 枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "入室通知を読むか迷うよね。次の配信では入室通知の読み上げをやめて枠の規模に合わせて変えてみてね。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "liver_unobserved_direction_added"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")

    def test_beauty_rejects_unobserved_application_feel(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "スポイトから液体を手の甲に垂らす"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "スポイトから液体を手の甲に垂らす場面で、出す時の感覚が意外と分かるかも✨",
                   "beauty_followup": "ほんとに使い方を動画で見られるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "beauty_unobserved_physical_property"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")

    def test_beauty_rejects_unobserved_texture_language(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "スポイトから液体を手の甲に垂らす"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "スポイトで液体を手の甲へ垂らす場面を見ると、質感や一滴の重みまで分かる気がするかも✨",
                   "beauty_followup": "購入前に動画で出し方を見られるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        transport = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "beauty_unobserved_physical_property"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
        self.assertEqual(transport.call_count, 2)

    def test_beauty_uses_one_bounded_validation_repair(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "スポイトから透明な液体を手の甲に垂らす"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        rejected = {"quote_choice": 0,
                    "reader_takeaway": "スポイトで透明な液体を手の甲へ垂らす場面を見ると、質感まで分かる気がするかも✨",
                    "beauty_followup": "購入前に動画で出し方を見られるのって結構大事だよね🤍"}
        repaired = {"quote_choice": 0,
                    "reader_takeaway": "スポイトで透明な液体を手の甲へ垂らす動きが動画で見えると、意外と出し方を確認しやすいかも✨",
                    "beauty_followup": "購入前に手の甲への使い方を見られるのって、ほんとに結構大事だよね🤍"}
        responses = [
            {"candidates": [{"content": {"parts": [{"text": json.dumps(rejected, ensure_ascii=False)}]}}]},
            {"candidates": [{"content": {"parts": [{"text": json.dumps(repaired, ensure_ascii=False)}]}}]},
        ]
        transport = Mock(side_effect=responses)
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=transport, reserve_request=Mock(), cache_dir=Path(tmp))
            result = client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                          schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
        self.assertEqual(transport.call_count, 2)
        self.assertTrue(client.caption_evidence.get("validation_repair_used"))
        self.assertEqual(client.caption_evidence.get("validation_repair_reason"), "beauty_unobserved_physical_property")
        self.assertIn("購入前", result["data"]["public_post_text"])
        self.assertNotIn("質感", result["data"]["public_post_text"])

    def test_beauty_rejects_repeated_quote_after_observation(self):
        fact = {"id": "VF1", "type": "visible_action", "text": "スポイトから液体を手の甲に垂らす"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "スポイトから液体を手の甲に垂らすところ、動画だと意外と分かりやすいかも✨",
                   "beauty_followup": "スポイトから液体を手の甲に垂らすところを購入前に見られるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "beauty_quote_repeated_after_observation"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
            self.assertEqual(client.caption_evidence.get("validation_error"), "beauty_quote_repeated_after_observation")

    def test_liver_rejects_unbound_next_stream_metric(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "だから枠の規模に合った 運用が一番いいと思います!!"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "枠の規模に合った運用って迷うよね。次の配信ではリスナー数や反応の速さを見てルールを変えてみてね✨"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "liver_next_stream_action_not_source_specific"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
            self.assertEqual(client.caption_evidence.get("validation_error"),
                             "liver_next_stream_action_not_source_specific")


    def test_liver_rejects_unobserved_context(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "入室通知は読み上げますか？ 枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "リスナーが気を使うよね。次の配信では枠の規模に合う入室通知の設定を決めてみてね。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "liver_unobserved_context_added"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
            self.assertEqual(client.caption_evidence.get("validation_error"), "liver_unobserved_context_added")


    def test_liver_rejects_formal_polite_takeaway(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "入室通知は読み上げますか？ 枠の規模に合った運用が一番いいと思います"}
        source = {"target_account_id": "liver_manager", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "枠の規模に合う運用は迷いを整理してくれます。次の配信では入室通知を読むか決めてみてね。"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "liver_formal_polite_tone"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="liver_manager")
            self.assertEqual(client.caption_evidence.get("validation_error"), "liver_formal_polite_tone")

    def test_beauty_rejects_unverified_semantic_label(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "グリシルグリシン3.0"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "成分名グリシルグリシン3.0が公式にあるか意外と確認したいかも✨",
                   "beauty_followup": "グリシルグリシン3.0という数値を見比べるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "beauty_semantic_inference_unverified"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")
            self.assertEqual(client.caption_evidence.get("validation_error"),
                             "beauty_semantic_inference_unverified")

    def test_beauty_rejects_low_value_character_count_comparison(self):
        fact = {"id": "VF1", "type": "visible_text", "text": "グリシルグリシン3.0"}
        source = {"target_account_id": "beauty_account", "media_first_input": {
            "selected_post_angle": {"anchor_fact_ids": ["VF1"]}, "media_context": {"visual_facts": [fact]}}}
        payload = {"quote_choice": 0,
                   "reader_takeaway": "グリシルグリシン3.0をGlycylglycineと比べると意外と文字数が違うかも✨",
                   "beauty_followup": "グリシルグリシン3.0の文字数を見比べるのって結構大事だよね🤍"}
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = SmokeGeminiClient(api_key="fixture", transport=Mock(return_value=response), reserve_request=Mock(), cache_dir=Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "beauty_low_value_text_comparison"):
                client.generate_json(model="gemini-3.5-flash", prompt=json.dumps(source, ensure_ascii=False),
                                     schema={}, operation="direct_reference_caption_generation", account_id="beauty_account")

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
