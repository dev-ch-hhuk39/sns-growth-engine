from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from accounts.beauty_policy import beauty_compliance_validation, beauty_cta_allowed_for_sequence  # noqa: E402
from generation.beauty_review_pipeline import DEFAULT_ROUTE_TEXTS, ROUTES, build_beauty_review_batch  # noqa: E402
from generation.reference_based_generator import normalize_generated_draft  # noqa: E402
from learning.pdca_orchestrator import PDCAOrchestrator  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _normalized(url: str) -> str:
    return str(url).split("?", 1)[0].rstrip("/")


def test_beauty_account_contract_matches_owner_brief() -> None:
    cfg = _json("config/accounts/beauty_account.json")
    pipeline = _json("config/beauty_account_pipeline.json")
    assert cfg["status"] == "active"
    assert cfg["platforms"] == ["threads"]
    assert cfg["target_audience"] == "美容・コスメが好きな20〜30代女性"
    assert cfg["first_person"] == "私"
    assert cfg["primary_goal"] == "フォロー・保存・リーチ獲得"
    assert cfg["cta_policy"]["cta_frequency_percent"] == 10
    assert cfg["cta_policy"]["allowed_cta_types"] == ["save", "like", "follow"]
    assert cfg["posting_schedule"]["daily_target_min"] == 1
    assert cfg["posting_schedule"]["daily_target_max"] == 2
    assert cfg["posting_schedule"]["scheduled_publish_enabled"] is True
    assert cfg["safety_policy"]["requires_human_review_before_post"] is False
    assert cfg["safety_policy"]["allow_real_post"] is True
    assert pipeline["status"] == "autonomous_strict_production"
    assert pipeline["auto_ready_enabled"] is True
    assert pipeline["scheduled_publish_enabled"] is True
    assert pipeline["real_post_enabled"] is True


def test_all_22_owner_declared_beauty_sources_are_mapped_and_disabled() -> None:
    manifest = _json("config/source_accounts/owner_reference_sources_20260817.json")
    declared = [url for urls in manifest["accounts"]["beauty_account"].values() for url in urls]
    assert len(declared) == 22
    assert len({_normalized(url) for url in declared}) == 22
    registry = _json("config/source_accounts/default_sources.json")["sources"]
    by_url = {_normalized(row.get("canonical_url") or row.get("source_url", "")): row for row in registry}
    for url in declared:
        row = by_url[_normalized(url)]
        assert "beauty_account" in row.get("target_account_ids", [])
        assert row.get("active") is False
        assert row.get("fetch_enabled") is False


def test_beauty_voice_and_public_validator_allow_good_copy() -> None:
    for text in DEFAULT_ROUTE_TEXTS.values():
        result = final_public_post_validator(text, "beauty_account")
        assert result["status"] == "PASS", result
        assert result["voice_persona_check"]["status"] == "VOICE_PERSONA_PASS"
        assert result["account_fit_score"] >= 80
        assert result["requires_human_review"] is False


def test_beauty_compliance_blocks_claims_and_separates_medical_review() -> None:
    medical = beauty_compliance_validation("美容医療の施術を検討する時は、クリニックで医師に確認する項目を整理してみて。")
    assert medical["status"] == "BLOCKED"
    assert medical["review_lane"] == "BEAUTY_MEDICAL"
    assert medical["medical_review_required"] is True
    assert medical["requires_human_review"] is False
    blocked = beauty_compliance_validation("この施術なら絶対に治る。今すぐ購入して。")
    assert blocked["status"] == "BLOCKED"
    assert blocked["blocked_reasons"]
    generated_claim = beauty_compliance_validation("冷風でキューティクルが閉じて、毎日のヘアケアが効果的になるはず。")
    assert generated_claim["status"] == "BLOCKED"
    assert beauty_compliance_validation("きっと肌が変わるはず！")["status"] == "BLOCKED"
    unsafe_usage = beauty_compliance_validation("ねぇ、みんな。私もつい後回しにしていた。シートマスクの上から美顔器を使って。")
    assert unsafe_usage["status"] == "BLOCKED"
    assert "beauty_fabricated_personal_experience" in unsafe_usage["blocked_reasons"]
    assert "beauty_unverified_product_usage" in unsafe_usage["blocked_reasons"]


def test_beauty_public_post_is_bounded_to_320_characters() -> None:
    text = "肌とスキンケアをまず見直す。" + "あ" * 310
    result = final_public_post_validator(text, "beauty_account")
    assert result["status"] == "BLOCKED"
    assert "beauty_text_too_long" in result["blocked_reasons"]


def test_beauty_public_post_blocks_malformed_te_form() -> None:
    malformed = (
        "スキンケアを見直したい時、全部を一度に変えると何が合ったのか分かりにくい🥺\n\n"
        "まずは使う順番か量のどちらか一つに絞って、過去の記録と比べるてみてほしいな✨🤍"
    )
    result = final_public_post_validator(malformed, "beauty_account")
    assert result["status"] == "BLOCKED"
    assert "malformed_te_form" in result["blocked_reasons"]

    corrected = malformed.replace("比べるてみて", "比べてみて")
    corrected_result = final_public_post_validator(corrected, "beauty_account")
    assert "malformed_te_form" not in corrected_result["blocked_reasons"]


def test_beauty_cta_policy_is_ten_percent_and_lightweight() -> None:
    selected = [n for n in range(1, 101) if beauty_cta_allowed_for_sequence(n)]
    assert selected == list(range(10, 101, 10))


def test_all_five_routes_are_waiting_review_and_never_publishable() -> None:
    result = build_beauty_review_batch(sequence_start=1)
    assert result["generation_routes"] == list(ROUTES)
    assert result["candidate_count"] == 5
    assert result["all_public_validators_pass"] is True
    assert result["all_candidates_waiting_review"] is True
    assert all(row["status"] == "WAITING_REVIEW" for row in result["candidates"])
    text_rows = [row for row in result["candidates"] if row["generation_route"] not in {"direct_reference_media", "approved_source_clip"}]
    assert all(row["auto_ready_allowed"] is True for row in text_rows)
    assert all(row["publisher_eligible"] is False for row in result["candidates"])
    media = [row for row in result["candidates"] if row["generation_route"] in {"direct_reference_media", "approved_source_clip"}]
    assert all(row["auto_ready_allowed"] is False for row in media)
    assert all(row["media_permission_gate"] == "AWAITING_APPROVED_MEDIA" for row in media)


def test_legacy_reference_generator_also_keeps_beauty_waiting_review() -> None:
    draft = normalize_generated_draft({"content": "本文", "text_policy_status": "OK"}, {}, "beauty_account")
    assert draft["status"] == "WAITING_REVIEW"


def test_beauty_pdca_is_strictly_account_scoped() -> None:
    rows = [
        {"account_id": "beauty_account", "platform": "threads", "content_type": "single_post", "views": 100, "likes": 10},
        {"account_id": "night_scout", "platform": "threads", "content_type": "single_post", "views": 9999, "likes": 9999},
    ]
    result = PDCAOrchestrator().run(rows, account_id="beauty_account", platform="threads", generate_next_plan=True)
    assert result["analysis"]["total_results"] == 1
    assert result["analysis"]["account_scope_status"] == "PASS"
    assert result["analysis"]["excluded_cross_account_result_count"] == 1
    assert all(job["account_id"] == "beauty_account" for job in result["next_generation_jobs"])
    assert all(job["status"] == "WAITING_REVIEW" for job in result["next_generation_jobs"])


def test_beauty_credentials_are_names_only_in_repository() -> None:
    credentials = _json("config/accounts/beauty_account.json")["threads_credentials"]
    assert credentials["handle"] == ""
    assert credentials["user_id"] == ""
    assert credentials["oauth_status"] == "GITHUB_ENVIRONMENT_SECRETS"
    assert credentials["handle_secret_name"] == "THREADS_HANDLE_BEAUTY_ACCOUNT"
    assert credentials["access_token_secret_name"] == "THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT"
    assert credentials["user_id_secret_name"] == "THREADS_USER_ID_BEAUTY_ACCOUNT"


def test_beauty_operational_mix_contains_exactly_five_routes() -> None:
    beauty = _json("config/content_mix/default_mix.json")["operational_threads_slot_mix"]["beauty_account"]
    assert set(beauty) == set(ROUTES)
    assert sum(beauty.values()) == 100
