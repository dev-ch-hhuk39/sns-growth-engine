#!/usr/bin/env python3
"""Common semantic, generation and final-review gate for Threads candidates."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from generation.source_copyedit import (
    evaluate_source_copyedit_contract,
    validate_source_preserving_public_post,
)
from hybrid_ai_policy import decide_route, requires_hybrid_ai_gate
from hybrid_ai_source_context import hybrid_ai_source_context_hash
from gemini_hybrid_client import provider_error_evidence, retryable_provider_error
from public_post_quality import canonical_voice_profile, canonical_voice_prompt, final_public_post_validator

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/hybrid_ai_account_policies.json"
GATE_SCHEMA_VERSION = "hybrid_ai_gate_v4"
PROMPT_VERSION = "hybrid_ai_prompts_v7"

GENERIC_TEMPLATE_PHRASES = (
    "確認することは一つ。",
    "この順番で考える理由はシンプル。",
    "見るポイントは次の通り。",
    "次に試すこと：",
)

SCHEDULED_TEXT_TYPES = {
    "original_text",
    "reference_text",
    "pdca_text",
    "metrics_driven_pdca_text",
    "new_text_generation",
    "reference_text_generation",
    "pdca_text_generation",
    "direct_reference_media",
}


def _scheduled_text_type(queue: Mapping[str, Any]) -> str:
    return _text(queue.get("content_type") or queue.get("generation_mode")).lower()


def _scheduled_text_contract_reasons(
    queue: Mapping[str, Any],
    text: str,
) -> list[str]:
    """Validate account voice while keeping PDCA evidence internal."""

    content_type = _scheduled_text_type(queue)
    if content_type not in SCHEDULED_TEXT_TYPES:
        return []
    value = _text(text)
    reasons: list[str] = []
    if _text(queue.get("account_id")) == "night_scout" and "僕" not in value:
        reasons.append("night_scout_first_person_boku_missing")
    if content_type in {"pdca_text", "metrics_driven_pdca_text", "pdca_text_generation"}:
        public_process_terms = (
            "前回の投稿", "実測", "PDCA", "反応理由", "次回検証",
            "表示数", "いいね数", "コメント数", "成果を分析",
        )
        if any(term in value for term in public_process_terms):
            reasons.append("pdca_internal_learning_exposed_in_public_text")
    return sorted(set(reasons))


def _scheduled_text_contract_instruction(queue: Mapping[str, Any]) -> str:
    instructions: list[str] = []
    content_type = _scheduled_text_type(queue)
    if content_type not in SCHEDULED_TEXT_TYPES:
        return ""
    if _text(queue.get("account_id")) == "night_scout":
        instructions.append("最終本文では一人称の『僕』を少なくとも一度残してください。")
    voice_contract = canonical_voice_prompt(_text(queue.get("account_id")))
    if voice_contract:
        instructions.append("アカウント音声契約: " + voice_contract)
    if content_type in {"pdca_text", "metrics_driven_pdca_text", "pdca_text_generation"}:
        instructions.append(
            "metrics、過去投稿、仮説、検証計画は内部学習にだけ使い、"
            "公開本文で言及しないでください。学習結果を反映した、独立した通常の新規投稿にしてください。"
        )
    return ("追加必須条件: " + "".join(instructions)) if instructions else ""


def _repair_night_scout_first_person(text: str) -> str:
    value = _text(text)
    if not value or "僕" in value:
        return value
    return f"僕なら、{value}"


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision",
        "target_account_match",
        "target_audience_match",
        "source_audience",
        "commercial_context",
        "source_usage_fit",
        "risk_flags",
        "reasons",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REJECT"]},
        "target_account_match": {"type": "string", "enum": ["PASS", "FAIL"]},
        "target_audience_match": {"type": "string", "enum": ["PASS", "FAIL"]},
        "source_audience": {"type": "string"},
        "commercial_context": {"type": "string"},
        "source_usage_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}
GENERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["public_post_text", "preserved_facts", "removed_noise", "notes"],
    "properties": {
        "public_post_text": {"type": "string", "minLength": 20},
        "preserved_facts": {"type": "array", "items": {"type": "string"}},
        "removed_noise": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
}
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision",
        "natural_japanese",
        "source_grounding",
        "account_fit",
        "public_safety",
        "voice_persona",
        "voice_persona_score",
        "identity_fit",
        "interpersonal_distance",
        "register_fit",
        "conversational_naturalness",
        "risk_flags",
        "reasons",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REJECT"]},
        "natural_japanese": {"type": "string", "enum": ["PASS", "FAIL"]},
        "source_grounding": {"type": "string", "enum": ["PASS", "FAIL"]},
        "account_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "public_safety": {"type": "string", "enum": ["PASS", "FAIL"]},
        "voice_persona": {"type": "string", "enum": ["PASS", "FAIL"]},
        "voice_persona_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "identity_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "interpersonal_distance": {"type": "string", "enum": ["PASS", "FAIL"]},
        "register_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "conversational_naturalness": {"type": "string", "enum": ["PASS", "FAIL"]},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass
class GateResult:
    status: str
    route: str
    public_post_text: str
    blocked_reasons: list[str]
    input_hash: str
    source_context_hash: str
    classification: dict[str, Any]
    generation: dict[str, Any]
    review: dict[str, Any]
    deterministic_validation: dict[str, Any]
    actual_requests: int
    provider_status: str
    provider_mode: str
    provider_error_type: str
    provider_http_status: str
    fallback_mode: str
    fallback_reason: str

    def audit(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = GATE_SCHEMA_VERSION
        data["prompt_version"] = PROMPT_VERSION
        return data


def load_account_policies(path: Path = POLICY_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw["accounts"])


def _text(value: Any) -> str:
    return str(value or "").strip()


def _queue_prompt_view(queue: Mapping[str, Any]) -> dict[str, str]:
    fields = (
        "queue_id",
        "account_id",
        "target_account_id",
        "generation_mode",
        "source_generation_mode",
        "transformation_type",
        "media_origin",
        "content_type",
        "source_id",
        "source_post_id",
        "source_video_id",
        "clip_candidate_id",
        "pdca_account_scope",
        "pdca_result_id",
        "rights_status",
        "permission_status",
        "public_post_text",
    )
    return {field: _text(queue.get(field)) for field in fields}


def hybrid_ai_input_hash(queue: Mapping[str, Any]) -> str:
    fields = (
        "queue_id",
        "account_id",
        "target_account_id",
        "platform",
        "generation_mode",
        "source_generation_mode",
        "transformation_type",
        "media_origin",
        "content_type",
        "source_id",
        "source_post_id",
        "source_video_id",
        "clip_candidate_id",
        "media_asset_id",
        "media_asset_ids_json",
        "public_post_text",
        "rights_status",
        "permission_status",
        "rights_review_required",
        "media_reuse_risk",
        "claim_support_json",
        "content_hash",
        "source_url",
        "source_time_range",
        "pdca_account_scope",
        "pdca_result_id",
    )
    payload = {field: _text(queue.get(field)) for field in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persisted_hybrid_ai_gate(queue: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = _text(queue.get("generation_policy_json"))
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    gate = value.get("hybrid_ai_gate") if isinstance(value, dict) else None
    return gate if isinstance(gate, dict) else None


def hybrid_ai_gate_current(
    queue: Mapping[str, Any],
    source_context: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    if not requires_hybrid_ai_gate(queue):
        return True, "not_required"
    gate = persisted_hybrid_ai_gate(queue)
    if gate is None:
        return False, "missing"
    if gate.get("schema_version") != GATE_SCHEMA_VERSION:
        return False, "schema_stale"
    if gate.get("prompt_version") != PROMPT_VERSION:
        return False, "prompt_stale"
    expected_route = decide_route(queue).route
    if gate.get("route") != expected_route:
        return False, "route_stale"
    if gate.get("input_hash") != hybrid_ai_input_hash(queue):
        return False, "input_hash_stale"
    if source_context is None:
        return False, "source_context_required"
    if gate.get("source_context_hash") != hybrid_ai_source_context_hash(source_context):
        return False, "source_context_stale"
    status = _text(gate.get("status")).upper()
    if status not in {"PASS", "BLOCKED"}:
        return False, "status_invalid"
    provider_mode = _text(gate.get("provider_mode"))
    if provider_mode == "deterministic_local_strict":
        deterministic = gate.get("deterministic_validation")
        if not isinstance(deterministic, dict):
            return False, "deterministic_evidence_missing"
        if _text(deterministic.get("status")).upper() != status:
            return False, "deterministic_status_mismatch"
        if _text(gate.get("provider_status")).upper() != "UNAVAILABLE":
            return False, "fallback_provider_status_invalid"
        if not _text(gate.get("fallback_reason")):
            return False, "fallback_reason_missing"
    elif provider_mode != "gemini":
        return False, "provider_mode_invalid"
    return True, status.lower()


def hybrid_ai_gate_passed(
    queue: Mapping[str, Any],
    source_context: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    current, reason = hybrid_ai_gate_current(queue, source_context)
    if not current:
        return False, reason
    if reason == "not_required":
        return True, reason
    if reason != "pass":
        return False, "not_pass"
    return True, "pass"


def _source_text(queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> str:
    candidates = (
        source_context.get("original_post_text"),
        source_context.get("transcript_excerpt"),
        source_context.get("transcript"),
        source_context.get("description"),
        source_context.get("source_text"),
        queue.get("public_post_text"),
    )
    seen: list[str] = []
    for value in candidates:
        text = _text(value)
        if text and text not in seen:
            seen.append(text)
    return "\n\n".join(seen)[:16000]


def _hygiene_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    if re.search(r"\[(?:音楽|拍手|BGM|笑い|無音)\]", text, flags=re.IGNORECASE):
        reasons.append("transcript_stage_direction_present")
    if "ライバの排出" in text or re.search(r"ライバー[^。\n]{0,12}排出", text):
        reasons.append("known_transcription_error_present")
    if re.search(r"(?:でで|がが|をを|にに|はは|もも)(?:[、。！!？?]|$)", text):
        reasons.append("duplicate_particle_present")
    if re.search(r"(?:月収|年収)\s*[0-9０-９,，]+\s*万?円?", text):
        reasons.append("unverified_income_amount_present")
    if re.search(r"[0-9０-９,，]+\s*万円[^。\n]{0,20}(?:稼|達成)", text):
        reasons.append("unverified_income_achievement_present")
    if any(phrase in text for phrase in GENERIC_TEMPLATE_PHRASES):
        reasons.append("generic_template_phrase_present")
    return reasons


def _is_true(value: Any) -> bool:
    return _text(value).lower() in {"true", "1", "yes", "y"}


def _preflight(queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    account_id = _text(queue.get("account_id"))
    target_account_id = _text(queue.get("target_account_id"))
    if target_account_id and target_account_id != account_id:
        reasons.append("target_account_mismatch")
    source_target = _text(source_context.get("source_target_account_id"))
    if source_target and source_target != account_id:
        reasons.append("source_target_account_mismatch")
    if source_context.get("read_errors"):
        reasons.append("source_context_read_failed")
    if _is_true(queue.get("excluded_from_activation")):
        reasons.append("excluded_from_activation")
    if _is_true(queue.get("repost_prohibited")):
        reasons.append("repost_prohibited")

    content_type = _scheduled_text_type(queue)
    if account_id == "beauty_account":
        if content_type == "reference_text_generation":
            if not _text(queue.get("source_id")) or not _text(queue.get("source_post_id")):
                reasons.append("beauty_reference_lineage_missing")
            if source_target != "beauty_account":
                reasons.append("beauty_reference_account_isolation_failed")
        if content_type == "pdca_text_generation":
            if _text(queue.get("pdca_account_scope")) != "beauty_account":
                reasons.append("beauty_pdca_account_scope_missing")
            if not _text(queue.get("pdca_result_id")):
                reasons.append("beauty_measured_pdca_lineage_missing")

    route = decide_route(queue).route
    media_route = route in {
        "external_direct_source_copyedit",
        "external_direct_transform",
        "owned_media_transform",
        "approved_clip_transform",
    }
    rights_status = _text(queue.get("rights_status")).lower()
    permission_status = _text(queue.get("permission_status")).lower()
    if rights_status in {"not_allowed", "denied", "blocked"}:
        reasons.append("rights_not_allowed")
    if permission_status in {"not_allowed", "denied", "blocked"}:
        reasons.append("permission_denied")
    if media_route and _is_true(queue.get("rights_review_required")):
        reasons.append("rights_review_required")
    if media_route and rights_status == "unknown" and permission_status not in {"granted", "not_required"}:
        reasons.append("rights_unverified")

    policies = {
        _text(source_context.get("use_policy")).upper(),
        _text(source_context.get("usage_scope")).upper(),
        _text(source_context.get("reuse_policy")).upper(),
    }
    permission_evidence = _text(source_context.get("permission_evidence_status")).upper()
    external_permission_route = route in {
        "external_direct_source_copyedit",
        "external_direct_transform",
        "approved_clip_transform",
    }
    if media_route and "REFERENCE_ONLY" in policies and permission_evidence != "APPROVED":
        reasons.append("reference_only_media_reuse_blocked")
    if external_permission_route and permission_evidence in {"", "MISSING", "DENIED"}:
        reasons.append("media_permission_evidence_missing_or_denied")
    if not _text(queue.get("public_post_text")) and route == "external_direct_source_copyedit":
        reasons.append("source_copyedit_text_missing")
    if route in {"external_direct_source_copyedit", "external_direct_transform"} and not _text(source_context.get("original_post_text")):
        reasons.append("direct_source_post_text_missing")
    if route == "approved_clip_transform":
        excerpt = _text(source_context.get("transcript_excerpt"))
        if not _text(queue.get("clip_candidate_id")):
            reasons.append("clip_candidate_id_missing")
        if not _text(queue.get("source_video_id")):
            reasons.append("source_video_id_missing")
        if not excerpt:
            reasons.append("clip_transcript_evidence_missing")
        if re.search(r"\[(?:音楽|拍手|BGM|笑い|無音)\]", excerpt, flags=re.IGNORECASE):
            reasons.append("clip_transcript_noise_present")
        try:
            duration = float(_text(source_context.get("clip_duration_seconds")) or 0)
        except ValueError:
            duration = 0.0
        if duration and not 12.0 <= duration <= 45.0:
            reasons.append("clip_duration_out_of_review_range")
        if not _text(source_context.get("clip_start_seconds")) or not _text(source_context.get("clip_end_seconds")):
            reasons.append("clip_exact_time_range_missing")
    if not _source_text(queue, source_context):
        reasons.append("source_evidence_missing")
    return sorted(set(reasons))


def _classification_prompt(
    queue: Mapping[str, Any],
    source_context: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    queue_view = _queue_prompt_view(queue)
    if decide_route(queue).route in {
        "external_direct_source_copyedit",
        "external_direct_transform",
    }:
        # Direct-media classification evaluates immutable source evidence. The
        # mutable draft is regenerated and reviewed by the later quality gates.
        queue_view.pop("public_post_text", None)
    source_view = {
        key: source_context.get(key)
        for key in (
            "source_id",
            "original_post_text",
            "transcript_excerpt",
            "transcript",
            "description",
            "source_text",
            "use_policy",
            "usage_scope",
            "reuse_policy",
            "source_target_account_id",
            "permission_evidence_status",
            "clip_duration_seconds",
            "clip_start_seconds",
            "clip_end_seconds",
        )
    }
    return (
        "あなたはSNS投稿候補の適合性審査担当です。文章生成はしません。"
        "対象アカウント、想定読者、BtoB/BtoC、参照元の利用目的を厳格に判定してください。"
        "店舗経営者・事業者向け素材を求職者向けへ無理に変換する場合、他社宣伝、"
        "根拠不明の収益実績、対象アカウント違いはREJECTしてください。\n\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"QUEUE={json.dumps(queue_view, ensure_ascii=False, sort_keys=True)}\n"
        f"SOURCE_CONTEXT={json.dumps(source_view, ensure_ascii=False, sort_keys=True)}"
    )


def _generation_prompt(
    route: str,
    queue: Mapping[str, Any],
    source_text: str,
    policy: Mapping[str, Any],
) -> str:
    if route == "external_direct_source_copyedit":
        instruction = (
            "元投稿の主張、固有情報、話者の温度感を維持し、誤字、重複助詞、メンション、ハッシュタグ、"
            "文字起こしノイズだけを必要最小限で修正してください。新しい助言や事実は追加しないでください。"
            "元投稿者の経験、担当数、実績、商品使用などの一人称の事実を、対象アカウントの"
            "『僕』や『私』の事実に絶対に変換しないでください。その事実は『この動画では』『投稿者は』などと"
            "帰属を保ち、対象アカウントの一人称は助言や判断にだけ使ってください。"
        )
    else:
        instruction = (
            "参照根拠に書かれた事実だけを使い、対象読者に自然で具体的なThreads投稿を新規作成してください。"
            "BtoBの主張をBtoCに変換しない。他社の宣伝文や収益実績を自社の主張として使わない。"
            "定型句を避け、3段落程度で簡潔にしてください。"
        )
    contract_instruction = _scheduled_text_contract_instruction(queue)
    voice_profile = canonical_voice_profile(_text(queue.get("account_id")))
    return (
        f"{instruction}"
        f"{(' ' + contract_instruction) if contract_instruction else ''}\n\n"
        f"ROUTE={route}\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"CANONICAL_VOICE_PROFILE={json.dumps(voice_profile, ensure_ascii=False, sort_keys=True)}\n"
        f"CURRENT_QUEUE_TEXT={_text(queue.get('public_post_text'))}\n"
        f"SOURCE_EVIDENCE={source_text}"
    )


def _review_prompt(
    queue: Mapping[str, Any],
    source_text: str,
    candidate_text: str,
    policy: Mapping[str, Any],
) -> str:
    pdca_instruction = ""
    if (
        _scheduled_text_type(queue) in {"pdca_text", "metrics_driven_pdca_text"}
        and _text(queue.get("generation_mode")).lower() == "metrics_driven_pdca_text"
    ):
        pdca_instruction = (
            "この候補はPDCA枠ですが、SOURCE_EVIDENCEのmetrics、過去投稿、仮説、"
            "検証計画は内部学習のみに使います。公開本文は、過去投稿や数値に言及しない"
            "独立した通常の新規コンテンツでなければREJECTしてください。"
        )
    return (
        "公開直前のSNS投稿を厳格に審査してください。自然な日本語、参照根拠への忠実性、"
        "対象読者・アカウント適合、公開安全性を確認してください。誤字、重複助詞、[音楽]等、"
        "定型句、根拠不明の収益額、他社宣伝、BtoB/BtoC不一致はREJECTしてください。"
        "参照元投稿者の経験・担当数・実績・商品使用を、対象アカウント自身の一人称の事実として"
        "語る候補はREJECTしてください。"
        f"{(' ' + pdca_instruction) if pdca_instruction else ''}\n\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"CANONICAL_VOICE_PROFILE={json.dumps(canonical_voice_profile(_text(queue.get('account_id'))), ensure_ascii=False, sort_keys=True)}\n"
        f"QUEUE_ID={_text(queue.get('queue_id'))}\n"
        f"SOURCE_EVIDENCE={source_text}\n"
        f"CANDIDATE_TEXT={candidate_text}"
    )


def _blocked_context(classification: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    blocked_audiences = {
        _text(item).lower()
        for item in policy.get("blocked_source_audiences", [])
        if _text(item)
    }
    source_audience = _text(classification.get("source_audience")).lower()
    if source_audience and source_audience in blocked_audiences:
        reasons.append("ai_blocked_source_audience")

    blocked_contexts = {
        _text(item).upper()
        for item in policy.get("blocked_contexts", [])
        if _text(item)
    }
    commercial_context = _text(classification.get("commercial_context")).upper()
    if commercial_context in blocked_contexts:
        reasons.append("ai_blocked_commercial_context")
    elif commercial_context.startswith("B2B") and any(item.startswith("B2B") for item in blocked_contexts):
        reasons.append("ai_blocked_commercial_context")
    return reasons


class HybridAiGate:
    def __init__(self, client: Any, policies: Mapping[str, Any] | None = None) -> None:
        self.client = client
        self.policies = dict(policies or load_account_policies())

    def _result(
        self,
        *,
        status: str,
        route: str,
        public_post_text: str,
        blocked_reasons: list[str],
        input_hash: str,
        source_context_hash: str,
        classification: dict[str, Any] | None = None,
        generation: dict[str, Any] | None = None,
        review: dict[str, Any] | None = None,
        deterministic_validation: dict[str, Any] | None = None,
        actual_requests: int = 0,
        provider_status: str = "AVAILABLE",
        provider_mode: str = "gemini",
        provider_error_type: str = "",
        provider_http_status: str = "",
        fallback_mode: str = "",
        fallback_reason: str = "",
    ) -> GateResult:
        return GateResult(
            status=status,
            route=route,
            public_post_text=public_post_text,
            blocked_reasons=sorted(set(blocked_reasons)),
            input_hash=input_hash,
            source_context_hash=source_context_hash,
            classification=classification or {},
            generation=generation or {},
            review=review or {},
            deterministic_validation=deterministic_validation or {},
            actual_requests=actual_requests,
            provider_status=provider_status,
            provider_mode=provider_mode,
            provider_error_type=provider_error_type,
            provider_http_status=str(provider_http_status or ""),
            fallback_mode=fallback_mode,
            fallback_reason=fallback_reason,
        )

    def evaluate(self, queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> GateResult:
        """Use Gemini when available and strict local evidence on transient outage."""

        before_requests = int(getattr(self.client, "actual_request_count", 0))
        try:
            return self._evaluate_with_provider(queue, source_context)
        except Exception as exc:
            if not retryable_provider_error(exc):
                raise
            evidence = provider_error_evidence(exc)
            return self._deterministic_fallback(
                queue,
                source_context,
                evidence=evidence,
                actual_requests=(
                    int(getattr(self.client, "actual_request_count", 0))
                    - before_requests
                ),
            )

    def _deterministic_fallback(
        self,
        queue: Mapping[str, Any],
        source_context: Mapping[str, Any],
        *,
        evidence: Mapping[str, Any],
        actual_requests: int,
    ) -> GateResult:
        route = decide_route(queue)
        account_id = _text(queue.get("account_id"))
        current_text = _text(queue.get("public_post_text"))
        source_text = _source_text(queue, source_context)
        initial_hash = hybrid_ai_input_hash(queue)
        source_hash = hybrid_ai_source_context_hash(source_context)
        reasons = _preflight(queue, source_context)
        reasons.extend(_scheduled_text_contract_reasons(queue, current_text))
        reasons.extend(_hygiene_reasons(current_text))

        public_validation = (
            validate_source_preserving_public_post(current_text, account_id)
            if route.route == "external_direct_source_copyedit"
            else final_public_post_validator(current_text, account_id)
        )
        if public_validation.get("status") != "PASS":
            reasons.extend(str(item) for item in public_validation.get("blocked_reasons", []))

        source_contract: dict[str, Any] = {}
        if route.route == "external_direct_source_copyedit":
            source_contract = evaluate_source_copyedit_contract(
                source_text=source_text,
                public_post_text=current_text,
                account_id=account_id,
                recent_posts=[],
            )
            if source_contract.get("status") != "PASS":
                reasons.extend(str(item) for item in source_contract.get("blocked_reasons", []))

        persisted_statuses = {
            field: _text(queue.get(field)).upper()
            for field in ("validator_status", "internal_leak_status", "account_fit_status")
        }
        for field, status in persisted_statuses.items():
            if status and status != "PASS":
                reasons.append(f"persisted_{field}_not_pass")

        media_validation: dict[str, Any] = {}
        media_route = route.route in {
            "external_direct_source_copyedit",
            "external_direct_transform",
            "owned_media_transform",
            "approved_clip_transform",
        }
        identity_evidence = {
            field: _text(source_context.get(field)).upper()
            for field in (
                "source_author_identity_status",
                "source_parent_identity_status",
                "source_media_parent_status",
                "source_media_order_status",
                "provenance_status",
            )
        }
        if media_route:
            for field in (
                "source_author_identity_status",
                "source_parent_identity_status",
                "provenance_status",
            ):
                if identity_evidence.get(field) != "PASS":
                    reasons.append(f"{field}_not_pass")
            if route.route in {"external_direct_source_copyedit", "external_direct_transform"}:
                for field in ("source_media_parent_status", "source_media_order_status"):
                    if identity_evidence.get(field) != "PASS":
                        reasons.append(f"{field}_not_pass")
            media_plan = dict(queue)
            media_plan["public_post_text"] = current_text
            media_plan.setdefault("caption_mode", queue.get("transformation_type", "transform"))
            raw_urls = queue.get("media_urls_json")
            if raw_urls and not media_plan.get("media_urls"):
                try:
                    parsed_urls = json.loads(_text(raw_urls))
                except json.JSONDecodeError:
                    parsed_urls = []
                media_plan["media_urls"] = parsed_urls if isinstance(parsed_urls, list) else []
            from media_post_validator import validate_media_post

            media_validation = validate_media_post(media_plan)
            if media_validation.get("status") != "PASS":
                reasons.extend(str(item) for item in media_validation.get("blocked_reasons", []))

        reasons = sorted(set(reasons))
        status = "PASS" if not reasons else "BLOCKED"
        voice = dict(public_validation.get("voice_persona_check", {}))
        review = {
            "decision": status,
            "natural_japanese": "PASS" if status == "PASS" else "FAIL",
            "source_grounding": "PASS" if not reasons else "FAIL",
            "account_fit": "PASS" if public_validation.get("account_fit_check", {}).get("status") == "PASS" else "FAIL",
            "public_safety": "PASS" if public_validation.get("status") == "PASS" else "FAIL",
            "voice_persona": "PASS" if voice.get("status") == "VOICE_PERSONA_PASS" else "FAIL",
            "voice_persona_score": int(voice.get("score", 0) or 0),
            "identity_fit": "PASS" if identity_evidence.get("source_author_identity_status", "PASS") == "PASS" else "FAIL",
            "interpersonal_distance": "PASS" if status == "PASS" else "FAIL",
            "register_fit": "PASS" if status == "PASS" else "FAIL",
            "conversational_naturalness": "PASS" if status == "PASS" else "FAIL",
            "risk_flags": reasons,
            "reasons": reasons,
            "review_provider": "deterministic_local_strict",
        }
        deterministic = {
            "status": status,
            "preflight": _preflight(queue, source_context),
            "blocked_reasons": reasons,
            "public_validation": public_validation,
            "source_copyedit_contract": source_contract,
            "persisted_statuses": persisted_statuses,
            "source_identity": identity_evidence,
            "media_validation": media_validation,
        }
        error_type = _text(evidence.get("provider_error_type"))
        http_status = _text(evidence.get("provider_http_status"))
        fallback_reason = (
            "gemini_retryable_http_unavailable"
            if error_type == "RETRYABLE_HTTP"
            else "gemini_transient_transport_unavailable"
        )
        return self._result(
            status=status,
            route=route.route,
            public_post_text=current_text,
            blocked_reasons=reasons,
            input_hash=initial_hash,
            source_context_hash=source_hash,
            review=review,
            deterministic_validation=deterministic,
            actual_requests=actual_requests,
            provider_status="UNAVAILABLE",
            provider_mode="deterministic_local_strict",
            provider_error_type=error_type,
            provider_http_status=http_status,
            fallback_mode="deterministic_strict",
            fallback_reason=fallback_reason,
        )

    def _evaluate_with_provider(self, queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> GateResult:
        route = decide_route(queue)
        account_id = _text(queue.get("account_id"))
        policy = self.policies.get(account_id)
        initial_hash = hybrid_ai_input_hash(queue)
        source_hash = hybrid_ai_source_context_hash(source_context)
        current_text = _text(queue.get("public_post_text"))
        if not policy:
            return self._result(
                status="BLOCKED",
                route=route.route,
                public_post_text=current_text,
                blocked_reasons=["account_policy_missing"],
                input_hash=initial_hash,
                source_context_hash=source_hash,
            )

        preflight = _preflight(queue, source_context)
        if preflight:
            return self._result(
                status="BLOCKED",
                route=route.route,
                public_post_text=current_text,
                blocked_reasons=preflight,
                input_hash=initial_hash,
                source_context_hash=source_hash,
                deterministic_validation={"preflight": preflight},
            )

        source_text = _source_text(queue, source_context)
        before_requests = int(getattr(self.client, "actual_request_count", 0))
        classify_response = self.client.generate_json(
            model=_text(source_context.get("classifier_model")) or "gemini-3.1-flash-lite",
            prompt=_classification_prompt(queue, source_context, policy),
            schema=CLASSIFICATION_SCHEMA,
            operation="classify",
            account_id=account_id,
            cache_context={
                "prompt_version": PROMPT_VERSION,
                "queue_hash": initial_hash,
                "source_context_hash": source_hash,
            },
        )
        classification = dict(classify_response["data"])
        classification_failures: list[str] = []
        if classification.get("decision") != "PASS":
            classification_failures.append("ai_classification_rejected")
        for field in ("target_account_match", "target_audience_match", "source_usage_fit"):
            if classification.get(field) != "PASS":
                classification_failures.append(f"ai_{field}_failed")
        classification_failures.extend(_blocked_context(classification, policy))
        classification_failures.extend(str(flag) for flag in classification.get("risk_flags", []))
        if classification_failures:
            used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
            return self._result(
                status="BLOCKED",
                route=route.route,
                public_post_text=current_text,
                blocked_reasons=classification_failures,
                input_hash=initial_hash,
                source_context_hash=source_hash,
                classification=classification,
                actual_requests=used,
            )

        generation: dict[str, Any] = {}
        candidate_text = current_text
        if route.generate:
            generate_response = self.client.generate_json(
                model=_text(source_context.get("generator_model")) or "gemini-3.5-flash",
                prompt=_generation_prompt(route.route, queue, source_text, policy),
                schema=GENERATION_SCHEMA,
                operation="generate",
                account_id=account_id,
                cache_context={
                    "prompt_version": PROMPT_VERSION,
                    "queue_hash": initial_hash,
                    "source_context_hash": source_hash,
                    "route": route.route,
                },
            )
            generation = dict(generate_response["data"])
            candidate_text = _text(generation.get("public_post_text"))

        if route.route in {"new_text_generation", "owned_media_transform", "external_direct_transform"}:
            generated_contract_reasons = _scheduled_text_contract_reasons(
                queue,
                candidate_text,
            )
            if generated_contract_reasons == ["night_scout_first_person_boku_missing"]:
                repaired_text = _repair_night_scout_first_person(candidate_text)
                repaired_validation = final_public_post_validator(repaired_text, account_id)
                repaired_reasons = (
                    _scheduled_text_contract_reasons(queue, repaired_text)
                    + _hygiene_reasons(repaired_text)
                    + (
                        []
                        if repaired_validation.get("status") == "PASS"
                        else [
                            str(reason)
                            for reason in repaired_validation.get("blocked_reasons", [])
                        ]
                    )
                )
                if not repaired_reasons:
                    candidate_text = repaired_text
                    generated_contract_reasons = []
                    generation["scheduled_text_contract"] = {
                        "status": "REPAIRED",
                        "repair": "night_scout_first_person_boku_prefix",
                        "fallback_to_current_queue_text": False,
                    }

            if generated_contract_reasons:
                fallback_text = current_text
                fallback_validation = final_public_post_validator(fallback_text, account_id)
                fallback_reasons = (
                    _scheduled_text_contract_reasons(queue, fallback_text)
                    + _hygiene_reasons(fallback_text)
                    + (
                        []
                        if fallback_validation.get("status") == "PASS"
                        else [
                            str(reason)
                            for reason in fallback_validation.get("blocked_reasons", [])
                        ]
                    )
                )
                if fallback_text and not fallback_reasons:
                    candidate_text = fallback_text
                    generation["scheduled_text_contract"] = {
                        "status": "FALLBACK_TO_VALIDATED_CURRENT_CANDIDATE",
                        "rejected_generated_contract_reasons": generated_contract_reasons,
                        "fallback_to_current_queue_text": True,
                    }
                else:
                    used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
                    final_queue = dict(queue)
                    final_queue["public_post_text"] = candidate_text
                    return self._result(
                        status="BLOCKED",
                        route=route.route,
                        public_post_text=candidate_text,
                        blocked_reasons=(
                            generated_contract_reasons
                            + [f"fallback_{reason}" for reason in fallback_reasons]
                        ),
                        input_hash=hybrid_ai_input_hash(final_queue),
                        source_context_hash=source_hash,
                        classification=classification,
                        generation=generation,
                        deterministic_validation={
                            "scheduled_text_contract": {
                                "generated_reasons": generated_contract_reasons,
                                "fallback_reasons": fallback_reasons,
                            }
                        },
                        actual_requests=used,
                    )

        deterministic_reasons = _hygiene_reasons(candidate_text)
        public_validation = (
            validate_source_preserving_public_post(candidate_text, account_id)
            if route.route == "external_direct_source_copyedit"
            else final_public_post_validator(candidate_text, account_id)
        )
        if public_validation["status"] != "PASS":
            deterministic_reasons.extend(str(reason) for reason in public_validation.get("blocked_reasons", []))

        source_contract: dict[str, Any] = {}
        if route.route == "external_direct_source_copyedit":
            source_contract = evaluate_source_copyedit_contract(
                source_text=source_text,
                public_post_text=candidate_text,
                account_id=account_id,
                recent_posts=[],
            )
            if source_contract.get("status") != "PASS":
                deterministic_reasons.extend(str(reason) for reason in source_contract.get("blocked_reasons", []))

        deterministic = {
            "status": "PASS" if not deterministic_reasons else "BLOCKED",
            "blocked_reasons": sorted(set(deterministic_reasons)),
            "public_validation": public_validation,
            "source_copyedit_contract": source_contract,
        }
        final_queue = dict(queue)
        final_queue["public_post_text"] = candidate_text
        final_hash = hybrid_ai_input_hash(final_queue)
        if deterministic_reasons:
            used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
            return self._result(
                status="BLOCKED",
                route=route.route,
                public_post_text=candidate_text,
                blocked_reasons=deterministic_reasons,
                input_hash=final_hash,
                source_context_hash=source_hash,
                classification=classification,
                generation=generation,
                deterministic_validation=deterministic,
                actual_requests=used,
            )

        review_response = self.client.generate_json(
            model=_text(source_context.get("review_model")) or "gemini-3.1-flash-lite",
            prompt=_review_prompt(queue, source_text, candidate_text, policy),
            schema=REVIEW_SCHEMA,
            operation="review",
            account_id=account_id,
            cache_context={
                "prompt_version": PROMPT_VERSION,
                "queue_hash": final_hash,
                "source_context_hash": source_hash,
                "candidate_text": candidate_text,
            },
        )
        review = dict(review_response["data"])
        review_failures: list[str] = []
        if review.get("decision") != "PASS":
            review_failures.append("ai_final_review_rejected")
        for field in (
            "natural_japanese", "source_grounding", "account_fit", "public_safety",
            "voice_persona", "identity_fit", "interpersonal_distance", "register_fit",
            "conversational_naturalness",
        ):
            if review.get(field) != "PASS":
                review_failures.append(f"ai_{field}_failed")
        if int(review.get("voice_persona_score", 0)) < 85:
            review_failures.append("ai_voice_persona_score_below_threshold")
        review_failures.extend(str(flag) for flag in review.get("risk_flags", []))
        used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
        return self._result(
            status="PASS" if not review_failures else "BLOCKED",
            route=route.route,
            public_post_text=candidate_text,
            blocked_reasons=review_failures,
            input_hash=final_hash,
            source_context_hash=source_hash,
            classification=classification,
            generation=generation,
            review=review,
            deterministic_validation=deterministic,
            actual_requests=used,
        )


def merge_gate_audit(existing: Any, result: GateResult) -> str:
    try:
        payload = json.loads(_text(existing)) if _text(existing) else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["hybrid_ai_gate"] = result.audit()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
