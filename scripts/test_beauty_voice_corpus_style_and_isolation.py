#!/usr/bin/env python3
"""Focused acceptance contract for Chadult Beauty Voice and route isolation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from generation.beauty_review_pipeline import ROUTES, select_beauty_route  # noqa: E402
from generation.beauty_voice import (  # noqa: E402
    beauty_style_fingerprint_validation,
    build_voice_corpus_summary,
    load_beauty_voice_profile,
)
from hybrid_ai_policy import TARGET_ACCOUNTS, requires_hybrid_ai_gate  # noqa: E402
from prepare_beauty_review_candidates import (  # noqa: E402
    select_beauty_pdca_context,
    select_beauty_reference_context,
)
from process_threads_queue import beauty_production_configured  # noqa: E402
from publication_review_board import decision_for_row, review_row  # noqa: E402
from sheets_client import TAB_DEFINITIONS  # noqa: E402
from acquire_approved_source_posts import selected_sources  # noqa: E402
from recover_production_sheets_threads_first import source_rows  # noqa: E402

GOOD = (
    "スキンケアを一度に変えたくなる時って\n"
    "ほんとに何から試すか迷うんだよね🥺\n\n"
    "個人的には、まず一つだけ変えるのが結構大事\n"
    "肌の変化と理由を分けて見やすい気がする💭\n\n"
    "使い始めた日をメモして\n"
    "その他はいつも通りで試してみてほしい🤍"
)


def main() -> None:
    profile = load_beauty_voice_profile()
    assert profile["style_profile_version"] == "chadult_beauty_voice_v1"
    assert profile["corpus_policy"]["content_reference_separated"] is True
    assert profile["corpus_policy"]["copy_verbatim_examples"] is False
    collection = profile["bounded_reference_collection"]
    assert collection["enabled"] is True
    assert collection["reference_only"] is True
    assert collection["x_read_only"] is True
    assert collection["allow_media_reuse"] is False
    assert collection["allow_x_post"] is False
    assert collection["max_new_posts_per_source_per_run"] == 10
    assert collection["max_total_new_posts_per_run"] == 30

    good = beauty_style_fingerprint_validation(GOOD)
    assert good["status"] == "VOICE_PERSONA_PASS", good
    assert good["score"] >= 85
    assert good["details"]["emoji_count"] >= 1
    assert good["details"]["conversational_style_score"] >= 85

    weak = beauty_style_fingerprint_validation(
        "美容家電は使う時間から選ぶと良いよね。\n\n"
        "私なら機能を確認します。\n\n比べてみてください。"
    )
    assert weak["status"] == "BLOCKED", weak
    assert "beauty_voice_emoji_count_out_of_range" in weak["reasons"]

    foreign = beauty_style_fingerprint_validation(GOOD + "\n\n配信時間と初見コメントも見てみて")
    assert foreign["status"] == "BLOCKED", foreign
    assert "beauty_voice_cross_account_context_detected" in foreign["reasons"]

    rows = []
    for source_id in profile["voice_reference_source_ids"][:5]:
        rows.extend(
            {
                "source_id": source_id,
                "target_account_id": "beauty_account",
                "original_post_text": f"美容テキスト{index}🤍",
            }
            for index in range(10)
        )
    rows.append({"source_id": "src_ns_forbidden", "target_account_id": "night_scout", "original_post_text": "夜職"})
    corpus = build_voice_corpus_summary(rows)
    assert corpus["status"] == "READY", corpus
    assert corpus["source_account_count"] == 5
    assert corpus["post_count"] == 50
    assert corpus["raw_post_text_included"] is False
    assert corpus["emoji_per_post"] > 0
    assert "humanity_marker_frequency" in corpus
    assert "soft_ending_frequency" in corpus
    assert "src_ns_forbidden" not in corpus["posts_per_source"]
    insufficient = build_voice_corpus_summary(rows[:9])
    assert insufficient["status"] == "INSUFFICIENT_CORPUS"

    reference = select_beauty_reference_context([
        {
            "source_id": profile["voice_reference_source_ids"][0],
            "target_account_id": "beauty_account",
            "source_post_id": "beauty_post_1",
            "individual_post_url": "https://example.test/beauty/post/1",
            "original_post_text": "美容の参考本文",
        },
        {
            "source_id": "src_ns_forbidden",
            "target_account_id": "night_scout",
            "source_post_id": "night_post_1",
            "individual_post_url": "https://example.test/night/post/1",
            "original_post_text": "夜職の本文",
        },
    ])
    assert reference["status"] == "PASS"
    assert reference["source_post_id"] == "beauty_post_1"
    assert "夜職" not in reference["internal_evidence"]

    pdca = select_beauty_pdca_context([
        {"result_id": "night_result", "account_id": "night_scout", "metrics_status": "MEASURED"},
        {
            "result_id": "beauty_result",
            "account_id": "beauty_account",
            "metrics_status": "MEASURED",
            "theme": "skin_care",
            "views": 120,
        },
    ])
    assert pdca["status"] == "PASS"
    assert pdca["pdca_result_id"] == "beauty_result"
    assert "night_result" not in pdca["internal_evidence"]

    selected = {select_beauty_route(number) for number in range(1, 101)}
    assert selected == set(ROUTES), selected
    assert "beauty_account" in TARGET_ACCOUNTS
    for route in ROUTES:
        queue = {
            "account_id": "beauty_account",
            "target_account_id": "beauty_account",
            "platform": "threads",
            "generation_mode": f"beauty_{route}",
            "content_type": route,
        }
        assert requires_hybrid_ai_gate(queue), route

    policy = json.loads((ROOT / "config/hybrid_ai_account_policies.json").read_text(encoding="utf-8"))
    beauty_policy = policy["accounts"]["beauty_account"]
    assert beauty_policy["strict_account_isolation"] is True
    assert beauty_policy["cross_account_learning"] is False

    pipeline = json.loads((ROOT / "config/beauty_account_pipeline.json").read_text(encoding="utf-8"))
    assert pipeline["status"] == "review_required_production"
    assert pipeline["candidate_status"] == "WAITING_REVIEW"
    assert pipeline["auto_ready_enabled"] is False
    assert set(pipeline["generation_routes"]) == set(ROUTES)
    assert beauty_production_configured() is True

    media_config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
    assert "beauty_account" in media_config["allowed_target_account_ids"]
    assert "beauty_account" in media_config["asset_inventory_targets"]
    direct_media_source = (ROOT / "scripts/run_direct_reference_media_pipeline.py").read_text(encoding="utf-8")
    assert '"beauty_account": "beauty_direct_media_review"' in direct_media_source
    assert 'choices=["night_scout", "liver_manager", "beauty_account"]' in direct_media_source

    required_voice_columns = {
        "voice_style_profile_version", "style_fingerprint_status", "style_fingerprint_score",
        "semantic_voice_status", "semantic_voice_score",
        "voice_corpus_status", "voice_corpus_source_count", "voice_corpus_post_count",
        "pdca_account_scope", "pdca_result_id",
    }
    assert required_voice_columns <= set(TAB_DEFINITIONS["queue"])
    assert required_voice_columns - {"pdca_account_scope", "pdca_result_id"} <= set(TAB_DEFINITIONS["publication_review"])

    queue = {
        "queue_id": "q_beauty_voice", "account_id": "beauty_account", "platform": "threads",
        "status": "WAITING_REVIEW", "public_post_text": GOOD, "validator_status": "PASS",
        "internal_leak_status": "PASS", "media_required": "false",
        "style_fingerprint_status": "VOICE_PERSONA_PASS", "style_fingerprint_score": 100,
        "semantic_voice_status": "PASS", "semantic_voice_score": 95,
        "voice_style_profile_version": "chadult_beauty_voice_v1",
        "voice_corpus_status": "READY", "voice_corpus_source_count": 5,
        "voice_corpus_post_count": 50,
    }
    mirrored = review_row(queue)
    assert mirrored["voice_style_profile_version"] == "chadult_beauty_voice_v1"
    assert mirrored["voice_corpus_status"] == "READY"
    assert decision_for_row({"review_decision": "OK"}, queue, allow_media_posts=False)[0] == "READY"
    assert decision_for_row(
        {"review_decision": "OK"}, {**queue, "semantic_voice_status": "BLOCKED"}, allow_media_posts=False
    )[0] == "BLOCKED_BEAUTY_VOICE"

    default_sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    beauty_sources = [row for row in default_sources if "beauty_account" in (row.get("target_account_ids") or [])]
    assert len(beauty_sources) == 22
    assert all(row.get("target_account_ids") == ["beauty_account"] for row in beauty_sources)
    legacy = [row for row in default_sources if row.get("legacy_status") == "LEGACY_QUARANTINED_NOT_IN_OWNER_MANIFEST"]
    assert len(legacy) == 3 and all(not row.get("target_account_ids") for row in legacy)

    voice_ids = set(profile["voice_reference_source_ids"])
    selected_sources_rows, blocked = selected_sources("beauty_account", "all", reference_only=True)
    assert {row["source_id"] for row in selected_sources_rows} == voice_ids
    assert blocked == []
    assert all(row.get("rights_policy") == "reference_only" for row in selected_sources_rows)
    assert all(row.get("can_reuse_media") is False for row in selected_sources_rows)
    selected_media_rows, _ = selected_sources("beauty_account", "all", reference_only=False)
    assert selected_media_rows == []
    account_rows, _video_rows = source_rows()
    beauty_registry = [row for row in account_rows if row.get("target_account_id") == "beauty_account"]
    assert {row["source_id"] for row in beauty_registry if row["fetch_enabled"] == "true"} == voice_ids
    assert all(row["can_reuse_media"] == "false" for row in beauty_registry)

    gate_source = (ROOT / "scripts/hybrid_ai_gate.py").read_text(encoding="utf-8")
    assert "pdca_internal_learning_exposed_in_public_text" in gate_source
    assert "実測結果、反応理由の仮説、次回に比較する一つの検証を必ず明記" not in gate_source
    workflow = (ROOT / ".github/workflows/beauty-threads-production.yml").read_text(encoding="utf-8")
    assert "run_hybrid_ai_queue_gate.py --account-id beauty_account" in workflow
    assert workflow.index("Save WAITING_REVIEW candidate") < workflow.index("Beauty semantic voice review")
    assert "ALLOW_REAL_X_POST: \"false\"" in workflow
    print("PASS beauty voice corpus, style fingerprint, routes, isolation, Sheets evidence")


if __name__ == "__main__":
    main()
