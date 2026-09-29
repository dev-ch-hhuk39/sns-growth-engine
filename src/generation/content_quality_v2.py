"""Content Quality V2: safety decisions stay hard; editorial quality ranks drafts."""
from __future__ import annotations

import json
import hashlib
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
    evidence = media.get("visual_evidence", {})
    visual_verified = (
        bool(vision_summary or visible_text)
        and vision_state in {"PASS", "PASS_VISION", "VISUAL_VERIFIED"}
        and isinstance(evidence, Mapping)
        and evidence.get("status") == "UNDERSTOOD"
        and bool(evidence.get("frame_hashes"))
        and bool(evidence.get("provider"))
        and evidence.get("media_asset_id") == media.get("media_asset_id")
        and bool(media.get("content_hash"))
        and evidence.get("content_hash") == media.get("content_hash")
    )
    if isinstance(evidence, Mapping) and evidence.get("provider") == "github_models_vision":
        visual_verified = False  # Retired evidence is never promoted into new runtime verification.
    if isinstance(evidence, Mapping) and evidence.get("provider") == "gemini":
        facts = media.get("visual_facts")
        visual_verified = (visual_verified and media.get("http_status") == 200
                           and media.get("response_schema_status") == "PASS"
                           and all(str(media.get(k) or "").strip() for k in ("visual_summary", "visible_action", "key_moment"))
                           and isinstance(facts, list) and bool(facts)
                           and all(isinstance(f, Mapping) and f.get("id") and f.get("type") in {
                               "visible_action", "key_moment", "visible_people_or_objects", "visible_text"}
                               and isinstance(f.get("text"), str) and f["text"].strip() for f in facts))
    transcript_text = _compact(media.get("transcript_summary") or media.get("spoken_content_summary") or media.get("transcript_text"))
    transcript_status = str(media.get("transcript_status") or "UNAVAILABLE").upper()
    claims = media.get("main_claims", media.get("main_claims_json", []))
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


def prepare_media_context(media: Mapping[str, Any], *, account_id: str,
                          source_creator_context: str = "") -> dict[str, Any]:
    """Pure normalization of asset-bound evidence; never fetch or infer facts."""
    stored = media.get("media_understanding", media.get("media_understanding_json", {}))
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            stored = {}
    merged = {**media, **(stored if isinstance(stored, Mapping) else {})}
    # Evidence cannot rewrite the identity or permission of its parent asset.
    for key in ("account_id", "target_account_id", "media_asset_id", "content_hash",
                "rights_status", "permission_status", "source_id", "source_post_id"):
        merged[key] = media.get(key, "")
    context = understand_media_contract(merged, account_id=account_id,
                                       source_creator_context=source_creator_context)
    context.update({key: merged.get(key, "") for key in (
        "source_id", "source_post_id", "rights_status", "permission_status", "visible_text",
        "visual_evidence", "content_hash", "technical_status", "permission_evidence",
    )})
    context["preview_url"] = str(media.get("preview_url") or media.get("storage_url") or media.get("media_url") or "")
    context["what_viewer_sees"] = context["what_viewer_actually_sees"]
    context["what_viewer_hears"] = context["what_viewer_actually_hears"]
    if not context["technical_status"]:
        from media.media_probe import asset_has_video_evidence
        if context["media_type"] == "video" and asset_has_video_evidence(dict(media)):
            context["technical_status"] = "PASS"
    if not context["permission_evidence"]:
        context["permission_evidence"] = media.get("permission_evidence_reference") or media.get("evidence_reference") or ""
    reasons = []
    if account_id not in ACCOUNTS or media.get("account_id", media.get("target_account_id")) != account_id:
        reasons.append("account_isolation")
    if media.get("target_account_id") and media["target_account_id"] != account_id:
        reasons.append("account_isolation")
    if context["rights_status"] not in {"owned", "licensed", "approved_creator_clip"}:
        reasons.append("rights_not_approved")
    if context["permission_status"] != "approved" or not context["permission_evidence"]:
        reasons.append("permission_evidence_required")
    if context["technical_status"] != "PASS" or not context["media_asset_id"] or not context["preview_url"]:
        reasons.append("technical_media_unverified")
    context["eligibility"] = {"status": "BLOCKED" if reasons else "PASS", "hard_reasons": reasons}
    context["publish_eligibility"] = dict(context["eligibility"])
    editorial_reasons = [reason for reason in reasons if reason not in {
        "rights_not_approved", "permission_evidence_required"}]
    context["editorial_draft_eligibility"] = {
        "status": "BLOCKED" if editorial_reasons else "PASS", "hard_reasons": editorial_reasons}
    context["visual_facts"] = []
    if context["visual_status"] == "VISUAL_VERIFIED":
        source_facts = merged.get("visual_facts", []) if context.get("visual_evidence", {}).get("provider") == "gemini" else [
            {"id": kind, "type": kind, "text": str(context.get(kind) or "").strip()}
            for kind in ("visible_action", "key_moment", "visible_people_or_objects", "visible_text")
            if str(context.get(kind) or "").strip()]
        for fact in source_facts:
            identity_parts = [context["media_asset_id"], context["content_hash"], fact["type"], fact["text"]]
            if context.get("visual_evidence", {}).get("provider") == "gemini":
                identity_parts.append(fact["id"])
            identity = json.dumps(identity_parts, ensure_ascii=False)
            context["visual_facts"].append({"id": "VF_" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                                            "type": fact["type"], "text": fact["text"]})
    context["strict_relevance_review"] = bool(media.get("strict_relevance_review"))
    context["account_relevance_review"] = merged.get("account_relevance_review", {})
    context["context_completeness"] = sum(bool(context.get(k)) for k in (
        "visual_summary", "visible_action", "key_moment", "main_topic", "source_post_id")) / 5
    return context


def evaluate_media_relevance(context: Mapping[str, Any], account_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Ground the reader benefit in observed action, not a platform/category label."""
    action = _compact(context.get("visible_action"))
    moment = _compact(context.get("key_moment"))
    verified = context.get("visual_status") == "VISUAL_VERIFIED"
    if context.get("strict_relevance_review"):
        review = context.get("account_relevance_review") or {}
        if not isinstance(review, Mapping):
            review = {}
        facts = [fact for fact in context.get("visual_facts", []) if fact["type"] in review.get("anchor_fact_types", [])]
        relevant = (verified and review.get("status") == "PASS"
                    and review.get("account_id") == context.get("account_id")
                    and bool(review.get("audience_need")) and bool(review.get("content_pillar"))
                    and any(fact["type"] == "visible_action" for fact in facts)
                    and bool(review.get("reason")))
        return {"status": "PASS" if relevant else "RELEVANCE_UNVERIFIED", "score": 80 if relevant else 20,
                "evidence": action if relevant else "", "key_moment": moment if relevant else "",
                "anchor_fact_ids": [fact["id"] for fact in facts] if relevant else [],
                "why_this_account_should_post_this": review.get("reason", "") if relevant else "RELEVANCE_UNVERIFIED"}
    terms = {
        "night_scout": ("接客", "時給", "出勤", "客", "店舗", "キャバ", "移籍"),
        "liver_manager": ("配信", "初見", "コメント", "リスナー", "ライブ", "ギフト"),
        "beauty_account": ("メイク", "肌", "コスメ", "ヘア", "リップ", "美容", "保湿"),
    }.get(str(context.get("account_id")), ())
    concrete = verified and len(action) >= 12 and len(moment) >= 8
    relevant = concrete and any(term in action + moment for term in terms)
    return {"status": "PASS" if relevant else "UNVERIFIED", "score": 80 if relevant else 20,
            "evidence": action if verified else "", "key_moment": moment if verified else "",
            "why_this_account_should_post_this": (
                f"「{moment}」で「{action}」が確認できる。{account_contract.get('audience', '')}に具体例として提示できる。"
                if relevant else "UNVERIFIED: account-specific observed action is missing"),
            "content_usefulness": "concrete_example" if relevant else "unverified"}


def select_media_angles(context: Mapping[str, Any], relevance: Mapping[str, Any]) -> dict[str, Any]:
    options = []
    if relevance.get("status") == "PASS":
        for kind, score in (("observation", 90), ("practical_takeaway", 75), ("commentary", 65)):
            options.append({"type": kind, "basis": relevance["evidence"],
                            "key_moment": relevance["key_moment"], "score": score,
                            "anchor_fact_ids": relevance.get("anchor_fact_ids") or [
                                fact["id"] for fact in context.get("visual_facts", [])
                                if fact["type"] in {"visible_action", "key_moment"}],
                            "media_asset_id": context["media_asset_id"]})
    return {"options": options[:3], "selected": max(options, key=lambda x: x["score"]) if options else {}}


def remove_media_test(caption: str, context: Mapping[str, Any], angle: Mapping[str, Any],
                      claim_support: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    from generation.semantic_alignment import LocalSemanticAlignmentProvider

    facts = {fact["id"]: fact for fact in context.get("visual_facts", [])
             if fact["id"] in angle.get("anchor_fact_ids", [])}
    supports = list(claim_support) if isinstance(claim_support, (list, tuple)) else []
    # Legacy literal captions can still provide evidence, but paraphrases use
    # explicit fact IDs and the existing semantic verifier instead of copying.
    if not supports:
        supports = [{"caption_claim": fact["text"], "source_evidence": fact["text"], "anchor_fact_ids": [fid]}
                    for fid, fact in facts.items() if _normalized(fact["text"]) in _normalized(caption)]
    accepted = []
    for support in supports:
        if not isinstance(support, Mapping):
            continue
        ids = support.get("anchor_fact_ids", [])
        claim = str(support.get("caption_claim") or "")
        evidence = str(support.get("source_evidence") or "")
        if not isinstance(ids, list) or not ids or any(not isinstance(fid, str) or fid not in facts for fid in ids):
            continue
        if not claim or _normalized(claim) not in _normalized(caption) or not evidence:
            continue
        source = "\n".join(facts[fid]["text"] for fid in ids)
        if _normalized(evidence) not in _normalized(source):
            continue
        verification = LocalSemanticAlignmentProvider().evaluate(
            source_text=source, public_post_text=caption, main_claims=[claim],
            claim_support=[{"caption_claim": claim, "source_evidence": evidence}], recent_posts=[])
        if any(item.get("verified") for item in (verification.data or {}).get("verified_claim_support", [])):
            accepted.append(dict(support))
    anchored = (context.get("visual_status") == "VISUAL_VERIFIED"
                and angle.get("media_asset_id") == context.get("media_asset_id") and bool(accepted))
    return {"status": "PASS" if anchored else "GENERIC_CAPTION_RISK_HIGH",
            "media_anchor_status": "PASS" if anchored else "UNVERIFIED",
            "anchor_fact_ids": sorted({fid for item in accepted for fid in item["anchor_fact_ids"]}) if anchored else [],
            "claim_support": accepted if anchored else [],
            "generic_caption_risk": "LOW" if anchored else "HIGH",
            "anchor_specificity": "verified_claim_to_visual_fact" if anchored else "insufficient"}


def fabricated_media_experience(caption: str) -> dict[str, Any]:
    # Attribution elsewhere in the paragraph must not excuse a first-person claim.
    ownership = re.search(
        r"(?:私|僕|俺|自分|当店|弊社|うち)(?:たち)?(?:が|は|も|の).{0,35}"
        r"(?:使った|使って|使い続け|試した|試して|経験した|売上|売り上げ|収入|稼い|稼げた|痩せた|肌が|所属|担当した|実績)", caption)
    return {"status": "BLOCKED" if ownership else "PASS",
            "reasons": ["source_creator_experience_reassigned"] if ownership else []}


def generate_media_first_caption(*, media: Mapping[str, Any], account_id: str,
                                 account_content_contract: Mapping[str, Any], recent_posts: list[str],
                                 caption_generator: Any, source_creator_context: str = "",
                                 editorial_draft: bool = False) -> dict[str, Any]:
    """Single caption entry: no I/O until evidence, eligibility and angle exist."""
    context = prepare_media_context(media, account_id=account_id, source_creator_context=source_creator_context)
    context["editorial_draft_only"] = editorial_draft
    relevance = evaluate_media_relevance(context, account_content_contract)
    angles = select_media_angles(context, relevance)
    base = {"media_context": context, "account_relevance": relevance, "post_angles": angles,
            "editorial_draft_eligibility": context["editorial_draft_eligibility"],
            "publish_eligibility": context["publish_eligibility"],
            "media_counted_as_success": False, "MEDIA_SUCCESS": False, "would_post": False}
    eligibility = context["editorial_draft_eligibility"] if editorial_draft else context["eligibility"]
    reasons = list(eligibility["hard_reasons"])
    if context["visual_status"] != "VISUAL_VERIFIED":
        reasons.append("visual_understanding_required")
    if not angles["selected"]:
        reasons.append("account_relevant_angle_unavailable")
    if reasons:
        return {**base, "status": "REVIEW_REQUIRED", "route_status": "DEGRADED_TO_TEXT",
                "public_post_text": "", "caption_attempt_count": 0, "blocked_reasons": reasons}
    output = caption_generator(media_context=context, selected_post_angle=angles["selected"],
                               account_content_contract=dict(account_content_contract), recent_posts=recent_posts)
    text = str(output.get("public_post_text") or "")
    experience = fabricated_media_experience(text)
    anchor = remove_media_test(text, context, angles["selected"], output.get("claim_support", []))
    reasons = list(output.get("blocked_reasons", []))
    reasons.extend(experience["reasons"])
    if anchor["status"] != "PASS":
        reasons.append("media_specific_anchor_missing")
    passed = output.get("status") == "PASS" and bool(text) and not reasons
    return {**output, **base, "status": "PASS" if passed else "REVIEW_REQUIRED",
            "public_post_text": text if passed else "", "rejected_caption": "" if passed else text,
            "route_status": "MEDIA_DRAFT" if passed else "DEGRADED_TO_TEXT",
            "blocked_reasons": reasons, "remove_media_test": anchor,
            "fabricated_experience_check": experience}


def build_post_package(
    *,
    account_id: str,
    media: Mapping[str, Any],
    public_caption: str,
    source_creator_context: str = "",
    why_account: str = "",
    hard_gate_result: Mapping[str, Any] | None = None,
    quality_components: Mapping[str, Any] | None = None,
    prepared_context: Mapping[str, Any] | None = None,
    prepared_relevance: Mapping[str, Any] | None = None,
    prepared_angles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    understanding = dict(prepared_context) if prepared_context is not None else prepare_media_context(
        media, account_id=account_id, source_creator_context=source_creator_context)
    caption = _compact(public_caption)
    relevance = dict(prepared_relevance or {})
    angles = list((prepared_angles or {}).get("options", []))
    selected = dict((prepared_angles or {}).get("selected", {}))
    anchor = remove_media_test(caption, understanding, selected, media.get("claim_support", []))
    anchor_status = anchor["status"]
    generic_risk = anchor["generic_caption_risk"]
    relevance_reason = relevance.get("why_this_account_should_post_this", "UNVERIFIED: no precaption relevance")
    result = {
        "account_id": account_id,
        "media_asset_id": understanding["media_asset_id"],
        "media_type": understanding["media_type"],
        "media_understanding": understanding,
        "why_this_account_should_post_this": relevance_reason,
        "post_angle_options": angles,
        "post_angle": selected or {"type": "unverified", "basis": ""},
        "hook": caption[:100],
        "caption": public_caption,
        "cta": "" if not re.search(r"(保存|いいね|フォロー|相談|試してみて)", caption) else "caption_contains_light_action",
        "claim_support": media.get("claim_support", []),
        "media_anchor": {**anchor, "remove_media_test": anchor_status},
        "fabricated_experience_check": fabricated_media_experience(public_caption),
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
