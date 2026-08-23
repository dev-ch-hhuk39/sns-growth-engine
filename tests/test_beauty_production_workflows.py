from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow(name: str) -> tuple[dict, str]:
    path = ROOT / ".github" / "workflows" / name
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def test_beauty_workflow_prepares_then_publishes_only_reviewed_ready_rows() -> None:
    data, text = _workflow("beauty-threads-production.yml")
    trigger = data.get("on") or data.get(True)
    assert trigger["schedule"] == [
        {"cron": "30 0 * * *"},
        {"cron": "30 9 * * *"},
        {"cron": "30 2 * * *"},
        {"cron": "30 11 * * *"},
    ]
    assert "--apply --confirm-prepare" in text
    assert "WAITING_REVIEW" in text
    assert "process_threads_queue.py --account-id beauty_account" in text
    assert "BEAUTY_PRODUCTION_ENABLED: \"true\"" in text
    assert 'if [ "$ACTION" = "publish" ] && [ "$BEAUTY_ACTIVATION_APPROVED" = "true" ]; then' in text
    assert "ALLOW_REAL_X_POST: \"false\"" in text
    assert "ALLOW_MEDIA_POSTS: \"false\"" in text
    assert "auto_approve_queue.py" not in text
    assert "Repository-wide Sheets diagnostic" in text
    assert "continue-on-error: true" in text
    assert "Strict Beauty queue and publisher preflight" in text
    assert text.count("recover_production_sheets_threads_first.py --verify-only") == 1
    assert "posted_results read-after-write" in text
    assert "queue-level read-after-write" in text
    preview_step = next(
        step for step in data["jobs"]["beauty-production"]["steps"]
        if step.get("name") == "Preview candidate"
    )
    assert preview_step["if"] == "env.ACTION == 'dry_run'"
    assert text.count("prepare_beauty_review_candidates.py") == 2


def test_token_refresh_workflow_includes_beauty_without_logging_token() -> None:
    _, text = _workflow("refresh-threads-tokens.yml")
    assert "beauty_account" in text
    assert "THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" in text
    assert "refresh_threads_token.py --account-id beauty_account --confirm-refresh" in text
    assert "gh secret set THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" in text
    assert "echo $THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" not in text


def test_beauty_publisher_requires_config_and_dedicated_runtime_gate(monkeypatch, tmp_path) -> None:
    worker = _load_script("process_threads_queue.py")
    monkeypatch.delenv("BEAUTY_PRODUCTION_ENABLED", raising=False)
    monkeypatch.setattr(worker, "BEAUTY_PIPELINE_CONFIG", tmp_path / "missing.json")
    allowed, reason = worker.beauty_publish_gate(dry_run=True)
    assert allowed is False
    assert reason == "beauty_production_config_not_enabled"
    config = tmp_path / "beauty.json"
    config.write_text(
        '{"status":"review_required_production","scheduled_publish_enabled":true,'
        '"real_post_enabled":true,"auto_ready_enabled":false}',
        encoding="utf-8",
    )
    monkeypatch.setattr(worker, "BEAUTY_PIPELINE_CONFIG", config)
    assert worker.beauty_publish_gate(dry_run=True) == (True, "")
    allowed, reason = worker.beauty_publish_gate(dry_run=False)
    assert allowed is False
    assert "BEAUTY_PRODUCTION_ENABLED" in reason
    monkeypatch.setenv("BEAUTY_PRODUCTION_ENABLED", "true")
    assert worker.beauty_publish_gate(dry_run=False) == (True, "")


def test_beauty_generated_candidate_is_never_ready(monkeypatch) -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    monkeypatch.setenv("GEMINI_API_KEY", "set-for-test")
    monkeypatch.setattr(prepare, "select_beauty_route", lambda _sequence: "new_text_generation")
    monkeypatch.setattr(
        prepare,
        "load_route_context",
        lambda _route, _topic="": {
            "status": "PASS",
            "source_ids": [],
            "voice_corpus": {"status": "READY", "source_account_count": 5, "post_count": 50},
        },
    )
    monkeypatch.setattr(
        prepare,
        "call_gemini_json",
        lambda *_args, **_kwargs: {
            "public_post_text": (
                "スキンケアを一度に変えたくなる時って\n"
                "ほんとに何から試すか迷うんだよね🥺\n\n"
                "個人的には、まず一つだけ変えるのが結構大事\n"
                "肌の変化と理由を分けて見やすい気がする💭\n\n"
                "使い始めた日をメモして\n"
                "その他はいつも通りで試してみてほしい🤍"
            ),
            "primary_topic": "ベースメイク前の保湿量",
        },
    )
    candidate = prepare.generate_candidate(slot_index=0, sequence_number=1)
    row = prepare.queue_row(candidate)
    assert candidate["status"] == "WAITING_REVIEW"
    assert row["status"] == "WAITING_REVIEW"
    assert row["auto_publish"] == "false"
    assert row["media_required"] == "false"
    assert row["validator_status"] == "PASS"


def test_beauty_prompt_encodes_account_fit_contract() -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    assert all("肌がゆらぐ" not in topic for topic in prepare.TOPICS)
    assert all("待ち時間" not in topic for topic in prepare.TOPICS)
    for topic, terms in prepare.TOPIC_CONTEXT_TERMS.items():
        prompt = prepare._prompt(topic, 1, "new_text_generation")
        assert all(term in prompt for term in terms)
        assert "全体140〜260文字" in prompt
        assert "3〜5段落" in prompt
        assert "感嘆符は0個" in prompt
        assert "average_line_length" not in prompt
        assert "full_stops_per_post" not in prompt
        assert "製品表示や説明書" in prompt
        assert "確認する・比べる・見直す・待つ・変える・メモする" in prompt
        assert "読者が自分で試して判断" in prompt
    no_emoji_prompt = prepare._prompt(prepare.TOPICS[0], 10, "new_text_generation")
    assert "絵文字は0個" in no_emoji_prompt
    assert "投稿全体で1個だけ" in no_emoji_prompt
    retry_prompt = prepare._prompt(
        prepare.TOPICS[2], 1, "new_text_generation", {}, ["persona_reader_context_insufficient"]
    )
    assert "自然な文脈で必ず入れ" in retry_prompt


def test_beauty_safety_fallbacks_all_pass_public_validator() -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    for topic, text in prepare.SAFE_TOPIC_FALLBACKS.items():
        candidate = prepare.build_beauty_review_candidate(
            "new_text_generation",
            public_post_text=text,
            sequence_number=1,
        )
        assert candidate["public_post_validator"]["status"] == "PASS", topic
        assert candidate["beauty_compliance"]["status"] == "PASS", topic


def test_beauty_pdca_unavailable_falls_back_only_to_beauty_new_text(monkeypatch) -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    monkeypatch.setenv("GEMINI_API_KEY", "set-for-test")
    monkeypatch.setattr(prepare, "select_beauty_route", lambda _sequence: "pdca_text_generation")
    calls = []

    def context(route, _topic=""):
        calls.append(route)
        if route == "pdca_text_generation":
            return {"status": "BLOCKED", "reason": "beauty_measured_pdca_evidence_insufficient"}
        return {
            "status": "PASS",
            "source_ids": [],
            "voice_corpus": {"status": "READY", "source_account_count": 5, "post_count": 50},
        }

    monkeypatch.setattr(prepare, "load_route_context", context)
    monkeypatch.setattr(
        prepare,
        "call_gemini_json",
        lambda *_args, **_kwargs: {
            "public_post_text": (
                "スキンケアを一度に変えたくなる時って\n"
                "ほんとに何から試すか迷うんだよね🥺\n\n"
                "個人的には、まず一つだけ変えるのが結構大事\n"
                "肌の変化と理由を分けて見やすい気がする💭\n\n"
                "使い始めた日をメモして\n"
                "その他はいつも通りで試してみてほしい🤍"
            ),
            "primary_topic": "スキンケア",
        },
    )
    candidate = prepare.generate_candidate(slot_index=0, sequence_number=1)
    assert candidate["status"] == "WAITING_REVIEW", candidate
    assert candidate["requested_generation_route"] == "pdca_text_generation"
    assert candidate["generation_route"] == "new_text_generation"
    assert candidate["route_fallback_reason"] == "beauty_measured_pdca_evidence_insufficient"
    row = prepare.queue_row(candidate)
    assert row["source_content_route"] == "pdca_text_generation"
    assert "beauty_measured_pdca_evidence_insufficient" in row["human_review_note"]
    assert calls == ["pdca_text_generation", "new_text_generation"]


def test_beauty_media_route_skips_without_text_fallback(monkeypatch) -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    monkeypatch.setattr(prepare, "select_beauty_route", lambda _sequence: "direct_reference_media")
    candidate = prepare.generate_candidate(slot_index=0, sequence_number=1)
    assert candidate["status"] == "SKIPPED", candidate
    assert candidate["reason"] == "beauty_media_route_delegated_no_text_fallback"
    assert candidate["generation_route"] == "direct_reference_media"


def test_beauty_gemini_errors_are_sanitized_and_classified() -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    cases = {
        "Gemini API エラー (HTTP 429)": ("gemini_rate_limited", True),
        "Gemini API エラー (HTTP 404)": ("gemini_model_not_found", False),
        "Gemini API エラー (HTTP 403)": ("gemini_auth_rejected", False),
        "JSONパース失敗": ("gemini_json_parse_failed", True),
        "Gemini API 接続エラー": ("gemini_connection_error", True),
    }
    for error, expected in cases.items():
        assert prepare._gemini_failure_reason({"_error": error, "_raw": "private"}) == expected


def test_beauty_compliance_blocks_unsupported_outcome_promises() -> None:
    from accounts.beauty_policy import beauty_compliance_validation

    for phrase in ("全然変わる", "格段に良くなる", "たった数分で"):
        result = beauty_compliance_validation(f"スキンケアは{phrase}")
        assert result["status"] == "BLOCKED", (phrase, result)
        assert "beauty_prohibited_effect_or_medical_claim" in result["blocked_reasons"]
    fabricated = beauty_compliance_validation(
        "私、保湿の量と待ち時間を分けて考えるようにしてる"
    )
    assert fabricated["status"] == "BLOCKED", fabricated
    assert "beauty_fabricated_personal_experience" in fabricated["blocked_reasons"]

    tired_skin = beauty_compliance_validation("肌が疲れてるサインかもしれない")
    assert tired_skin["status"] == "BLOCKED", tired_skin
    for usage in ("化粧水をたっぷり塗る", "数分待ってメイク", "数分長く待つ"):
        result = beauty_compliance_validation(usage)
        assert result["status"] == "BLOCKED", (usage, result)
        assert "beauty_unverified_product_usage" in result["blocked_reasons"]


def test_beauty_secrets_are_referenced_by_name_only() -> None:
    _, beauty = _workflow("beauty-threads-production.yml")
    assert "${{ secrets.THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT }}" in beauty
    assert "${{ secrets.THREADS_USER_ID_BEAUTY_ACCOUNT }}" in beauty
    assert "${{ secrets.THREADS_HANDLE_BEAUTY_ACCOUNT }}" in beauty
    assert "access_token=" not in beauty.lower()
