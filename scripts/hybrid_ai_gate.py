#!/usr/bin/env python3
"""Common semantic/generation/review gate for every automated Threads route."""
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
from public_post_quality import final_public_post_validator

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/hybrid_ai_account_policies.json"
GATE_SCHEMA_VERSION = "hybrid_ai_gate_v1"
PROMPT_VERSION = "hybrid_ai_prompts_v1"

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
        "public_post_text": {"type": "string"},
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
        "risk_flags",
        "reasons",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REJECT"]},
        "natural_japanese": {"type": "string", "enum": ["PASS", "FAIL"]},
        "source_grounding": {"type": "string", "enum": ["PASS", "FAIL"]},
        "account_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "public_safety": {"type": "string", "enum": ["PASS", "FAIL"]},
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
    classification: dict[str, Any]
    generation: dict[str, Any]
    review: dict[str, Any]
    deterministic_validation: dict[str, Any]
    actual_requests: int

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


def hybrid_ai_input_hash(queue: Mapping[str, Any]) -> str:
    fields = [
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
    ]
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


def hybrid_ai_gate_passed(queue: Mapping[str, Any]) -> tuple[bool, str]:
    if not requires_hybrid_ai_gate(queue):
        return True, "not_required"
    gate = persisted_hybrid_ai_gate(queue)
    if gate is None:
        return False, "missing"
    if gate.get("schema_version") != GATE_SCHEMA_VERSION:
        return False, "schema_stale"
    if gate.get("status") != "PASS":
        return False, "not_pass"
    if gate.get("input_hash") != hybrid_ai_input_hash(queue):
        return False, "input_hash_stale"
    return True, "pass"


def _source_text(queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> str:
    candidates = [
        source_context.get("original_post_text"),
        source_context.get("transcript_excerpt"),
        source_context.get("transcript"),
        source_context.get("description"),
        source_context.get("source_text"),
        queue.get("public_post_text"),
    ]
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
    if "ライバの排出" in text:
        reasons.append("known_transcription_error_present")
    if re.search(r"(?:でで|がが|をを|にに|はは|もも)(?:[、。！!？?]|$)", text):
        reasons.append("duplicate_particle_present")
    if re.search(r"(?:月収|年収)\s*[0-9０-９,，]+\s*万?円?", text):
        reasons.append("unverified_income_amount_present")
    if re.search(r"[0-9０-９,，]+\s*万円[^。\n]{0,20}(?:稼|達成)", text):
        reasons.append("unverified_income_achievement_present")
    return reasons


def _preflight(queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    account_id = _text(queue.get("account_id"))
    target_account_id = _text(queue.get("target_account_id"))
    if target_account_id and target_account_id != account_id:
        reasons.append("target_account_mismatch")
    if _text(queue.get("excluded_from_activation")).lower() in {"true", "1", "yes"}:
        reasons.append("excluded_from_activation")
    if _text(queue.get("repost_prohibited")).lower() in {"true", "1", "yes"}:
        reasons.append("repost_prohibited")
    route = decide_route(queue).route
    media_route = route in {"external_direct_source_copyedit", "owned_media_transform", "approved_clip_transform"}
    policies = {
        _text(source_context.get("use_policy")).upper(),
        _text(source_context.get("usage_scope")).upper(),
        _text(source_context.get("reuse_policy")).upper(),
    }
    if media_route and "REFERENCE_ONLY" in policies:
        reasons.append("reference_only_media_reuse_blocked")
    if not _text(queue.get("public_post_text")) and route == "external_direct_source_copyedit":
        reasons.append("source_copyedit_text_missing")
    if not _source_text(queue, source_context):
        reasons.append("source_evidence_missing")
    return reasons


def _classification_prompt(queue: Mapping[str, Any], source_context: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    return (
        "あなたはSNS投稿候補の適合性審査担当です。文章生成はしません。"
        "対象アカウント、想定読者、BtoB/BtoC、参照元の利用目的を厳格に判定してください。"
        "元素材が店舗経営者・事業者向けなのに求職者向けへ無理に変換されている場合はREJECT。"
        "他社宣伝、根拠不明の収益実績、対象アカウント違いもREJECT。\n\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"QUEUE={json.dumps(dict(queue), ensure_ascii=False, sort_keys=True)}\n"
        f"SOURCE_CONTEXT={json.dumps(dict(source_context), ensure_ascii=False, sort_keys=True)}"
    )


def _generation_prompt(route: str, queue: Mapping[str, Any], source_text: str, policy: Mapping[str, Any]) -> str:
    if route == "external_direct_source_copyedit":
        instruction = (
            "元投稿の主張、固有情報、話者の温度感を維持し、誤字、重複助詞、メンション、ハッシュタグ、"
            "文字起こしノイズだけを必要最小限で修正してください。新しい助言や事実は追加しないでください。"
        )
    else:
        instruction = (
            "参照根拠に書かれた事実だけを使い、対象読者に自然で具体的なThreads投稿を新規作成してください。"
            "BtoBの主張をBtoCに変換しない。他社の宣伝文や収益実績を自社の主張として使わない。"
            "テンプレ句を避け、3段落程度で簡潔にしてください。"
        )
    return (
        f"{instruction}\n\n"
        f"ROUTE={route}\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"CURRENT_QUEUE_TEXT={_text(queue.get('public_post_text'))}\n"
        f"SOURCE_EVIDENCE={source_text}"
    )


def _review_prompt(queue: Mapping[str, Any], source_text: str, candidate_text: str, policy: Mapping[str, Any]) -> str:
    return (
        "公開直前のSNS投稿を厳格に審査してください。"
        "自然な日本語、参照根拠への忠実性、対象読者・アカウント適合、公開安全性を確認してください。"
        "誤字、重複助詞、[音楽]等、根拠不明の収益額、他社宣伝、BtoB/BtoC不一致はREJECT。\n\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\n"
        f"QUEUE_ID={_text(queue.get('queue_id'))}\n"
        f"SOURCE_EVIDENCE={source_text}\n"
        f"CANDIDATE_TEXT={candidate_text}"
    )


class HybridAiGate:
    def __init__(self, client: Any, policies: Mapping[str, Any] | None = None) -> None:
        self.client = client
        self.policies = dict(policies or load_account_policies())

    def evaluate(self, queue: Mapping[str, Any], source_context: Mapping[str, Any]) -> GateResult:
        route = decide_route(queue)
        account_id = _text(queue.get("account_id"))
        policy = self.policies.get(account_id)
        initial_hash = hybrid_ai_input_hash(queue)
        if not policy:
            return GateResult("BLOCKED", route.route, _text(queue.get("public_post_text")), ["account_policy_missing"], initial_hash, {}, {}, {}, {}, 0)
        preflight = _preflight(queue, source_context)
        if preflight:
            return GateResult("BLOCKED", route.route, _text(queue.get("public_post_text")), preflight, initial_hash, {}, {}, {}, {"preflight": preflight}, 0)

        source_text = _source_text(queue, source_context)
        before_requests = int(getattr(self.client, "actual_request_count", 0))
        classify_response = self.client.generate_json(
            model=_text(source_context.get("classifier_model")) or "gemini-2.5-flash-lite",
            prompt=_classification_prompt(queue, source_context, policy),
            schema=CLASSIFICATION_SCHEMA,
            operation="classify",
            account_id=account_id,
            cache_context={"prompt_version": PROMPT_VERSION, "queue_hash": initial_hash},
        )
        classification = dict(classify_response["data"])
        classification_failures = []
        if classification.get("decision") != "PASS":
            classification_failures.append("ai_classification_rejected")
        for field in ("target_account_match", "target_audience_match", "source_usage_fit"):
            if classification.get(field) != "PASS":
                classification_failures.append(f"ai_{field}_failed")
        if classification_failures:
            used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
            return GateResult("BLOCKED", route.route, _text(queue.get("public_post_text")), classification_failures + list(classification.get("risk_flags", [])), initial_hash, classification, {}, {}, {}, used)

        generation: dict[str, Any] = {}
        candidate_text = _text(queue.get("public_post_text"))
        if route.generate:
            generate_response = self.client.generate_json(
                model=_text(source_context.get("generator_model")) or "gemini-2.5-flash",
                prompt=_generation_prompt(route.route, queue, source_text, policy),
                schema=GENERATION_SCHEMA,
                operation="generate",
                account_id=account_id,
                cache_context={"prompt_version": PROMPT_VERSION, "queue_hash": initial_hash, "route": route.route},
            )
            generation = dict(generate_response["data"])
            candidate_text = _text(generation.get("public_post_text"))

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
        if deterministic_reasons:
            used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
            final_queue = dict(queue)
            final_queue["public_post_text"] = candidate_text
            return GateResult("BLOCKED", route.route, candidate_text, sorted(set(deterministic_reasons)), hybrid_ai_input_hash(final_queue), classification, generation, {}, deterministic, used)

        review_response = self.client.generate_json(
            model=_text(source_context.get("review_model")) or "gemini-2.5-flash-lite",
            prompt=_review_prompt(queue, source_text, candidate_text, policy),
            schema=REVIEW_SCHEMA,
            operation="review",
            account_id=account_id,
            cache_context={"prompt_version": PROMPT_VERSION, "queue_hash": initial_hash, "candidate_text": candidate_text},
        )
        review = dict(review_response["data"])
        review_failures = []
        if review.get("decision") != "PASS":
            review_failures.append("ai_final_review_rejected")
        for field in ("natural_japanese", "source_grounding", "account_fit", "public_safety"):
            if review.get(field) != "PASS":
                review_failures.append(f"ai_{field}_failed")
        review_failures.extend(str(flag) for flag in review.get("risk_flags", []))
        final_queue = dict(queue)
        final_queue["public_post_text"] = candidate_text
        used = int(getattr(self.client, "actual_request_count", 0)) - before_requests
        return GateResult(
            "PASS" if not review_failures else "BLOCKED",
            route.route,
            candidate_text,
            sorted(set(review_failures)),
            hybrid_ai_input_hash(final_queue),
            classification,
            generation,
            review,
            deterministic,
            used,
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
