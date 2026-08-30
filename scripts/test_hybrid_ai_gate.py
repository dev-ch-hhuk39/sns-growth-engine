#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import (  # noqa: E402
    HybridAiGate,
    _classification_prompt,
    hybrid_ai_gate_current,
    hybrid_ai_gate_passed,
    merge_gate_audit,
)
from public_post_quality import generate_reader_facing_post  # noqa: E402


class FakeClient:
    def __init__(
        self,
        *,
        classification: dict[str, Any] | None = None,
        generated_text: str = "",
        review: dict[str, Any] | None = None,
    ) -> None:
        self.actual_request_count = 0
        self.classification = classification or {
            "decision": "PASS",
            "target_account_match": "PASS",
            "target_audience_match": "PASS",
            "source_audience": "beginner_liver",
            "commercial_context": "B2C",
            "source_usage_fit": "PASS",
            "risk_flags": [],
            "reasons": [],
        }
        self.generated_text = generated_text
        self.review = review or {
            "decision": "PASS",
            "natural_japanese": "PASS",
            "source_grounding": "PASS",
            "account_fit": "PASS",
            "public_safety": "PASS",
            "voice_persona": "PASS",
            "voice_persona_score": 95,
            "identity_fit": "PASS",
            "interpersonal_distance": "PASS",
            "register_fit": "PASS",
            "conversational_naturalness": "PASS",
            "risk_flags": [],
            "reasons": [],
        }

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.actual_request_count += 1
        operation = kwargs["operation"]
        if operation == "classify":
            data = self.classification
        elif operation == "generate":
            data = {
                "public_post_text": self.generated_text,
                "preserved_facts": [],
                "removed_noise": [],
                "notes": "fixture",
            }
        else:
            data = self.review
        return {"data": data, "actual_requests": 1, "cache_hit": False}


def base_queue() -> dict[str, Any]:
    return {
        "queue_id": "q_fixture",
        "account_id": "liver_manager",
        "target_account_id": "liver_manager",
        "platform": "threads",
        "generation_mode": "direct_reference_media",
        "transformation_type": "source_copyedit",
        "media_origin": "direct_reference",
        "public_post_text": "配信が崩れそうって不安になるよね。そんな時は、リスナー皆んなでで支えられる一言を次の配信で試してみてね。",
        "source_post_id": "sp_fixture",
        "rights_status": "allowed",
        "permission_status": "granted",
    }


def source_context() -> dict[str, Any]:
    return {
        "original_post_text": base_queue()["public_post_text"],
        "permission_evidence_status": "APPROVED",
        "classifier_model": "fixture-classifier",
        "generator_model": "fixture-generator",
        "review_model": "fixture-review",
        "read_errors": [],
    }


def main() -> None:
    stale_direct_draft = "STALE_MUTABLE_DRAFT_MUST_NOT_CLASSIFY_SOURCE"
    direct_prompt = _classification_prompt(
        {
            "queue_id": "q_direct_stale_draft",
            "account_id": "liver_manager",
            "target_account_id": "liver_manager",
            "generation_mode": "direct_reference_media",
            "media_origin": "direct_reference",
            "public_post_text": stale_direct_draft,
        },
        {
            "original_post_text": "配信でリスナーへ挨拶する話",
            "transcript_excerpt": "初見が入室した時の声かけ",
        },
        {},
    )
    assert stale_direct_draft not in direct_prompt

    current_text = "CURRENT_TEXT_REMAINS_FOR_TEXT_CLASSIFICATION"
    text_prompt = _classification_prompt(
        {
            "queue_id": "q_new_text",
            "account_id": "liver_manager",
            "target_account_id": "liver_manager",
            "generation_mode": "new_text_generation",
            "public_post_text": current_text,
        },
        {},
        {},
    )
    assert current_text in text_prompt

    corrected = "配信が崩れそうって不安になるよね。そんな時は、リスナーみんなで支えられる一言を次の配信で試してみてね。"
    context = source_context()
    result = HybridAiGate(FakeClient(generated_text=corrected)).evaluate(base_queue(), context)
    assert result.status == "PASS", result.audit()
    assert "でで" not in result.public_post_text
    assert result.actual_requests == 3

    transform_queue = {
        **base_queue(),
        "caption_mode": "transform",
        "transformation_type": "transform",
    }
    transform_text = generate_reader_facing_post(
        "liver_manager",
        3,
    )["public_post_text"]
    transform_result = HybridAiGate(
        FakeClient(generated_text=transform_text)
    ).evaluate(transform_queue, context)
    assert transform_result.status == "PASS", transform_result.audit()
    assert transform_result.route == "external_direct_transform"
    assert transform_result.deterministic_validation["source_copyedit_contract"] == {}

    inconsistent = {
        "decision": "PASS",
        "target_account_match": "PASS",
        "target_audience_match": "PASS",
        "source_audience": "agency_owner",
        "commercial_context": "B2B_SALES",
        "source_usage_fit": "PASS",
        "risk_flags": [],
        "reasons": [],
    }
    blocked_context = HybridAiGate(
        FakeClient(classification=inconsistent, generated_text=corrected)
    ).evaluate(base_queue(), context)
    assert blocked_context.status == "BLOCKED"
    assert "ai_blocked_source_audience" in blocked_context.blocked_reasons
    assert "ai_blocked_commercial_context" in blocked_context.blocked_reasons

    reference_only = HybridAiGate(FakeClient(generated_text=corrected)).evaluate(
        base_queue(),
        {
            **context,
            "use_policy": "REFERENCE_ONLY",
            "permission_evidence_status": "MISSING",
        },
    )
    assert reference_only.status == "BLOCKED"
    assert "reference_only_media_reuse_blocked" in reference_only.blocked_reasons
    assert reference_only.actual_requests == 0

    denied = base_queue()
    denied["permission_status"] = "denied"
    denied_result = HybridAiGate(FakeClient(generated_text=corrected)).evaluate(denied, context)
    assert denied_result.status == "BLOCKED"
    assert "permission_denied" in denied_result.blocked_reasons
    assert denied_result.actual_requests == 0

    mismatched_context = {**context, "source_target_account_id": "night_scout"}
    mismatch_result = HybridAiGate(FakeClient(generated_text=corrected)).evaluate(
        base_queue(), mismatched_context
    )
    assert mismatch_result.status == "BLOCKED"
    assert "source_target_account_mismatch" in mismatch_result.blocked_reasons

    income_queue = base_queue()
    income_queue.update(
        {
            "generation_mode": "reference_text",
            "transformation_type": "transform",
            "media_origin": "",
            "rights_status": "",
            "permission_status": "",
        }
    )
    income_result = HybridAiGate(
        FakeClient(generated_text="配信未経験から月収500万円を達成できます。")
    ).evaluate(income_queue, {**context, "source_text": "配信事務所の説明"})
    assert income_result.status == "BLOCKED"
    assert "unverified_income_amount_present" in income_result.blocked_reasons

    template_result = HybridAiGate(
        FakeClient(generated_text="配信を続ける時に確認することは一つ。毎週の配信時間を先に決めてください。")
    ).evaluate(income_queue, {**context, "source_text": "配信時間を決める話"})
    assert template_result.status == "BLOCKED"
    assert "generic_template_phrase_present" in template_result.blocked_reasons

    passed_queue = base_queue()
    passed_queue["public_post_text"] = result.public_post_text
    passed_queue["generation_policy_json"] = merge_gate_audit("", result)
    ok, reason = hybrid_ai_gate_passed(passed_queue, context)
    assert ok is True and reason == "pass"
    current, status = hybrid_ai_gate_current(passed_queue, context)
    assert current is True and status == "pass"

    stale_prompt_policy = json.loads(passed_queue["generation_policy_json"])
    stale_prompt_policy["hybrid_ai_gate"]["prompt_version"] = (
        "hybrid_ai_prompts_previous"
    )
    stale_prompt_queue = {
        **passed_queue,
        "generation_policy_json": json.dumps(
            stale_prompt_policy,
            ensure_ascii=False,
            sort_keys=True,
        ),
    }
    current, reason = hybrid_ai_gate_current(stale_prompt_queue, context)
    assert current is False and reason == "prompt_stale"

    changed_route = dict(passed_queue)
    changed_route["transformation_type"] = "transform"
    changed_route["caption_mode"] = "transform"
    changed_route["generation_policy_json"] = passed_queue["generation_policy_json"]
    current, reason = hybrid_ai_gate_current(changed_route, context)
    assert current is False and reason == "route_stale"

    changed_queue = dict(passed_queue)
    changed_queue["public_post_text"] += "変更"
    ok, reason = hybrid_ai_gate_passed(changed_queue, context)
    assert ok is False and reason == "input_hash_stale"

    changed_context = {**context, "use_policy": "REFERENCE_ONLY"}
    ok, reason = hybrid_ai_gate_passed(passed_queue, changed_context)
    assert ok is False and reason == "source_context_stale"

    beauty_text = (
        "スキンケアを一度に変えたくなる時って\n"
        "ほんとに何から試すか迷うんだよね🥺\n\n"
        "個人的には、まず一つだけ変えるのが結構大事\n"
        "肌の変化と理由を分けて見やすい気がする💭\n\n"
        "使い始めた日をメモして\n"
        "その他はいつも通りで試してみてほしい🤍"
    )
    beauty_queue = {
        "queue_id": "q_beauty_fixture",
        "account_id": "beauty_account",
        "target_account_id": "beauty_account",
        "platform": "threads",
        "generation_mode": "beauty_new_text_generation",
        "content_type": "new_text_generation",
        "public_post_text": beauty_text,
    }
    beauty_classification = {
        "decision": "PASS",
        "target_account_match": "PASS",
        "target_audience_match": "PASS",
        "source_audience": "beauty_cosmetics_women_20s_30s",
        "commercial_context": "B2C",
        "source_usage_fit": "PASS",
        "risk_flags": [],
        "reasons": [],
    }
    beauty_result = HybridAiGate(
        FakeClient(classification=beauty_classification, generated_text=beauty_text)
    ).evaluate(beauty_queue, {**context, "source_text": beauty_text})
    assert beauty_result.status == "PASS", beauty_result.audit()
    assert beauty_result.review["voice_persona"] == "PASS"

    beauty_prepared = {
        **beauty_queue,
        "generated_by": "prepare_beauty_review_candidates.py",
        "semantic_voice_status": "PENDING_HYBRID_AI_REVIEW",
    }
    rewrite_attempt = "全然違うと私自身は感じました。"
    review_only_client = FakeClient(
        classification=beauty_classification,
        generated_text=rewrite_attempt,
    )
    beauty_review_only = HybridAiGate(review_only_client).evaluate(
        beauty_prepared,
        {**context, "source_text": beauty_text},
    )
    assert beauty_review_only.status == "PASS", beauty_review_only.audit()
    assert beauty_review_only.route == "semantic_review"
    assert beauty_review_only.public_post_text == beauty_text
    assert beauty_review_only.generation == {}
    assert review_only_client.actual_request_count == 2

    reviewed_beauty_queue = {
        **beauty_prepared,
        "generated_by": "hybrid_ai_gate_v4",
        "semantic_voice_status": "PASS",
        "generation_policy_json": merge_gate_audit("", beauty_review_only),
    }
    current, reason = hybrid_ai_gate_current(
        reviewed_beauty_queue,
        {**context, "source_text": beauty_text},
    )
    assert current is True and reason == "pass"

    stale_route_queue = dict(beauty_prepared)
    stale_route_queue["generation_policy_json"] = merge_gate_audit("", beauty_result)
    current, reason = hybrid_ai_gate_current(
        stale_route_queue,
        {**context, "source_text": beauty_text},
    )
    assert current is False and reason == "route_stale"
    assert beauty_result.deterministic_validation["public_validation"]["voice_persona_check"]["style_profile_version"] == "chadult_beauty_voice_v1"

    beauty_reference = {
        **beauty_queue,
        "generation_mode": "beauty_reference_text_generation",
        "content_type": "reference_text_generation",
    }
    missing_lineage = HybridAiGate(
        FakeClient(classification=beauty_classification, generated_text=beauty_text)
    ).evaluate(beauty_reference, {**context, "source_text": beauty_text})
    assert missing_lineage.status == "BLOCKED"
    assert "beauty_reference_lineage_missing" in missing_lineage.blocked_reasons

    beauty_pdca = {
        **beauty_queue,
        "generation_mode": "beauty_pdca_text_generation",
        "content_type": "pdca_text_generation",
        "pdca_result_id": "beauty_result_1",
        "pdca_account_scope": "liver_manager",
    }
    wrong_scope = HybridAiGate(
        FakeClient(classification=beauty_classification, generated_text=beauty_text)
    ).evaluate(beauty_pdca, {**context, "source_text": beauty_text})
    assert wrong_scope.status == "BLOCKED"
    assert "beauty_pdca_account_scope_missing" in wrong_scope.blocked_reasons

    print("PASS hybrid AI gate including Beauty lineage and PDCA isolation")


if __name__ == "__main__":
    main()
