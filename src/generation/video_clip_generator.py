"""Threads-only text generation for transcript-grounded video clip candidates.

The canonical account persona comes from config/post_generation_rules.json.
This module never publishes. Persisted candidates remain WAITING_REVIEW.
Physical cutting is handled by generation.video_clip_materializer.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from text_policy import check_text_policy
from generation.source_provenance import normalize_source_context, reference_bridge_signal, validate_source_claims

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "config" / "post_generation_rules.json"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
TARGET_PLATFORM = "threads"



def _plain_public_text(value: Any) -> str:
    """Normalize model output to plain social copy; Markdown styling is not public copy."""
    text = str(value or "").strip()
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = text.replace("**", "").replace("__", "").replace("~~", "").replace("`", "")
    text = text.replace("*", "")
    return text.strip()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _load_generation_contract(account_id: str) -> dict[str, Any]:
    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError(f"unsupported account_id: {account_id}")
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    persona = dict((payload.get("persona_profiles") or {}).get(account_id) or {})
    account = dict((payload.get("accounts") or {}).get(account_id) or {})
    if not persona or not account:
        raise RuntimeError(f"canonical generation contract missing for {account_id}")
    return {"persona": persona, "account": account}


def _build_system_prompt(account_id: str, source_context: dict[str, Any] | None = None) -> str:
    contract = _load_generation_contract(account_id)
    source = normalize_source_context(source_context)
    canonical_voice_rule = (
        "For liver_manager: if first person is needed, use 私 only; never 僕/俺. Use a gentle manager/coaching voice with concrete LIVE action plus a reason, prefer line breaks over repeated masculine full-stop assertions, and stay consistent with the canonical persona. "
        if account_id == "liver_manager"
        else
        "For night_scout: use 僕 naturally, speak from practical scout field experience, help night-work women make decisions, and avoid recruiter-ad copy or preachy language. "
    )
    provenance_rule = (
        "The source is third-party reference media. Treat the post as commentary, agreement, or a lesson from the attached video. "
        "Never imply that the source agency, people, program, numbers, achievements, or exact process belong to the target account. "
        "Do not write institutional ownership claims such as 'our agency does this' about source-specific facts. "
        "Principle-level agreement is allowed: you may say that the point is important and that the target team also pays attention to the same general principle, without inventing target-side results. "
        "Make the reaction relationship visible with one natural Japanese reference bridge. Examples include 'こんな感じで', 'こういうのは大事', 'こういう事例を見ると', 'この考え方', or '僕たちもここは意識してる'. Do not mechanically repeat one fixed phrase; choose wording that fits the source. "
        if source["source_relation"] == "third_party_reference"
        else
        "The source is explicitly classified as owned/first-party. First-person framing is allowed only when grounded in the clip and canonical account context. "
    )
    return (
        f"Canonical account_id: {account_id}. "
        "You are an SNS editor producing exactly one Japanese Threads post from a video clip. "
        "The clip transcript is the semantic boundary. Do not invent facts or switch topics. "
        "Use the canonical account persona and purpose below. Avoid generic motivational filler, "
        "agency-sales language, and internal analysis. "
        + provenance_rule
        + canonical_voice_rule
        + "Public threads_text must be plain text: no Markdown bold/italic markers, no asterisks, no backticks, and no heading syntax. "
        + "Do not output raw source URLs or internal source metadata; you may naturally refer to 'this video' or 'this point'. Return JSON only.\n\n"
        + json.dumps({"generation_contract": contract, "source_context": source}, ensure_ascii=False, sort_keys=True)
    )


def _build_user_prompt(candidate: dict[str, Any], account_id: str, source_context: dict[str, Any] | None = None) -> str:
    source = normalize_source_context(source_context)
    payload = {
        "account_id": account_id,
        "source_relation": source["source_relation"],
        "source_name": source["source_name"],
        "source_author_handle": source["source_author_handle"],
        "clip_title": str(candidate.get("clip_title", ""))[:160],
        "hook": str(candidate.get("hook", ""))[:240],
        "why_it_works": str(candidate.get("why_it_works", ""))[:300],
        "target_persona": str(candidate.get("target_persona", ""))[:160],
        "threads_post_angle": str(candidate.get("threads_post_angle", ""))[:400],
        "transcript_excerpt": str(candidate.get("transcript_excerpt", ""))[:1600],
    }
    return (
        "Create one Threads post grounded in this clip. Keep the clip's hook/topic/claim order when useful. "
        "The post must make sense with the attached clip. For third-party source media, write from a reaction/commentary/lesson stance and never convert source-specific facts into the target account's own achievements. "
        "General agreement with a principle is allowed, but do not invent target-side numbers, results, programs, or ownership. "
        "For third-party source media, include a natural reference bridge so readers can feel that this account is reacting to the attached source. Do not force the exact phrase 'こんな感じで'; vary the wording to fit the clip. "
        "Output JSON with keys threads_text, title, hypothesis, media_strategy. "
        "threads_text must be <= 600 Japanese characters; media_strategy must be video_clip.\n\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )

def _mock_generation(account_id: str) -> dict[str, Any]:
    if account_id == "night_scout":
        text = "[MOCK] This Night Scout clip candidate is grounded in the clip transcript."
    else:
        text = "[MOCK] This Liver Manager clip candidate is grounded in the clip transcript."
    return {
        "threads_text": text,
        "title": "[MOCK] clip candidate",
        "hypothesis": "clip-grounded Threads candidate",
        "media_strategy": "video_clip",
    }


def _is_rights_blocked(candidate: dict[str, Any]) -> bool:
    rights = str(candidate.get("rights_status", "unknown")).lower()
    risk = str(candidate.get("media_reuse_risk", "low")).lower()
    return rights == "not_allowed" or risk == "high"


def _needs_rights_review(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("rights_status", "unknown")).lower() == "unknown"


def generate_from_clip(
    candidate: dict[str, Any],
    account: dict[str, Any],
    *,
    mock_llm: bool = True,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    account_id = str(account.get("account_id", "")).strip()
    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError(f"unsupported account_id: {account_id}")
    source = normalize_source_context(source_context or candidate)
    if mock_llm:
        result = _mock_generation(account_id)
        result["_source_relation"] = source["source_relation"]
        result["_ownership_claim_status"] = "MOCK_NOT_EVALUATED"
        return result
    from llm_client import call_gemini_json
    result = call_gemini_json(
        prompt=_build_user_prompt(candidate, account_id, source),
        system_prompt=_build_system_prompt(account_id, source),
    )
    if not isinstance(result, dict):
        raise RuntimeError("clip generation did not return a JSON object")
    text = _plain_public_text(result.get("threads_text", ""))
    result["threads_text"] = text
    if not text:
        raise RuntimeError("clip generation returned empty threads_text")
    provenance = validate_source_claims(text, source)
    if not provenance["ok"]:
        raise RuntimeError("clip generation ownership/provenance claim guard failed")
    bridge = reference_bridge_signal(text, source)
    if not bridge["ok"]:
        raise RuntimeError("clip generation reference bridge missing")
    result["_source_relation"] = source["source_relation"]
    result["_ownership_claim_status"] = provenance["status"]
    result["_reference_bridge_status"] = bridge["status"]
    return result


def _check_threads_text(text: str) -> tuple[str, str]:
    policy = check_text_policy(text, TARGET_PLATFORM)
    if policy.status == "FAIL":
        text = text[:800]
        policy = check_text_policy(text, TARGET_PLATFORM)
    return text, policy.status


def save_clip_generation_result(
    client: Any,
    candidate: dict[str, Any],
    generation: dict[str, Any],
    *,
    account_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError(f"unsupported account_id: {account_id}")
    clip_id = str(candidate.get("clip_id") or candidate.get("clip_candidate_id") or "").strip()
    rights_blocked = _is_rights_blocked(candidate)
    rights_review_required = _needs_rights_review(candidate)
    threads_text, threads_policy = _check_threads_text(str(generation.get("threads_text", "")))
    if not threads_text:
        raise ValueError("threads_text is empty")
    draft_id = f"d-{_short_uuid()}"
    source_video_id = str(candidate.get("source_video_id", ""))
    source_range = f"{candidate.get('start_seconds', candidate.get('start_time', ''))}~{candidate.get('end_seconds', candidate.get('end_time', ''))}"
    draft_data = {
        "draft_id": draft_id,
        "account_id": account_id,
        "title": str(generation.get("title", "clip draft"))[:100],
        "body_md": threads_text,
        "content": threads_text,
        "status": "WAITING_REVIEW",
        "generation_mode": "video_clip_reference",
        "content_route": "video_clip_reference",
        "hypothesis": str(generation.get("hypothesis", "")),
        "media_strategy": "video_clip",
        "video_clip_id": clip_id,
        "source_video_id": source_video_id,
        "source_video_url": str(candidate.get("source_video_url", "")),
        "source_time_range": source_range,
        "confidence_level": "MEDIUM",
        "ai_publish_recommendation": "WAITING_REVIEW",
        "notes": f"clip_id={clip_id} rights_blocked={rights_blocked} rights_review_required={rights_review_required}",
    }
    if not dry_run:
        client.save_draft(
            account_id=account_id,
            title=draft_data["title"],
            body_md=draft_data["body_md"],
            **{k: v for k, v in draft_data.items() if k not in ("account_id", "title", "body_md")},
        )
    queue_ids: list[str] = []
    if not rights_blocked:
        derivative_id = f"sd-{_short_uuid()}"
        derivative = {
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": TARGET_PLATFORM,
            "text": threads_text,
            "hashtags": "",
            "status": "WAITING_REVIEW",
            "reason": "video_clip_generation",
            "char_count": str(len(threads_text)),
            "text_policy_status": threads_policy,
            "video_clip_id": clip_id,
            "source_time_range": source_range,
        }
        queue_id = f"q-{_short_uuid()}"
        queue = {
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": TARGET_PLATFORM,
            "priority": "3",
            "status": "WAITING_REVIEW",
            "auto_publish": "false",
            "generation_mode": "video_clip_reference",
            "content_type": "video_clip_reference",
            "content_route": "video_clip_reference",
            "confidence_level": "MEDIUM",
            "ai_publish_recommendation": "WAITING_REVIEW",
            "text_policy_status": threads_policy,
            "public_post_text": threads_text,
            "video_clip_id": clip_id,
            "clip_candidate_id": clip_id,
            "source_video_id": source_video_id,
            "media_required": "true",
            "media_type": "video",
            "media_asset_id": str(candidate.get("clip_media_asset_id") or candidate.get("media_asset_id") or ""),
            "rights_status": str(candidate.get("rights_status", "unknown")),
            "permission_status": str(candidate.get("permission_status", "unknown")),
            "rights_review_required": "true" if rights_review_required else "false",
            "media_reuse_risk": str(candidate.get("media_reuse_risk", "low")),
            "source_video_url": str(candidate.get("source_video_url", "")),
            "source_time_range": source_range,
        }
        if not dry_run:
            client.append_social_derivative(derivative)
            client.append_queue_item(queue)
        queue_ids.append(queue_id)
    if not dry_run:
        client.update_video_clip_candidate(
            clip_id,
            text_generation_status="done",
            generated_draft_id=draft_id,
            generated_at=_now(),
            rights_review_required="true" if rights_review_required else "false",
        )
    return {
        "draft_id": draft_id,
        "queue_ids": queue_ids,
        "rights_blocked": rights_blocked,
        "rights_review_required": rights_review_required,
        "platform": TARGET_PLATFORM,
    }


def generate_from_clips_batch(
    candidates: list[dict[str, Any]],
    client: Any,
    account: dict[str, Any],
    *,
    mock_llm: bool = True,
    dry_run: bool = True,
) -> dict[str, Any]:
    account_id = str(account.get("account_id", ""))
    total = len(candidates)
    generated = rights_blocked_count = errors = 0
    for candidate in candidates:
        try:
            generation = generate_from_clip(candidate, account, mock_llm=mock_llm)
            result = save_clip_generation_result(
                client,
                candidate,
                generation,
                account_id=account_id,
                dry_run=dry_run,
            )
            generated += 1
            if result["rights_blocked"]:
                rights_blocked_count += 1
        except Exception as exc:
            print(f"[ERROR] clip generation failed: {exc.__class__.__name__}")
            errors += 1
    return {
        "total": total,
        "generated": generated,
        "rights_blocked": rights_blocked_count,
        "errors": errors,
    }
