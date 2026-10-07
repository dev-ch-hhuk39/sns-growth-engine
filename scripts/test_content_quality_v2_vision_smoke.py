#!/usr/bin/env python3
"""Fact-linked paraphrases, review-only rights separation and workflow isolation."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from generation import content_quality_v2 as quality  # noqa: E402
from test_media_first_pipeline import asset  # noqa: E402
from run_content_quality_v2_vision_smoke import smoke_previews, build_package, render, summary  # noqa: E402


from evidence_context_caption import PrivacyBoundedGeminiGroundedProvider  # noqa: E402


class VisionSmokeTests(unittest.TestCase):
    def context(self):
        row = asset()
        row["visible_action"] = "配信者が初見の名前を呼んでいる"
        ctx = quality.prepare_media_context(row, account_id="liver_manager")
        angle = quality.select_media_angles(ctx, quality.evaluate_media_relevance(ctx, {"audience": "配信初心者"}))["selected"]
        return ctx, angle

    def test_natural_paraphrase_without_visual_description_copy(self):
        ctx, angle = self.context()
        fact = next(f for f in ctx["visual_facts"] if f["type"] == "visible_action")
        claim = "名前を呼ぶだけでも自分に気づいてくれたって伝わりやすい"
        text = "初見さんが入ってきた時、" + claim + "☺️\n次の配信では、入室に気づいたらまず名前＋一言から試してみてもいいかも。"
        result = quality.remove_media_test(text, ctx, angle, [{
            "caption_claim": claim, "source_evidence": fact["text"], "anchor_fact_ids": [fact["id"]]}])
        self.assertEqual(result["status"], "PASS", result)
        self.assertNotIn(fact["text"], text)
        self.assertNotIn(ctx["key_moment"], text)

    def test_generic_caption_and_fake_fact_ids_rejected(self):
        ctx, angle = self.context()
        generic = "初見を大切にすると配信は伸びやすい。次回も頑張ろう。"
        self.assertEqual(quality.remove_media_test(generic, ctx, angle)["generic_caption_risk"], "HIGH")
        support = [{"caption_claim": generic, "source_evidence": ctx["visible_action"], "anchor_fact_ids": ["VF_FAKE"]}]
        self.assertEqual(quality.remove_media_test(generic, ctx, angle, support)["status"], "GENERIC_CAPTION_RISK_HIGH")

    def test_gemini_top_level_action_and_key_moment_are_preserved_as_facts(self):
        row = asset()
        row["visible_action"] = "スポイトから透明な液体を手の甲に垂らす"
        row["key_moment"] = "透明な液体が手の甲に落ちる瞬間"
        row["visible_text"] = "商品名"
        row["visual_facts"] = [{"id": "VF_TEXT", "type": "visible_text", "text": "商品名"}]
        row["visual_evidence"] = {**row["visual_evidence"], "provider": "gemini"}
        row["http_status"] = 200
        row["response_schema_status"] = "PASS"
        ctx = quality.prepare_media_context(row, account_id="liver_manager")
        by_type = {fact["type"]: fact["text"] for fact in ctx["visual_facts"]}
        self.assertEqual(by_type["visible_action"], row["visible_action"])
        self.assertEqual(by_type["key_moment"], row["key_moment"])
        self.assertEqual(by_type["visible_text"], "商品名")

    def test_fact_ids_stable_and_asset_bound(self):
        ctx, _ = self.context()
        again, _ = self.context()
        self.assertEqual(ctx["visual_facts"], again["visual_facts"])
        changed = asset()
        changed["content_hash"] = "other"
        self.assertEqual(quality.prepare_media_context(changed, account_id="liver_manager")["visual_facts"], [])

    def test_review_does_not_grant_publish_permission(self):
        row = asset()
        row.update(rights_status="unknown", permission_status="unverified", permission_evidence="")
        original = copy.deepcopy(row)
        generator = Mock(return_value={"status": "BLOCKED", "public_post_text": ""})
        args = dict(media=row, account_id="liver_manager", account_content_contract={"audience": "配信初心者"},
                    recent_posts=[], caption_generator=generator)
        production = quality.generate_media_first_caption(**args)
        generator.assert_not_called()
        draft = quality.generate_media_first_caption(**args, editorial_draft=True)
        generator.assert_called_once()
        self.assertEqual(draft["editorial_draft_eligibility"]["status"], "PASS")
        self.assertEqual(draft["publish_eligibility"]["status"], "BLOCKED")
        self.assertFalse(draft["would_post"])
        self.assertFalse(production["MEDIA_SUCCESS"])
        self.assertEqual(row, original)

    def test_unclear_relevance_makes_no_caption_request(self):
        row = smoke_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text())[0]
        inspected = {"status": "PREVIEW_READ_OK", "content_hash": "a" * 64,
                     "frames": [{"sha256": "b" * 64}],
                     "vision": {"status": "PASS", "visual_summary": "人物の映像", "visible_people_or_objects": "人物",
                                "visible_action": "人物が箱を開けて見せている", "key_moment": "机の上の場面",
                                "main_topic": "開封", "account_relevance_review": {"status": "RELEVANCE_UNVERIFIED"}}}
        with patch("run_content_quality_v2_vision_smoke.inspect_preview", return_value=inspected), \
             patch("run_content_quality_v2_vision_smoke.SourceGroundedCaptionService") as service:
            package = build_package(row, Path("/tmp/not-written"))
        service.return_value.generate_media_context.assert_not_called()
        self.assertEqual(package["result"]["public_post_text"], "")
        self.assertIn("RELEVANCE_UNVERIFIED", render([package]))

    def test_unrelated_claim_cannot_use_real_fact_id(self):
        ctx, angle = self.context()
        fact = next(f for f in ctx["visual_facts"] if f["type"] == "visible_action")
        text = "初見を大切にすると配信は伸びやすい。次回も頑張ろう。"
        result = quality.remove_media_test(text, ctx, angle, [{
            "caption_claim": text, "source_evidence": fact["text"], "anchor_fact_ids": [fact["id"]]}])
        self.assertEqual(result["generic_caption_risk"], "HIGH")
        for malformed in ([None], [{"anchor_fact_ids": [{}]}], None):
            self.assertEqual(quality.remove_media_test(text, ctx, angle, malformed)["generic_caption_risk"], "HIGH")

    def test_no_fallback_counts_as_real_ai_proof(self):
        package = {"vision": {"status": "PASS"}, "result": {
            "status": "PASS", "public_post_text": "fixture", "provider_name": "deterministic_local_strict",
            "provider_status": "PASS", "remove_media_test": {"status": "PASS", "generic_caption_risk": "LOW"},
            "fabricated_experience_check": {"status": "PASS"}}}
        self.assertEqual(summary([package] * 3)["VERIFIED_MEDIA_PACKAGE_COUNT"], 0)
        package["result"]["provider_name"] = PrivacyBoundedGeminiGroundedProvider.provider_name
        self.assertEqual(summary([package] * 3)["VERIFIED_MEDIA_PACKAGE_COUNT"], 3)
        package["result"]["fabricated_experience_check"]["status"] = "BLOCKED"
        self.assertEqual(summary([package] * 3)["VERIFIED_MEDIA_PACKAGE_COUNT"], 0)

    def test_workflow_smoke_isolation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/direct-media-preparation.yml").read_text())
        jobs = workflow["jobs"]
        for name, job in jobs.items():
            if name == "content-quality-v2-vision-smoke":
                self.assertNotIn("environment", job)
                import re
                self.assertEqual(re.findall(r"secrets\.([A-Z_]+)", json.dumps(job)), ["GEMINI_API_KEY"])
                self.assertEqual(job["env"]["GEMINI_API_KEY"], "${{ secrets.GEMINI_API_KEY }}")
                self.assertNotIn("GITHUB_TOKEN", job["env"])
                self.assertNotIn("GITHUB_MODELS_ENABLED", job["env"])
                self.assertEqual(job["permissions"], {"contents": "read"})
                self.assertNotIn("--apply", json.dumps(job))
                for step in job["steps"]:
                    if "upload-artifact" in step.get("uses", ""):
                        self.assertTrue(step["with"]["path"].endswith(".md"))
            else:
                self.assertIn("content_quality_v2_vision_smoke != 'true'", job["if"])
        selected = smoke_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text())
        self.assertEqual(len(selected), 3)
        self.assertEqual({row["account_id"] for row in selected}, quality.ACCOUNTS)


if __name__ == "__main__":
    unittest.main()
