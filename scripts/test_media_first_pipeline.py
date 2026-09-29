#!/usr/bin/env python3
"""Offline behavioral tests of the real Direct/Clip caption entry points."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from generation import content_quality_v2 as quality  # noqa: E402
from generation.source_grounded_caption import SourceGroundedCaptionService  # noqa: E402
import run_direct_reference_media_pipeline as direct  # noqa: E402
import run_media_production_pipeline as clip_pipeline  # noqa: E402
from build_media_first_review_pack import selected_previews  # noqa: E402


def asset(account="liver_manager"):
    action = {"night_scout": "接客中に注文を復唱してからグラスを並べている",
              "liver_manager": "配信者が初見の名前を呼んでコメント欄を指している",
              "beauty_account": "リップを手の甲に三本並べて色の違いを見せている"}[account]
    return {"account_id": account, "target_account_id": account, "media_asset_id": "asset1",
            "source_id": "source1", "source_post_id": "post1", "media_type": "video",
            "storage_url": "https://example.invalid/asset.mp4", "duration_seconds": 12,
            "width": 720, "height": 1280, "rights_status": "owned", "permission_status": "approved",
            "permission_evidence": "fixture-owner-permission", "technical_status": "PASS", "content_hash": "a" * 64,
            "vision_status": "PASS", "visual_summary": action, "visible_action": action,
            "key_moment": "開始直後に青いカードを持ち上げた場面", "main_topic": "具体例",
            "visual_evidence": {"status": "UNDERSTOOD", "frame_hashes": ["b" * 64], "provider": "fixture",
                                "content_hash": "a" * 64, "media_asset_id": "asset1"}}


def source(account="liver_manager"):
    return {"source_id": "source1", "source_post_id": "post1", "source_video_id": "video1",
            "target_account_id": account, "platform": "youtube", "external_post_id": "abcdefghijk",
            "canonical_post_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "original_post_text": "Historical text must not drive generation.", "title": "説明",
            "rights_status": "owned", "permission_status": "approved"}


def caption(row):
    return f"この動画では{row['key_moment']}、{row['visible_action']}。一度立ち止まって相手の反応を見ているところも、慌てずに伝えるための具体例として見たいね。"


class MediaFirstTests(unittest.TestCase):
    def invoke(self, row=None, generator=None):
        row = row or asset()
        return quality.generate_media_first_caption(
            media=row, account_id=row["account_id"], account_content_contract={"audience": "読者"},
            recent_posts=[], caption_generator=generator or (lambda **kw: {"status": "PASS", "public_post_text": caption(row)}))

    def assert_order(self, route):
        row = asset()
        events = []
        originals = {name: getattr(quality, name) for name in (
            "prepare_media_context", "evaluate_media_relevance", "select_media_angles")}
        def recorder(name):
            def call(*args, **kwargs):
                events.append(name)
                return originals[name](*args, **kwargs)
            return call
        service = Mock()
        def generate(_bundle, **request):
            events.append("caption")
            self.assertEqual(request["media_context"]["visual_status"], "VISUAL_VERIFIED")
            self.assertTrue(request["selected_post_angle"])
            self.assertTrue(request["account_content_contract"])
            self.assertEqual(request["recent_posts"], ["recent"])
            return {"status": "PASS", "public_post_text": caption(row), "blocked_reasons": [],
                    "semantic_alignment": {"status": "PASS"}}
        service.generate_media_context.side_effect = generate
        with patch.object(quality, "prepare_media_context", side_effect=recorder("prepare_media_context")), \
             patch.object(quality, "evaluate_media_relevance", side_effect=recorder("evaluate_media_relevance")), \
             patch.object(quality, "select_media_angles", side_effect=recorder("select_media_angles")):
            if route == "direct":
                result = direct._generate_direct_media_caption(post=source(), media=row,
                    bundle=direct.build_source_post_bundle(source(), [row]), account_id="liver_manager",
                    recent_posts=["recent"], caption_service=service)
            else:
                with patch.object(clip_pipeline, "final_public_post_validator", return_value={"status": "PASS", "blocked_reasons": []}):
                    result = clip_pipeline._generate_final_media_caption(
                        clip={"account_id": "liver_manager", "clip_candidate_id": "clip1", "start_seconds": 10,
                              "end_seconds": 22, "transcript_excerpt": "", "source_video_id": "video1"},
                        source_video=source(), media_asset=row, account_id="liver_manager",
                        recent_posts=["recent"], caption_service=service)
        self.assertEqual(events, ["prepare_media_context", "evaluate_media_relevance", "select_media_angles", "caption"])
        self.assertEqual(result["status"], "PASS", result)

    def test_direct_call_order(self):
        self.assert_order("direct")

    def test_clip_call_order(self):
        self.assert_order("clip")

    def test_transcript_does_not_verify_visuals(self):
        row = asset()
        row.pop("visual_evidence")
        row.update(transcript_status="PASS", transcript_text="実際に発話した内容")
        generator = Mock()
        result = self.invoke(row, generator)
        self.assertEqual(result["media_context"]["visual_status"], "VISUAL_UNVERIFIED")
        generator.assert_not_called()

    def test_frame_extraction_is_not_understanding(self):
        row = asset()
        row["visual_evidence"]["status"] = "EXTRACTED_ONLY"
        self.assertEqual(self.invoke(row)["status"], "REVIEW_REQUIRED")

    def test_foreign_asset_evidence_rejected(self):
        row = asset()
        row["visual_evidence"]["media_asset_id"] = "another_asset"
        self.assertEqual(self.invoke(row)["status"], "REVIEW_REQUIRED")

    def test_stale_hash_evidence_rejected(self):
        row = asset()
        row["content_hash"] = "changed"
        self.assertEqual(self.invoke(row)["status"], "REVIEW_REQUIRED")

    def test_generic_caption_is_degraded(self):
        result = self.invoke(generator=lambda **kw: {"status": "PASS", "public_post_text": "初見への配信コメント対応は大事。自分のペースで頑張ろう。"})
        self.assertEqual(result["remove_media_test"]["generic_caption_risk"], "HIGH")
        self.assertEqual(result["route_status"], "DEGRADED_TO_TEXT")
        self.assertFalse(result["MEDIA_SUCCESS"])

    def test_generic_topic_does_not_establish_relevance(self):
        row = asset()
        row.update(visible_action="ライブ関連", key_moment="関連動画")
        generator = Mock()
        self.invoke(row, generator)
        generator.assert_not_called()

    def test_attribution_elsewhere_does_not_allow_own_experience(self):
        result = quality.fabricated_media_experience("投稿者の説明を見た。私も一週間使って肌が変わった。")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(quality.fabricated_media_experience("投稿者は一週間使ったと話している。")['status'], "PASS")

    def test_rights_and_permission_are_hard(self):
        for update in ({"rights_status": "reference_only"}, {"permission_status": "denied"}, {"permission_evidence": ""}):
            generator = Mock()
            self.assertEqual(self.invoke({**asset(), **update}, generator)["status"], "REVIEW_REQUIRED")
            generator.assert_not_called()

    def test_technical_validity_is_hard(self):
        self.assertEqual(self.invoke({**asset(), "technical_status": "UNVERIFIED"})["status"], "REVIEW_REQUIRED")

    def test_all_accounts_isolated(self):
        for account in sorted(quality.ACCOUNTS):
            for other in sorted(quality.ACCOUNTS - {account}):
                row = asset(account)
                row["target_account_id"] = other
                self.assertEqual(self.invoke(row)["status"], "REVIEW_REQUIRED")
            self.assertEqual(self.invoke(asset(account))["status"], "PASS")

    def test_no_draft_writes_for_unverified_direct_candidate(self):
        client = Mock()
        with patch.object(direct, "_records", return_value=[]), \
             patch.object(direct, "select_direct_candidates", return_value=([(source(), {**asset(), "visual_evidence": {}}, {})], [])), \
             patch.object(direct, "_permission_map", return_value=({}, [])):
            result = direct.build_plan("liver_manager", "", client, apply=False, manual_e2e_proof=True)
        self.assertFalse(result["would_post"])
        self.assertEqual(client.mock_calls, [])
        self.assertFalse(quality.load_policy()["publishing_enabled"])

    def test_text_fallback_is_not_media_success(self):
        fallback = quality.select_media_or_text_fallback([], [
            {"account_id": "liver_manager", "hard_gate_status": "PASS", "public_post_text": "読者向けの新規本文"}], account_id="liver_manager")
        self.assertEqual(fallback["route_status"], "DEGRADED_TO_TEXT")
        self.assertFalse(fallback["media_counted_as_success"])

    def test_caption_service_receives_verified_context_not_historical_text(self):
        row = asset()
        context = quality.prepare_media_context(row, account_id="liver_manager")
        angle = quality.select_media_angles(context, quality.evaluate_media_relevance(context, {"audience": "読者"}))["selected"]
        service = SourceGroundedCaptionService(Mock(), allow_deterministic_fallback=False)
        bundle = direct.build_source_post_bundle(source(), [row])
        with patch.object(service, "generate", return_value={"status": "PASS"}) as generate:
            service.generate_media_context(bundle, media_context=context, selected_post_angle=angle,
                                           account_content_contract={"audience": "読者"}, recent_posts=[])
        sent_bundle = generate.call_args.args[0]
        self.assertNotIn("Historical text", sent_bundle.original_post_text)
        self.assertIn(row["visible_action"], sent_bundle.original_post_text)
        self.assertIn('"media_context"', generate.call_args.kwargs["transcript_excerpt"])

    def test_review_pack_limit_and_non_fabrication(self):
        previews = selected_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text())
        self.assertEqual(len(previews), 6)
        for account in quality.ACCOUNTS:
            self.assertEqual(sum(row["account_id"] == account for row in previews), 2)


if __name__ == "__main__":
    unittest.main()
