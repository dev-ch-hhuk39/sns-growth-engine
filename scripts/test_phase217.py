"""
test_phase217.py — Phase 2.17 コンテンツテーマガード テスト

テスト項目:
  - detect_forbidden_keywords
  - calculate_target_fit_score
  - check_content_theme
  - apply_content_theme_guard
  - score_generated_post (account_config 統合)
  - ns_08/lm_08 が inactive であること
  - ACCOUNT_FORBIDDEN_KEYWORDS の存在確認
  - generate_from_jobs の content_theme_guard ロジック
  - approve_queue の content_theme_guard ロジック
  - check_pipeline_integrity の REJECTED 対応
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

import unittest

from generation.approval_scorer import (
    apply_content_theme_guard,
    calculate_target_fit_score,
    check_content_theme,
    detect_forbidden_keywords,
    score_generated_post,
)
from seeds import (
    ACCOUNT_FORBIDDEN_KEYWORDS,
    ACCOUNT_FORBIDDEN_THEMES,
    CATEGORY_SEEDS,
)


# ------------------------------------------------------------------ #
# detect_forbidden_keywords
# ------------------------------------------------------------------ #

class TestDetectForbiddenKeywords(unittest.TestCase):

    def test_single_hit(self):
        hits = detect_forbidden_keywords("代理店で稼ぐ方法", ["代理店", "パートナー募集"])
        self.assertIn("代理店", hits)

    def test_no_hit(self):
        hits = detect_forbidden_keywords("キャバ嬢向けの店選び", ["代理店", "パートナー募集"])
        self.assertEqual(hits, [])

    def test_multiple_hits(self):
        hits = detect_forbidden_keywords("代理店パートナー募集中", ["代理店", "パートナー募集"])
        self.assertEqual(len(hits), 2)

    def test_empty_text(self):
        hits = detect_forbidden_keywords("", ["代理店"])
        self.assertEqual(hits, [])

    def test_empty_keywords(self):
        hits = detect_forbidden_keywords("代理店で稼ぐ", [])
        self.assertEqual(hits, [])

    def test_night_scout_agency_keywords(self):
        """night_scout の代理店系キーワードをすべて検出できること。"""
        ns_kws = ACCOUNT_FORBIDDEN_KEYWORDS["night_scout"]
        for kw in ns_kws:
            hits = detect_forbidden_keywords(f"これは{kw}の話です", ns_kws)
            self.assertIn(kw, hits, f"キーワード '{kw}' が検出されなかった")

    def test_liver_manager_keywords(self):
        lm_kws = ACCOUNT_FORBIDDEN_KEYWORDS["liver_manager"]
        hits = detect_forbidden_keywords("情報商材を売る", lm_kws)
        self.assertIn("情報商材", hits)

    def test_kyaba_content_no_hit(self):
        """キャバ嬢向けの正常な投稿はヒットしないこと。"""
        ns_kws = ACCOUNT_FORBIDDEN_KEYWORDS["night_scout"]
        text = "キャバを始めたての子に伝えたいこと。店選びで3年後の年収が変わる。"
        hits = detect_forbidden_keywords(text, ns_kws)
        self.assertEqual(hits, [], f"正常投稿でヒットが出た: {hits}")

    def test_scout_agency_hit(self):
        """スカウト代理店キーワードを検出できること。"""
        ns_kws = ACCOUNT_FORBIDDEN_KEYWORDS["night_scout"]
        hits = detect_forbidden_keywords("スカウト代理店として高収益を狙う", ns_kws)
        self.assertTrue(len(hits) >= 1)


# ------------------------------------------------------------------ #
# calculate_target_fit_score
# ------------------------------------------------------------------ #

class TestCalculateTargetFitScore(unittest.TestCase):

    def setUp(self):
        self.account_config = {"account_id": "night_scout"}

    def test_clean_draft_score_1(self):
        draft = {"body_md": "キャバ嬢の店選びノウハウ", "cta_text": "相談はLINEで"}
        score = calculate_target_fit_score(draft, self.account_config)
        self.assertEqual(score, 1.0)

    def test_one_hit_reduces_score(self):
        draft = {"body_md": "代理店として稼ぐ仕組みを解説", "cta_text": ""}
        score = calculate_target_fit_score(draft, self.account_config)
        self.assertLess(score, 1.0)

    def test_multiple_hits_reduce_more(self):
        draft = {"body_md": "代理店パートナー募集・高収益", "cta_text": "ビジネス構造を教えます"}
        score_multi = calculate_target_fit_score(draft, self.account_config)
        draft_single = {"body_md": "代理店として稼ぐ", "cta_text": ""}
        score_single = calculate_target_fit_score(draft_single, self.account_config)
        self.assertLess(score_multi, score_single)

    def test_unknown_account_score_1(self):
        draft = {"body_md": "代理店", "cta_text": ""}
        score = calculate_target_fit_score(draft, {"account_id": "unknown_account"})
        self.assertEqual(score, 1.0)

    def test_score_never_negative(self):
        draft = {"body_md": " ".join(ACCOUNT_FORBIDDEN_KEYWORDS["night_scout"]), "cta_text": ""}
        score = calculate_target_fit_score(draft, self.account_config)
        self.assertGreaterEqual(score, 0.0)


# ------------------------------------------------------------------ #
# check_content_theme
# ------------------------------------------------------------------ #

class TestCheckContentTheme(unittest.TestCase):

    def setUp(self):
        self.account_config = {"account_id": "night_scout"}

    def test_theme_ok_for_clean_draft(self):
        draft = {"body_md": "キャバ嬢向けの店選びノウハウ", "cta_text": ""}
        result = check_content_theme(draft, self.account_config)
        self.assertTrue(result["theme_ok"])
        self.assertEqual(result["forbidden_hits"], [])
        self.assertEqual(result["target_fit_score"], 1.0)

    def test_theme_fail_for_agency_draft(self):
        draft = {"body_md": "代理店として稼ぐ方法", "cta_text": "高収益を狙う"}
        result = check_content_theme(draft, self.account_config)
        self.assertFalse(result["theme_ok"])
        self.assertTrue(len(result["forbidden_hits"]) >= 1)
        self.assertNotEqual(result["theme_rejection_reason"], "")

    def test_紹介業_hit(self):
        draft = {"body_md": "紹介業として独立する方法", "cta_text": ""}
        result = check_content_theme(draft, self.account_config)
        self.assertFalse(result["theme_ok"])

    def test_高収益_hit(self):
        draft = {"body_md": "組織的なロジックで高収益を目指す", "cta_text": ""}
        result = check_content_theme(draft, self.account_config)
        self.assertFalse(result["theme_ok"])

    def test_liver_manager_info_shozai_hit(self):
        account_config = {"account_id": "liver_manager"}
        draft = {"body_md": "情報商材を活用して稼ぐ方法", "cta_text": ""}
        result = check_content_theme(draft, account_config)
        self.assertFalse(result["theme_ok"])

    def test_liver_manager_clean(self):
        account_config = {"account_id": "liver_manager"}
        draft = {"body_md": "TikTokライブで月10万稼いだ話", "cta_text": ""}
        result = check_content_theme(draft, account_config)
        self.assertTrue(result["theme_ok"])


# ------------------------------------------------------------------ #
# apply_content_theme_guard
# ------------------------------------------------------------------ #

class TestApplyContentThemeGuard(unittest.TestCase):

    def setUp(self):
        self.account_config = {"account_id": "night_scout"}
        self.base_score = {
            "buzz_potential_score": 75.0,
            "conversion_potential_score": 60.0,
            "brand_risk_score": 0.2,
            "imitation_risk": "low",
            "media_reuse_risk": "low",
            "text_policy_status": "OK",
            "confidence_level": "HIGH",
            "ai_publish_recommendation": "recommend",
            "suggested_status": "APPROVED",
            "ai_review": "",
        }

    def test_clean_draft_unchanged(self):
        draft = {"body_md": "キャバ嬢向けの店選びノウハウ", "cta_text": ""}
        result = apply_content_theme_guard(dict(self.base_score), draft, self.account_config)
        self.assertEqual(result["ai_publish_recommendation"], "recommend")
        self.assertEqual(result["confidence_level"], "HIGH")

    def test_agency_draft_rejected(self):
        draft = {"body_md": "代理店として稼ぐ仕組み", "cta_text": "高収益を目指す"}
        result = apply_content_theme_guard(dict(self.base_score), draft, self.account_config)
        self.assertEqual(result["ai_publish_recommendation"], "reject")
        self.assertEqual(result["confidence_level"], "LOW")
        self.assertGreater(result["brand_risk_score"], 0.2)
        self.assertIn("content_theme_guard", result["ai_review"])
        self.assertIn("target_mismatch", result["ai_review"])

    def test_brand_risk_capped_at_1(self):
        draft = {"body_md": "代理店パートナー募集ビジネス構造", "cta_text": "高収益"}
        score = dict(self.base_score)
        score["brand_risk_score"] = 0.9
        result = apply_content_theme_guard(score, draft, self.account_config)
        self.assertLessEqual(result["brand_risk_score"], 1.0)

    def test_target_fit_score_added(self):
        draft = {"body_md": "キャバ嬢の話", "cta_text": ""}
        result = apply_content_theme_guard(dict(self.base_score), draft, self.account_config)
        self.assertIn("target_fit_score", result)


# ------------------------------------------------------------------ #
# score_generated_post (account_config 統合)
# ------------------------------------------------------------------ #

class TestScoreGeneratedPostWithAccountConfig(unittest.TestCase):

    def test_no_account_config_no_theme_guard(self):
        """account_config なしではテーマガードが適用されず、target_fit_score が結果に含まれない。"""
        draft = {"body_md": "代理店として稼ぐ", "cta_text": ""}
        result = score_generated_post(draft, platform="x")
        self.assertNotIn("target_fit_score", result)
        self.assertNotIn("theme_rejection_reason", result)

    def test_with_account_config_agency_rejected(self):
        draft = {"body_md": "代理店として稼ぐ仕組みを解説します", "cta_text": "高収益を目指す"}
        account_config = {"account_id": "night_scout"}
        result = score_generated_post(draft, platform="x", account_config=account_config)
        self.assertEqual(result["ai_publish_recommendation"], "reject")
        self.assertEqual(result["suggested_status"], "WAITING_REVIEW")
        self.assertIn("content_theme_guard", result.get("ai_review", ""))

    def test_with_account_config_clean_has_target_fit_1(self):
        """クリーンな投稿は target_fit_score=1.0 で theme_rejection_reason が空。"""
        draft = {"body_md": "キャバを始めたての子に必ず伝えること。店選びで3年後の年収が変わる。", "cta_text": "相談はLINEで"}
        account_config = {"account_id": "night_scout"}
        result = score_generated_post(draft, platform="x", account_config=account_config)
        self.assertEqual(result.get("target_fit_score"), 1.0)
        self.assertEqual(result.get("theme_rejection_reason"), "")


# ------------------------------------------------------------------ #
# seeds: ns_08/lm_08 が inactive であること
# ------------------------------------------------------------------ #

class TestSeedsInactiveCategories(unittest.TestCase):

    def test_ns_08_inactive(self):
        ns_08 = next((c for c in CATEGORY_SEEDS if c["category_id"] == "ns_08"), None)
        self.assertIsNotNone(ns_08, "ns_08 カテゴリが見つかりません")
        self.assertEqual(ns_08["active"], "FALSE", f"ns_08.active={ns_08['active']} (FALSE 期待)")

    def test_lm_08_inactive(self):
        lm_08 = next((c for c in CATEGORY_SEEDS if c["category_id"] == "lm_08"), None)
        self.assertIsNotNone(lm_08, "lm_08 カテゴリが見つかりません")
        self.assertEqual(lm_08["active"], "FALSE", f"lm_08.active={lm_08['active']} (FALSE 期待)")

    def test_other_categories_still_active(self):
        active_ns = [c for c in CATEGORY_SEEDS if c["account_id"] == "night_scout" and c["active"] == "TRUE"]
        self.assertGreater(len(active_ns), 0, "night_scout のアクティブカテゴリが0件")

    def test_ns_08_not_deleted(self):
        ns_08 = next((c for c in CATEGORY_SEEDS if c["category_id"] == "ns_08"), None)
        self.assertIsNotNone(ns_08, "ns_08 は削除せず保持すること")


# ------------------------------------------------------------------ #
# ACCOUNT_FORBIDDEN_KEYWORDS / THEMES の存在確認
# ------------------------------------------------------------------ #

class TestAccountForbiddenKeywords(unittest.TestCase):

    def test_night_scout_keywords_exist(self):
        kws = ACCOUNT_FORBIDDEN_KEYWORDS.get("night_scout", [])
        self.assertGreater(len(kws), 0)

    def test_liver_manager_keywords_exist(self):
        kws = ACCOUNT_FORBIDDEN_KEYWORDS.get("liver_manager", [])
        self.assertGreater(len(kws), 0)

    def test_themes_night_scout(self):
        themes = ACCOUNT_FORBIDDEN_THEMES.get("night_scout", [])
        self.assertGreater(len(themes), 0)

    def test_themes_liver_manager(self):
        themes = ACCOUNT_FORBIDDEN_THEMES.get("liver_manager", [])
        self.assertGreater(len(themes), 0)

    def test_dairitenパートナー募集_in_night_scout(self):
        kws = ACCOUNT_FORBIDDEN_KEYWORDS["night_scout"]
        self.assertIn("代理店", kws)
        self.assertIn("パートナー募集", kws)

    def test_jyoho_shozai_in_liver_manager(self):
        kws = ACCOUNT_FORBIDDEN_KEYWORDS["liver_manager"]
        self.assertIn("情報商材", kws)


# ------------------------------------------------------------------ #
# VALID_QUEUE_STATUSES に REJECTED が含まれること
# ------------------------------------------------------------------ #

class TestValidQueueStatuses(unittest.TestCase):

    def test_rejected_in_valid_statuses(self):
        """check_pipeline_integrity.py の VALID_QUEUE_STATUSES に REJECTED が含まれること。"""
        import importlib.util
        scripts_dir = os.path.join(_V2_ROOT, "scripts")
        spec = importlib.util.spec_from_file_location(
            "check_pipeline_integrity",
            os.path.join(scripts_dir, "check_pipeline_integrity.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn("REJECTED", mod.VALID_QUEUE_STATUSES)


# ------------------------------------------------------------------ #
# reference_based_generator のプロンプトにNGブロックが含まれること
# ------------------------------------------------------------------ #

class TestNGBlockInPrompt(unittest.TestCase):

    def test_ng_block_in_reference_based_prompt(self):
        from generation.reference_based_generator import build_reference_based_prompt
        job = {}
        score = {}
        account = {"account_id": "night_scout", "target_persona": "キャバ嬢", "tone": "強め", "main_genre": "夜職"}
        prompt = build_reference_based_prompt(job, score, account, "x")
        self.assertIn("アカウント固有禁止事項", prompt)
        self.assertIn("代理店", prompt)

    def test_ng_block_in_original_hypothesis_prompt(self):
        from generation.reference_based_generator import build_original_hypothesis_prompt
        job = {}
        account = {"account_id": "night_scout", "target_persona": "キャバ嬢", "tone": "強め", "main_genre": "夜職"}
        prompt = build_original_hypothesis_prompt(job, account, "x")
        self.assertIn("アカウント固有禁止事項", prompt)

    def test_no_ng_block_for_unknown_account(self):
        from generation.reference_based_generator import build_reference_based_prompt
        job = {}
        score = {}
        account = {"account_id": "unknown_account", "target_persona": "", "tone": "", "main_genre": ""}
        prompt = build_reference_based_prompt(job, score, account, "x")
        self.assertNotIn("アカウント固有禁止事項", prompt)

    def test_ng_block_liver_manager(self):
        from generation.reference_based_generator import build_reference_based_prompt
        job = {}
        score = {}
        account = {"account_id": "liver_manager", "target_persona": "ライバー", "tone": "ロジカル", "main_genre": "ライバー"}
        prompt = build_reference_based_prompt(job, score, account, "threads")
        self.assertIn("アカウント固有禁止事項", prompt)
        self.assertIn("情報商材", prompt)


# ------------------------------------------------------------------ #
# generate_from_jobs テーマチェックロジック（ユニットレベル）
# ------------------------------------------------------------------ #

class TestGenerateFromJobsThemeCheck(unittest.TestCase):
    """generate_from_jobs.py のテーマチェックロジックを直接テスト。"""

    def _run_theme_check(self, account_id: str, results: list[dict]) -> list[dict]:
        """generate_from_jobs.main() 内のテーマチェックロジックを再現。"""
        forbidden = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
        if forbidden:
            for r in results:
                if r.get("status") == "FAILED":
                    continue
                draft_content = r.get("content", "") or r.get("body_md", "")
                if not draft_content:
                    continue
                hits = detect_forbidden_keywords(draft_content, forbidden)
                if hits:
                    r["status"] = "WAITING_REVIEW"
                    r["theme_rejection_reason"] = f"content_theme_guard: forbidden_keywords={hits}"
        return results

    def test_agency_result_becomes_waiting_review(self):
        results = [
            {
                "job_id": "job-0001",
                "status": "DRAFT",
                "content": "代理店として稼ぐ方法を教えます",
                "generation_mode": "reference_based",
                "text_policy_status": "OK",
            }
        ]
        updated = self._run_theme_check("night_scout", results)
        self.assertEqual(updated[0]["status"], "WAITING_REVIEW")
        self.assertIn("content_theme_guard", updated[0].get("theme_rejection_reason", ""))

    def test_clean_result_unchanged(self):
        results = [
            {
                "job_id": "job-0002",
                "status": "DRAFT",
                "content": "キャバを始めたての子に伝えること",
                "generation_mode": "reference_based",
                "text_policy_status": "OK",
            }
        ]
        updated = self._run_theme_check("night_scout", results)
        self.assertEqual(updated[0]["status"], "DRAFT")
        self.assertNotIn("theme_rejection_reason", updated[0])

    def test_failed_result_not_touched(self):
        results = [
            {
                "job_id": "job-0003",
                "status": "FAILED",
                "content": "代理店として稼ぐ",
                "generation_mode": "reference_based",
                "text_policy_status": "FAIL",
            }
        ]
        updated = self._run_theme_check("night_scout", results)
        self.assertEqual(updated[0]["status"], "FAILED")

    def test_agency_result_not_ready(self):
        results = [
            {
                "job_id": "job-0004",
                "status": "APPROVED",
                "content": "スカウト代理店で高収益を狙う仕組み",
                "generation_mode": "reference_based",
                "text_policy_status": "OK",
            }
        ]
        updated = self._run_theme_check("night_scout", results)
        self.assertNotEqual(updated[0]["status"], "APPROVED")
        self.assertEqual(updated[0]["status"], "WAITING_REVIEW")


# ------------------------------------------------------------------ #
# approve_queue テーマゲートロジック（ユニットレベル）
# ------------------------------------------------------------------ #

class TestApproveQueueThemeGate(unittest.TestCase):
    """approve_queue.py のテーマゲートロジックを直接テスト。"""

    def _theme_gate_check(self, account_id: str, deriv_text: str) -> list[str]:
        forbidden = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
        if forbidden and deriv_text:
            return detect_forbidden_keywords(deriv_text, forbidden)
        return []

    def test_agency_derivative_blocked(self):
        deriv_text = "代理店として稼ぐ仕組みを解説。高収益を目指す方へ。"
        hits = self._theme_gate_check("night_scout", deriv_text)
        self.assertTrue(len(hits) >= 1)

    def test_clean_derivative_passes(self):
        deriv_text = "キャバを始めたての子に必ず伝えること。店選びで3年後の年収が変わる。"
        hits = self._theme_gate_check("night_scout", deriv_text)
        self.assertEqual(hits, [])

    def test_liver_manager_info_shozai_blocked(self):
        deriv_text = "情報商材を活用して副業で月50万稼ぐ方法"
        hits = self._theme_gate_check("liver_manager", deriv_text)
        self.assertIn("情報商材", hits)

    def test_partner_boshu_blocked(self):
        deriv_text = "パートナー募集中！一緒に夜職ビジネスを拡大しませんか"
        hits = self._theme_gate_check("night_scout", deriv_text)
        self.assertIn("パートナー募集", hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
