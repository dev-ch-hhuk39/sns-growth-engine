#!/usr/bin/env python3
"""Focused V1 contract for transient-provider fallback and strict autonomy."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from gemini_hybrid_client import (  # noqa: E402
    GeminiHttpError,
    GeminiProviderUnavailableError,
)
from hybrid_ai_gate import (  # noqa: E402
    HybridAiGate,
    hybrid_ai_gate_passed,
    merge_gate_audit,
)
from accounts.beauty_policy import beauty_compliance_validation  # noqa: E402
from select_beauty_scheduled_ready import select_beauty_scheduled_ready  # noqa: E402

NIGHT_TEXT = (
    "これからキャバを始める子は、時給だけで店を決めない方がいい。\n\n"
    "客層、ノルマ、出勤のしやすさ、担当へ相談できるか。"
    "条件を並べないと、入ってから続けにくいことって結構ある。\n\n"
    "僕なら、無理なく続けられる店か体入前に見るんだよね。"
)
BEAUTY_TEXT = (
    "スキンケアを一度に変えたくなる時って\n"
    "ほんとに何から試すか迷うんだよね🥺\n\n"
    "個人的には、まず一つだけ変えるのが結構大事\n"
    "肌の変化と理由を分けて見やすい気がする💭\n\n"
    "使い始めた日をメモして\n"
    "その他はいつも通りで試してみてほしい🤍"
)


class FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.actual_request_count = 2

    def generate_json(self, **_kwargs: object) -> dict:
        raise self.exc


class RejectingClient:
    actual_request_count = 1

    def generate_json(self, **_kwargs: object) -> dict:
        return {
            "data": {
                "decision": "REJECT",
                "target_account_match": "FAIL",
                "target_audience_match": "FAIL",
                "source_audience": "business_operator",
                "commercial_context": "B2B_SALES",
                "source_usage_fit": "FAIL",
                "risk_flags": ["semantic_mismatch"],
                "reasons": ["wrong audience"],
            }
        }


def media_queue(**updates: object) -> dict:
    row = {
        "queue_id": "q_fallback_media",
        "account_id": "night_scout",
        "target_account_id": "night_scout",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "generation_mode": "direct_reference_media",
        "content_type": "direct_video",
        "media_origin": "direct_reference",
        "transformation_type": "transform",
        "source_id": "src_night",
        "source_post_id": "sp_night_1",
        "public_post_text": NIGHT_TEXT,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": "https://cdn.example/night.mp4",
        "media_asset_id": "ma_night_1",
        "media_status": "UPLOADED",
        "media_required": "true",
        "media_type": "video",
        "duration_seconds": 20,
        "aspect_ratio": "9:16",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "alignment_status": "PASS",
        "final_alignment_score": 0.91,
        "main_claim_coverage": 1.0,
        "unsupported_claim_count": 0,
        "source_copy_similarity": 0.3,
        "recent_post_similarity": 0.2,
    }
    row.update(updates)
    return row


def media_context(**updates: object) -> dict:
    row = {
        "source_id": "src_night",
        "source_post_id": "sp_night_1",
        "original_post_text": NIGHT_TEXT,
        "source_text": NIGHT_TEXT,
        "source_target_account_id": "night_scout",
        "permission_evidence_status": "APPROVED",
        "use_policy": "APPROVED_MEDIA_REUSE",
        "usage_scope": "APPROVED_MEDIA_REUSE",
        "reuse_policy": "APPROVED",
        "canonical_source_url": "https://www.threads.com/@owner/post/abc",
        "source_author_identity_status": "PASS",
        "source_parent_identity_status": "PASS",
        "source_media_parent_status": "PASS",
        "source_media_order_status": "PASS",
        "provenance_status": "PASS",
        "read_errors": [],
    }
    row.update(updates)
    return row


def assert_transient_fallback(exc: Exception) -> None:
    queue = media_queue()
    context = media_context()
    result = HybridAiGate(FailingClient(exc)).evaluate(queue, context)
    assert result.status == "PASS", result.audit()
    assert result.provider_status == "UNAVAILABLE"
    assert result.provider_mode == "deterministic_local_strict"
    assert result.fallback_mode == "deterministic_strict"
    assert result.deterministic_validation["media_validation"]["status"] == "PASS"
    persisted = {**queue, "generation_policy_json": merge_gate_audit("", result)}
    assert hybrid_ai_gate_passed(persisted, context) == (True, "pass")


def main() -> int:
    # A-C: bounded Gemini exhaustion can continue only through strict evidence.
    assert_transient_fallback(GeminiHttpError(429, "quota"))
    assert_transient_fallback(GeminiHttpError(503, "temporary"))
    assert_transient_fallback(GeminiProviderUnavailableError("TIMEOUT", "timeout"))

    # D: a real semantic rejection is a terminal content decision.
    rejected = HybridAiGate(RejectingClient()).evaluate(media_queue(), media_context())
    assert rejected.status == "BLOCKED"
    assert rejected.provider_mode == "gemini"
    assert not rejected.fallback_mode

    # E-H: strict local checks remain fail-closed.
    bad_cases = (
        media_queue(validator_status="BLOCKED"),
        media_queue(rights_status="third_party_reference_only"),
        media_queue(permission_status="denied"),
    )
    for queue in bad_cases:
        result = HybridAiGate(FailingClient(GeminiHttpError(429, "quota"))).evaluate(
            queue, media_context()
        )
        assert result.status == "BLOCKED", result.audit()
    isolated = HybridAiGate(FailingClient(GeminiHttpError(429, "quota"))).evaluate(
        media_queue(), media_context(source_target_account_id="liver_manager")
    )
    assert isolated.status == "BLOCKED"

    # I-K: safe Beauty can use formal autonomous provenance; medical content
    # blocks and no fake human approval is introduced.
    beauty = beauty_compliance_validation(BEAUTY_TEXT)
    assert beauty["status"] == "PASS" and beauty["auto_ready_allowed"] is True
    medical = beauty_compliance_validation(BEAUTY_TEXT + "\nボトックス施術なら必ず変わる")
    assert medical["status"] == "BLOCKED" and medical["auto_ready_allowed"] is False
    beauty_ready = {
        "queue_id": "q_beauty_auto",
        "account_id": "beauty_account",
        "platform": "threads",
        "status": "READY",
        "slot_id": "beauty_1130",
        "business_date_jst": "2026-08-29",
        "approval_source": "autonomous_strict_beauty",
        "approval_policy": "autonomous_strict_beauty",
        "auto_publish": "true",
        "auto_ready_by": "auto_approve_queue.py",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "semantic_voice_status": "PASS",
        "style_fingerprint_status": "VOICE_PERSONA_PASS",
        "human_review_decision": "",
    }
    selected = select_beauty_scheduled_ready(
        [beauty_ready], text_slot_id="beauty_1130", business_date_jst="2026-08-29"
    )
    assert selected and selected["queue_id"] == "q_beauty_auto"
    assert not selected.get("human_review_decision")

    # L-N: scheduled contracts use strict approval, normal NO_POST, and never X.
    workflows = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            ".github/workflows/autonomous-growth-loop-night-scout.yml",
            ".github/workflows/autonomous-growth-loop-liver-manager.yml",
            ".github/workflows/beauty-threads-production.yml",
            ".github/workflows/direct-reference-media-night-scout.yml",
            ".github/workflows/direct-reference-media-liver-manager.yml",
            ".github/workflows/media-growth-post-night-scout.yml",
            ".github/workflows/media-growth-post-liver-manager.yml",
        )
    )
    assert "steps.scheduled_queue.outputs.human_approved" not in workflows
    assert '--require-human-review' not in workflows
    assert 'ALLOW_REAL_X_POST: "true"' not in workflows
    assert 'exit 2; fi' not in "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            ".github/workflows/direct-reference-media-night-scout.yml",
            ".github/workflows/direct-reference-media-liver-manager.yml",
            ".github/workflows/media-growth-post-night-scout.yml",
            ".github/workflows/media-growth-post-liver-manager.yml",
        )
    )
    print(json.dumps({"status": "PASS", "checks": "A-N"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
