#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from generation.content_quality_v2 import (  # noqa: E402
    build_post_package,
    hard_gate,
    load_policy,
    rank_candidate,
    repair_style_only,
    select_media_or_text_fallback,
    select_ranked_candidate,
    sanitize_transcript_excerpt,
    understand_media_contract,
)


def test_quality_is_ranked_not_hard_blocked() -> None:
    result = hard_gate(
        {"account_id": "liver_manager", "target_account_id": "liver_manager",
         "platform": "threads", "public_post_text": "配信の話。"},
        account_id="liver_manager",
        public_validation={"status": "BLOCKED", "blocked_reasons": ["naturalness_below_threshold", "topic_coherence_low"]},
    )
    assert result == {"status": "PASS", "hard_gate_reasons": []}


def test_account_rights_duplicate_and_private_data_remain_hard() -> None:
    cases = [
        ({"account_id": "liver_manager", "target_account_id": "night_scout"}, "account_mismatch"),
        ({"account_id": "liver_manager", "duplicate": True}, "duplicate_asset_or_post"),
        ({"account_id": "liver_manager", "media_required": True}, "rights_invalid"),
    ]
    for candidate, expected in cases:
        result = hard_gate(candidate, account_id="liver_manager")
        assert expected in result["hard_gate_reasons"]
    private = hard_gate(
        {"account_id": "liver_manager", "target_account_id": "liver_manager"},
        account_id="liver_manager",
        public_validation={"status": "BLOCKED", "blocked_reasons": ["internal_terms"]},
    )
    assert "internal_terms" in private["hard_gate_reasons"]


def test_fabricated_experience_unsupported_claim_and_broken_japanese_block() -> None:
    fabricated = hard_gate({"public_post_text": "私が1週間使ったら変わった。"}, account_id="beauty_account")
    unsupported = hard_gate({"public_post_text": "この方法なら必ず治る。"}, account_id="beauty_account")
    malformed = hard_gate({"public_post_text": "確認しましょうんだよね"}, account_id="night_scout")
    assert "fabricated_personal_experience" in fabricated["hard_gate_reasons"]
    assert "unsupported_high_risk_factual_claim" in unsupported["hard_gate_reasons"]
    assert "broken_japanese" in malformed["hard_gate_reasons"]
    benign = hard_gate({"public_post_text": "出勤条件は必ず書面で確認したい。"}, account_id="night_scout")
    assert "unsupported_high_risk_factual_claim" not in benign["hard_gate_reasons"]

    from generation.content_quality_v2 import fabricated_media_experience
    for text in (
        "朝のスキンケアに取り入れると、肌がキュッと整う感じがして気に入ってるよ。",
        "アゼライン酸もあわせて使うと肌の調子がいい気がするな。",
        "この美容液は使いやすいから気に入っている。",
    ):
        assert fabricated_media_experience(text)["status"] == "BLOCKED", text
    safe_observation = "画面に「グリシルグリシン3.0」と表示され、スポイトから透明な液体を手に出している。"
    assert fabricated_media_experience(safe_observation)["status"] == "PASS"
    attributed = "動画の人物が「気に入ってる」という感想を紹介している。"
    assert fabricated_media_experience(attributed)["status"] == "PASS"


def test_supported_claim_mapping_is_handled_and_source_experience_is_not_reassigned() -> None:
    evidence = [{"caption_claim": "動画の発信者は1週間使った感想を紹介している", "source_evidence": "1週間使った"}]
    attributed = hard_gate(
        {"public_post_text": "発信者が1週間使った感想を紹介している。", "source_creator_context": "1週間使った", "supported_claims": evidence},
        account_id="beauty_account",
    )
    assert "source_creator_experience_reassigned" not in attributed["hard_gate_reasons"]


def test_beauty_repairs_zero_emoji_once_and_liver_does_not_force_one() -> None:
    beauty = repair_style_only("スキンケアは使う順番も大切。", "beauty_account")
    liver = repair_style_only("初見がコメントしにくい時は、質問を一つに絞る。", "liver_manager")
    assert beauty["repair_count"] == 1 and any(e in beauty["public_post_text"] for e in load_policy()["accounts"]["beauty_account"]["emoji_allowed"])
    assert liver["repair_count"] == 0 and not any(e in liver["public_post_text"] for e in load_policy()["accounts"]["liver_manager"]["emoji_allowed"])
    assert "確認することは一つ。" not in repair_style_only("確認することは一つ。\n控除を聞く。", "night_scout")["public_post_text"]


def test_transcript_alone_never_proves_visual_understanding() -> None:
    understanding = understand_media_contract(
        {"media_asset_id": "m1", "media_type": "video", "transcript_text": "初見への声かけについて話す", "transcript_status": "PASS"},
        account_id="liver_manager",
    )
    assert understanding["visual_status"] == "VISUAL_UNVERIFIED"
    assert understanding["what_viewer_actually_sees"] == "VISUAL_UNVERIFIED"
    assert understanding["what_viewer_actually_hears"] != "AUDIO_UNVERIFIED"


def test_unverified_visual_and_generic_caption_are_ranked_down_not_blocked() -> None:
    package = build_post_package(
        account_id="liver_manager",
        media={"media_asset_id": "m1", "media_type": "video", "transcript_text": "配信では初見への質問を短くするとよい", "transcript_status": "PASS"},
        public_caption="毎日少しずつ工夫していきたい。",
        hard_gate_result={"status": "PASS", "hard_gate_reasons": []},
    )
    assert package["hard_gate_result"]["status"] == "PASS"
    assert package["generic_caption_risk"] == "HIGH"
    assert "VISUAL_UNVERIFIED" in package["warnings"]
    assert package["media_anchor"]["remove_media_test"] == "GENERIC_CAPTION_RISK_HIGH"


def test_transcript_cleanup_removes_annotation_garbage_without_rewriting_facts() -> None:
    result = sanitize_transcript_excerpt("初見さんへの声かけ\n[音楽]\n初見さんへの声かけ\n�")
    assert result["text"] == "初見さんへの声かけ"
    assert result["dropped_fragment_count"] == 3


def test_pairwise_regression_fixtures_are_rank_ordered() -> None:
    policy = load_policy()
    fixtures = policy["pairwise_regression"]
    assert len(fixtures) == 3
    score_sets = {
        "LM-03": {"reader_value": 90, "account_relevance": 92, "naturalness": 88, "persona_evidence": 90, "topic_coherence": 94, "media_caption_relevance": 40, "concrete_evidence": 90, "novelty": 85, "cta_fit": 82, "style_diversity": 88},
        "LM-01": {"reader_value": 55, "account_relevance": 58, "naturalness": 60, "persona_evidence": 55, "topic_coherence": 52, "media_caption_relevance": 40, "concrete_evidence": 45, "novelty": 40, "cta_fit": 65, "style_diversity": 50},
        "NS-08": {"reader_value": 88, "account_relevance": 94, "naturalness": 86, "persona_evidence": 92, "topic_coherence": 90, "media_caption_relevance": 40, "concrete_evidence": 94, "novelty": 82, "cta_fit": 80, "style_diversity": 90},
        "NS-04": {"reader_value": 55, "account_relevance": 60, "naturalness": 58, "persona_evidence": 55, "topic_coherence": 55, "media_caption_relevance": 40, "concrete_evidence": 42, "novelty": 35, "cta_fit": 58, "style_diversity": 35},
        "BA-07": {"reader_value": 90, "account_relevance": 92, "naturalness": 94, "persona_evidence": 94, "topic_coherence": 90, "media_caption_relevance": 40, "concrete_evidence": 85, "novelty": 86, "cta_fit": 88, "style_diversity": 92},
        "BA-03": {"reader_value": 55, "account_relevance": 55, "naturalness": 58, "persona_evidence": 50, "topic_coherence": 56, "media_caption_relevance": 40, "concrete_evidence": 40, "novelty": 35, "cta_fit": 55, "style_diversity": 35},
    }
    for fixture in fixtures:
        higher = rank_candidate({"quality_components": score_sets[fixture["preferred"]]}, account_id=fixture["account_id"])
        lower = rank_candidate({"quality_components": score_sets[fixture["lower_ranked"]]}, account_id=fixture["account_id"])
        assert higher["quality_rank"] > lower["quality_rank"], fixture["id"]


def test_media_regression_fixtures_are_visible_and_unverified_is_explicit() -> None:
    rows = load_policy()["media_regression"]
    assert {row["id"] for row in rows} == {"NS-M03", "LM-M02", "BA-M01"}
    assert json.loads(json.dumps(rows))[1]["expected_warning"] == "VISUAL_UNVERIFIED"


def test_rank_selector_ignores_legacy_status_and_selects_best_hard_pass() -> None:
    selected = select_ranked_candidate([
        {"candidate_id": "weak", "hard_gate_status": "PASS", "quality_components": {"reader_value": 20}},
        {"candidate_id": "strong", "hard_gate_status": "PASS", "quality_components": {"reader_value": 95, "account_relevance": 90}},
        {"candidate_id": "unsafe", "hard_gate_status": "BLOCKED", "quality_components": {"reader_value": 100}},
    ], account_id="liver_manager")
    assert selected and selected["candidate_id"] == "strong"


def test_media_exhaustion_is_explicit_text_degradation_not_media_success() -> None:
    fallback = select_media_or_text_fallback(
        [{"candidate_id": "bad-media", "hard_gate_result": {"status": "BLOCKED"},
          "quality_components": {"reader_value": 100}}],
        [{"candidate_id": "safe-text", "hard_gate_status": "PASS",
          "quality_components": {"reader_value": 60}}],
        account_id="night_scout",
    )
    assert fallback and fallback["candidate_id"] == "safe-text"
    assert fallback["route_status"] == "DEGRADED_TO_TEXT"
    assert fallback["media_counted_as_success"] is False
    assert fallback["fallback_reason"] == "NO_HARD_GATE_MEDIA_CANDIDATE"


def test_content_v2_policy_stays_draft_only() -> None:
    policy = load_policy()
    assert policy["draft_only"] is True
    assert policy["publishing_enabled"] is False


def test_auto_approval_evaluator_never_promotes_v2_drafts() -> None:
    import auto_approve_queue

    rules = auto_approve_queue.rules_for_account(auto_approve_queue.load_rules(), "liver_manager")
    text = "配信で初見さんがコメントしやすいように、質問を一つに絞って待ってみる。"
    result = auto_approve_queue.evaluate_item(
        queue={"queue_id": "q_v2_test", "account_id": "liver_manager", "target_account_id": "liver_manager",
               "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "original_text",
               "content_quality_v2_version": "content_quality_v2", "content_quality_v2_status": "DRAFT_ONLY_RANKED",
               "public_post_text": text},
        draft={}, derivative={"text": text}, scores_by_ref={}, existing_texts=[],
        rules={**rules, "auto_ready_enabled": True},
    )
    assert result["status"] == "DRAFT_ONLY"
    assert result["content_quality_v2_status"] == "DRAFT_ONLY_RANKED"


def test_hybrid_v2_treats_editorial_voice_and_template_as_warnings() -> None:
    from hybrid_ai_gate import _candidate_hygiene_reasons, _candidate_scheduled_text_contract_reasons

    row = {
        "content_quality_v2_version": "content_quality_v2",
        "content_quality_v2_status": "DRAFT_ONLY_RANKED",
        "account_id": "night_scout",
        "content_type": "original_text",
    }
    assert "generic_template_phrase_present" not in _candidate_hygiene_reasons(
        row, "確認することは一つ。条件を比べる。",
    )
    assert _candidate_scheduled_text_contract_reasons(row, "店の条件を比べる。") == []


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} Content Quality V2 contract tests")
