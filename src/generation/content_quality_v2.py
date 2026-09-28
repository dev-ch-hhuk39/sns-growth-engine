"""Content Quality V2: safety decisions stay hard; editorial quality ranks drafts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config" / "content_quality_v2.json"
ACCOUNTS = {"night_scout", "liver_manager", "beauty_account"}


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: str) -> str:
    return re.sub(r"[\s、。，．！？!?・:：;；()（）「」『』【】]", "", value).lower()


def _first_person_experience_reasons(
    text: str,
    *,
    source_creator_context: str = "",
    account_id: str = "",
) -> list[str]:
    policy = load_policy()
    cfg = policy.get("accounts", {}).get(account_id, {})
    patterns = [str(item) for item in cfg.get("blocked_first_person_experience_patterns", [])]
    reasons = ["fabricated_personal_experience"] if any(item in text for item in patterns) else []
    source_context = _compact(source_creator_context)
    own_experience = re.search(r"(?:私|僕|自分)(?:も|が|は).{0,18}(?:使|試|経験|売上|収入|稼い)", text)
    if own_experience and source_context and any(term in source_context for term in ("使って", "試して", "売上", "収入", "稼い")):
        if not any(marker in text for marker in ("投稿者", "発信者", "話して", "紹介して", "動画では")):
            reasons.append("source_creator_experience_reassigned")
    return sorted(set(reasons))


def _unsupported_high_risk_reasons(
    text: str,
    *,
    supported_claims: Iterable[str] = (),
) -> list[str]:
    high_risk_claim_patterns = (
        r"(?:月収|年収).{0,16}\d[\d,万億円]*",
        r"(?:稼げる|稼げます|治る|治ります|治療できる|副作用がない|効果がある|安全性が高い|保証する|保証します)",
        r"(?:必ず|絶対).{0,12}(?:稼げる|治る|効果|改善|増える|減る|成功|保証)",
    )
    if not any(re.search(pattern, text) for pattern in high_risk_claim_patterns):
        return []
    if isinstance(supported_claims, Mapping):
        supported_claims = [
            value for value in supported_claims.values()
            if isinstance(value, (str, int, float))
        ]
    elif isinstance(supported_claims, str):
        supported_claims = [supported_claims]
    claims: list[str] = []
    for item in supported_claims:
        if isinstance(item, Mapping):
            item = " ".join(
                str(item.get(key) or "")
                for key in ("caption_claim", "source_evidence", "claim", "evidence")
            )
        normalized = _normalized(str(item))
        if normalized:
            claims.append(normalized)
    compact_text = _normalized(text)
    if any(claim and (claim in compact_text or compact_text in claim) for claim in claims):
        return []
    # Any high-risk proposition without matched evidence is fail-closed.
    return ["unsupported_high_risk_factual_claim"]


def _broken_japanese_reasons(text: str) -> list[str]:
    patterns = (
        r"ましょうんだよね", r"みてみてみて", r"てみてみて", r"ですねね", r"だぁだ", r"てで=", r"るて(?:みて|みよう|ほしい|ください)"
    )
    return ["broken_japanese"] if any(re.search(pattern, text) for pattern in patterns) else []


def sanitize_transcript_excerpt(value: str, *, max_chars: int = 2400) -> dict[str, Any]:
    """Remove obvious ASR/annotation debris without inventing or paraphrasing facts."""
    original = str(value or "")
    cleaned_lines: list[str] = []
    dropped = 0
    for line in original.splitlines():
        item = line.strip()
        if not item or re.fullmatch(r"[\[【（(].{0,24}(?:音楽|BGM|拍手|歓声|不明瞭|聞き取れず).{0,24}[\]】）)]", item):
            dropped += bool(item)
            continue
        if "\ufffd" in item or re.fullmatch(r"[\W_]+", item):
            dropped += 1
            continue
        if cleaned_lines and _normalized(cleaned_lines[-1]) == _normalized(item):
            dropped += 1
            continue
        cleaned_lines.append(item)
    result = "\n".join(cleaned_lines)[:max_chars].strip()
    return {"text": result, "changed": result != original.strip(), "dropped_fragment_count": dropped}


def hard_gate(
    candidate: Mapping[str, Any],
    *,
    account_id: str,
    public_validation: Mapping[str, Any] | None = None,
    media_validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return only safety/compliance/identity blockers, not editorial score failures."""
    reasons: set[str] = set()
    text = str(candidate.get("public_post_text") or candidate.get("text") or "")
    target = str(candidate.get("target_account_id") or candidate.get("account_id") or account_id)
    if account_id not in ACCOUNTS or target != account_id:
        reasons.add("account_mismatch")
    if candidate.get("platform") and str(candidate.get("platform")).lower() != "threads":
        reasons.add("platform_not_threads")
    if candidate.get("duplicate") or candidate.get("idempotency_conflict"):
        reasons.add("duplicate_asset_or_post")
    if public_validation is not None:
        try:
            from media_v1_policy import split_public_validation
        except ImportError:
            from scripts.media_v1_policy import split_public_validation
        hard, _soft = split_public_validation(public_validation)
        reasons.update(hard)
        if str(public_validation.get("internal_leak_check", {}).get("status", "")).upper() == "BLOCKED":
            reasons.add("internal_private_metadata_leak")
    reasons.update(_first_person_experience_reasons(
        text,
        source_creator_context=str(candidate.get("source_creator_context") or ""),
        account_id=account_id,
    ))
    reasons.update(_unsupported_high_risk_reasons(
        text,
        supported_claims=candidate.get("supported_claims", []) or candidate.get("claim_support", []),
    ))
    reasons.update(_broken_japanese_reasons(text))
    if media_validation is not None:
        reasons.update(str(item) for item in media_validation.get("hard_gate_blocked_reasons", []) if str(item))
        if str(media_validation.get("hard_gate_status", "")).upper() == "BLOCKED" and not media_validation.get("hard_gate_blocked_reasons"):
            reasons.add("media_technical_or_permission_invalid")
    if candidate.get("media_required"):
        if str(candidate.get("rights_status", "")).lower() not in {"owned", "licensed", "approved_creator_clip"}:
            reasons.add("rights_invalid")
        if str(candidate.get("permission_status", "")).lower() != "approved":
            reasons.add("permission_invalid")
        if not str(candidate.get("media_asset_id") or "").strip() or not str(candidate.get("media_url") or "").strip():
            reasons.add("media_asset_or_url_missing")
    return {"status": "PASS" if not reasons else "BLOCKED", "hard_gate_reasons": sorted(reasons)}


def repair_style_only(text: str, account_id: str) -> dict[str, Any]:
    """Apply bounded, meaning-preserving cleanup; never add claims or rewrite facts."""
    policy = load_policy()
    value = str(text or "").strip()
    original = value
    repairs: list[str] = []
    if not value:
        return {"public_post_text": value, "repair_count": 0, "repairs": []}
    removable = policy.get("template_phrases", {}).get("repairable_literal_lines", [])
    lines = value.splitlines()
    cleaned = [line for line in lines if _compact(line) not in {_compact(item) for item in removable}]
    value = "\n".join(cleaned)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    if value != original:
        repairs.append("removed_literal_template_boilerplate")
    elif account_id == "beauty_account":
        allowed = policy["accounts"][account_id]["emoji_allowed"]
        emoji_count = sum(value.count(emoji) for emoji in allowed)
        if emoji_count == 0:
            if any(term in value for term in ("不安", "迷う", "悩む", "気になる")):
                emoji = "🥺"
            elif any(term in value for term in ("うれしい", "嬉しい", "好き", "楽しい")):
                emoji = "✨"
            elif any(term in value for term in ("肌", "スキンケア", "コスメ", "メイク", "髪")):
                emoji = "🤍"
            else:
                emoji = "💭"
            # Attach to the first complete sentence/line; do not add a new claim.
            match = re.search(r"[。！？!?]|\n", value)
            at = match.start() if match else len(value)
            value = value[:at].rstrip() + emoji + value[at:]
            repairs.append("beauty_single_semantic_emoji_inserted")
    return {"public_post_text": value, "repair_count": min(1, len(repairs)), "repairs": repairs[:1]}


def rank_candidate(candidate: Mapping[str, Any], *, account_id: str) -> dict[str, Any]:
    """Score editorial preference. Missing evidence is neutral-low, never a block."""
    policy = load_policy()
    weights = policy["quality_ranking"]["weights"]
    missing = float(policy["quality_ranking"]["missing_component_score"])
    raw = candidate.get("quality_components", {})
    components = {key: max(0.0, min(100.0, float(raw.get(key, missing)))) for key in weights}
    warnings = [str(item) for item in candidate.get("warnings", []) if str(item)]
    understanding = candidate.get("media_understanding") or {}
    has_media = bool(candidate.get("media_required") or candidate.get("media_asset_id")
                     or understanding or candidate.get("media_url"))
    visual_status = str(understanding.get("visual_status") or understanding.get("status") or
                        ("VISUAL_UNVERIFIED" if has_media else "NOT_APPLICABLE"))
    if has_media and visual_status != "VISUAL_VERIFIED":
        components["media_caption_relevance"] = min(components["media_caption_relevance"], 35.0)
        components["concrete_evidence"] = min(components["concrete_evidence"], 35.0)
        warnings.append("VISUAL_UNVERIFIED")
    generic_risk = str(candidate.get("generic_caption_risk", "UNKNOWN")).upper()
    weighted = sum(components[key] * float(weight) for key, weight in weights.items())
    if generic_risk == "HIGH":
        weighted -= float(policy["quality_ranking"]["generic_caption_high_penalty"])
        warnings.append("GENERIC_CAPTION_RISK_HIGH")
    if has_media and visual_status != "VISUAL_VERIFIED":
        weighted -= float(policy["quality_ranking"]["visual_unverified_penalty"])
    return {
        "quality_rank": round(max(0.0, min(100.0, weighted)), 2),
        "quality_rank_components": components,
        "warnings": sorted(set(warnings)),
    }


def select_ranked_candidate(candidates: Iterable[Mapping[str, Any]], *, account_id: str) -> dict[str, Any] | None:
    eligible: list[tuple[float, str, dict[str, Any]]] = []
    for candidate in candidates:
        row = dict(candidate)
        if row.get("hard_gate_status") != "PASS":
            continue
        rank = rank_candidate(row, account_id=account_id)
        row.update(rank)
        eligible.append((float(rank["quality_rank"]), str(row.get("candidate_id", "")), row))
    return max(eligible, key=lambda entry: (entry[0], entry[1]))[2] if eligible else None


def select_media_or_text_fallback(
    media_candidates: Iterable[Mapping[str, Any]],
    text_candidates: Iterable[Mapping[str, Any]],
    *,
    account_id: str,
) -> dict[str, Any] | None:
    """Prefer safe media; otherwise expose a text fallback without media-success semantics."""
    def normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        candidate = dict(row)
        gate = candidate.get("hard_gate_result") or candidate.get("hard_gate") or {}
        candidate.setdefault("hard_gate_status", str(gate.get("status", "")).upper())
        return candidate

    media_rows = [normalized(row) for row in media_candidates]
    selected_media = select_ranked_candidate(media_rows, account_id=account_id)
    if selected_media:
        return {
            **selected_media,
            "route_status": "MEDIA_SELECTED",
            "actual_post_type": "media",
            "media_counted_as_success": True,
            "fallback_reason": "",
        }

    selected_text = select_ranked_candidate(
        [normalized(row) for row in text_candidates], account_id=account_id,
    )
    if not selected_text:
        return None
    return {
        **selected_text,
        "route_status": "DEGRADED_TO_TEXT",
        "actual_post_type": "text",
        "media_counted_as_success": False,
        "fallback_reason": (
            "MEDIA_CANDIDATES_EXHAUSTED" if not media_rows
            else "NO_HARD_GATE_MEDIA_CANDIDATE"
        ),
    }


def understand_media_contract(
    media: Mapping[str, Any],
    *,
    account_id: str,
    source_creator_context: str = "",
) -> dict[str, Any]:
    """Normalize stored visual/transcript evidence without inferring vision from ASR."""
    vision_summary = _compact(media.get("visual_summary"))
    visible_text = _compact(media.get("visible_text"))
    vision_state = str(media.get("vision_status") or "").upper()
    visual_verified = bool(vision_summary or visible_text) and vision_state in {"PASS", "PASS_VISION", "VISUAL_VERIFIED"}
    transcript_text = _compact(media.get("transcript_summary") or media.get("spoken_content_summary") or media.get("transcript_text"))
    transcript_status = str(media.get("transcript_status") or "UNAVAILABLE").upper()
    claims = media.get("main_claims", [])
    if isinstance(claims, str):
        try:
            claims = json.loads(claims)
        except json.JSONDecodeError:
            claims = []
    return {
        "media_asset_id": str(media.get("media_asset_id") or media.get("source_post_media_id") or ""),
        "account_id": account_id,
        "media_type": str(media.get("media_type") or "unknown").lower(),
        "visual_summary": vision_summary,
        "visible_people_or_objects": str(media.get("visible_people_or_objects") or ""),
        "visible_action": str(media.get("visible_action") or ""),
        "spoken_content_summary": transcript_text,
        "transcript_confidence": media.get("transcript_confidence", "UNVERIFIED"),
        "visual_confidence": media.get("visual_confidence", "VERIFIED" if visual_verified else "UNVERIFIED"),
        "key_moment": str(media.get("key_moment") or ""),
        "main_topic": str(media.get("main_topic") or ""),
        "factual_claims": claims if isinstance(claims, list) else [],
        "uncertain_claims": media.get("uncertain_claims", []),
        "source_creator_context": source_creator_context,
        "what_viewer_actually_sees": vision_summary if visual_verified else "VISUAL_UNVERIFIED",
        "what_viewer_actually_hears": transcript_text if transcript_text and transcript_status in {"PASS", "AVAILABLE", "VERIFIED"} else "AUDIO_UNVERIFIED",
        "visual_status": "VISUAL_VERIFIED" if visual_verified else "VISUAL_UNVERIFIED",
        "transcript_status": transcript_status,
    }


def build_post_package(
    *,
    account_id: str,
    media: Mapping[str, Any],
    public_caption: str,
    source_creator_context: str = "",
    why_account: str = "",
    hard_gate_result: Mapping[str, Any] | None = None,
    quality_components: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    understanding = understand_media_contract(media, account_id=account_id, source_creator_context=source_creator_context)
    caption = _compact(public_caption)
    evidence = " ".join(str(understanding[key]) for key in ("visual_summary", "visible_people_or_objects", "visible_action", "spoken_content_summary", "main_topic"))
    caption_terms = {term for term in re.findall(r"[\u4e00-\u9fff\u3040-\u30ff]{2,}", caption) if len(term) >= 2}
    evidence_terms = set(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff]{2,}", evidence))
    anchor_terms = sorted(caption_terms & evidence_terms, key=len, reverse=True)
    verified_evidence = understanding["visual_status"] == "VISUAL_VERIFIED" or understanding["transcript_status"] in {"PASS", "AVAILABLE", "VERIFIED"}
    anchor_status = "PASS" if anchor_terms and verified_evidence else "UNVERIFIED"
    # Remove-media test: if no concrete evidence token from this asset anchors
    # the caption, swapping the asset would leave the caption essentially intact.
    generic_risk = "LOW" if anchor_terms else "HIGH"
    main_topic = understanding["main_topic"] or (anchor_terms[0] if anchor_terms else "")
    if why_account and _compact(why_account).lower() not in {"this is relevant", "relevant", "related"}:
        relevance_reason = why_account
    elif understanding["visual_status"] == "VISUAL_VERIFIED" and main_topic:
        relevance_reason = f"確認済みのメディア理解にある「{main_topic}」を、{account_id}の読者課題に接続できる可能性がある（推定。owner確認前）。"
    else:
        relevance_reason = "UNVERIFIED: 現在の視覚証拠から、このアカウントが投稿すべき具体的理由を確定できない。"
    angle_options = []
    if anchor_terms:
        angle_options = [
            {"type": "observation", "basis": anchor_terms[0]},
            {"type": "practical_takeaway", "basis": anchor_terms[0]},
            {"type": "commentary", "basis": anchor_terms[0]},
        ]
    angles = angle_options[: int(load_policy()["max_media_angles_per_asset"])]
    result = {
        "account_id": account_id,
        "media_asset_id": understanding["media_asset_id"],
        "media_type": understanding["media_type"],
        "media_understanding": understanding,
        "why_this_account_should_post_this": relevance_reason,
        "post_angle_options": angles,
        "post_angle": angles[0] if angles else {"type": "unverified", "basis": ""},
        "hook": caption[:100],
        "caption": public_caption,
        "cta": "" if not re.search(r"(保存|いいね|フォロー|相談|試してみて)", caption) else "caption_contains_light_action",
        "claim_support": media.get("claim_support", []),
        "media_anchor": {"status": anchor_status, "matched_terms": anchor_terms[:8],
                         "remove_media_test": "PASS" if anchor_terms else "GENERIC_CAPTION_RISK_HIGH"},
        "persona_evidence": media.get("persona_evidence", {}),
        "generic_caption_risk": generic_risk,
        "hard_gate_result": dict(hard_gate_result or {"status": "UNVERIFIED", "hard_gate_reasons": []}),
        "warnings": [] if anchor_status == "PASS" else ["media_specific_concrete_anchor_unverified"],
    }
    candidate = {
        "candidate_id": str(media.get("media_asset_id") or ""),
        "quality_components": dict(quality_components or {}),
        "media_understanding": understanding,
        "generic_caption_risk": generic_risk,
        "warnings": result["warnings"],
    }
    result.update(rank_candidate(candidate, account_id=account_id))
    return result
