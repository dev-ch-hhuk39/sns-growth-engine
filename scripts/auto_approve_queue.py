#!/usr/bin/env python3
"""AUTO_READY gated approval for Threads queue rows.

This script evaluates WAITING_REVIEW queue items and promotes only safe,
text-only Threads candidates to READY. It never posts. AUTO_POST remains a
separate flag and the worker still requires its real-post triple gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import extract_public_post_text, final_public_post_validator  # noqa: E402
from hybrid_ai_gate import hybrid_ai_gate_passed, requires_hybrid_ai_gate  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from accounts.managed_accounts import account_choices, auto_ready_account_ids  # noqa: E402
from accounts.managed_accounts import managed_account  # noqa: E402

RULES_FILE = ROOT / "config/auto_approval_rules.json"
ALLOWED_ACCOUNTS = set(auto_ready_account_ids())
ELIGIBLE_STATUS = "WAITING_REVIEW"
READY_STATUS = "READY"
AUTO_READY_BY = "auto_approve_queue.py"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_rules(path: str | Path = RULES_FILE) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    accounts = data.get("accounts", {})
    return {"defaults": defaults, "accounts": accounts}


def rules_for_account(rules: dict[str, Any], account_id: str) -> dict[str, Any]:
    merged = dict(rules.get("defaults", {}))
    merged.update(rules.get("accounts", {}).get(account_id, {}))
    return merged


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def text_for_item(queue: dict[str, Any], draft: dict[str, Any] | None, derivative: dict[str, Any] | None) -> str:
    # 新しい生成パイプラインは投稿本文をqueueへ直接保存する。
    if str(queue.get("public_post_text", "")).strip():
        return extract_public_post_text(queue.get("public_post_text", ""))
    if derivative and str(derivative.get("text", "")).strip():
        return extract_public_post_text(derivative.get("text", ""))
    if draft:
        return extract_public_post_text(draft.get("body_md") or draft.get("content") or "")
    return ""


def tokenize_jp(text: str) -> set[str]:
    normalized = re.sub(r"[^\wぁ-んァ-ヶ一-龠ー]+", " ", text.lower())
    return {t for t in normalized.split() if len(t) >= 2}


def near_duplicate(text: str, existing_texts: list[str], threshold: float = 0.86) -> bool:
    n = normalize_text(text)
    if not n:
        return True
    for other in existing_texts:
        on = normalize_text(other)
        if n == on:
            return True
        a, b = tokenize_jp(text), tokenize_jp(other)
        if a and b and len(a & b) / max(1, len(a | b)) >= threshold:
            return True
    return False


def _contains_any(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if t and t.lower() in low]


def quality_score(text: str, account_id: str) -> tuple[int, dict[str, int]]:
    length = len(text)
    clarity = 12 if 80 <= length <= 420 else 8 if 40 <= length <= 520 else 4
    specificity = 12 if any(k in text for k in ("理由", "ポイント", "準備", "相談", "配信", "夜職", "店", "初見", "コメント")) else 8
    usefulness = 14 if any(k in text for k in ("整理", "具体", "改善", "大事", "選ぶ", "続け", "入りやすい", "変わる")) else 9
    account_terms = {
        "night_scout": ("夜職", "キャバ", "働く", "相談", "求人", "副収入"),
        "liver_manager": ("配信", "ライバー", "TikTok", "LIVE", "リスナー", "ギフト", "事務所"),
    }.get(account_id, ())
    if account_id == "night_scout":
        account_terms = (*account_terms, "移籍", "客層", "ノルマ", "担当", "出勤", "店")
    account_fit = 14 if any(k in text for k in account_terms) else 7
    first = text.splitlines()[0] if text else ""
    hook_strength = 12 if len(first) <= 45 and any(k in first for k in ("人", "理由", "ポイント", "仕組み", "見るべき")) else 7
    cta = 10 if any(k in text for k in ("相談", "プロフィール", "DM", "LINE")) else 6
    originality = 12 if any(k in text for k in ("自分", "生活", "空気", "環境", "無理", "初見", "担当", "相談")) else 9
    tone_fit = 14 if not any(k in text for k in ("!!!", "絶対", "誰でも", "今すぐ稼げ")) else 4
    parts = {
        "clarity": clarity,
        "specificity": specificity,
        "usefulness": usefulness,
        "account_fit": account_fit,
        "hook_strength": hook_strength,
        "cta_naturalness": cta,
        "originality": originality,
        "tone_fit": tone_fit,
    }
    return min(100, sum(parts.values())), parts


def risk_score(text: str, queue: dict[str, Any], rules: dict[str, Any]) -> tuple[int, dict[str, int]]:
    money_terms = ("絶対稼げる", "必ず稼げる", "保証", "誰でも月収", "確実に")
    legal_terms = ("違法", "脱税", "詐欺", "薬", "未成年")
    privacy_terms = ("晒す", "本名", "住所", "電話番号")
    brand_terms = ("暴露", "炎上", "叩く", "最悪")
    platform_terms = ("規約違反", "BAN回避", "裏技")
    rights = 0
    if str(queue.get("media_asset_id", "")).strip() or str(queue.get("video_clip_id", "")).strip():
        rights += 15
    if str(queue.get("media_reuse_risk", "")).lower() in {"high", "unknown"}:
        rights += 10
    parts = {
        "money_guarantee_risk": 25 if _contains_any(text, list(money_terms)) else 0,
        "legal_risk": 25 if _contains_any(text, list(legal_terms)) else 0,
        "privacy_risk": 25 if _contains_any(text, list(privacy_terms)) else 0,
        "brand_risk": 15 if _contains_any(text, list(brand_terms)) else 0,
        "rights_risk": rights,
        "platform_risk": 20 if _contains_any(text, list(platform_terms)) else 0,
        "controversy_risk": 10 if _contains_any(text, list(rules.get("sensitive_terms", []))) else 0,
    }
    return min(100, sum(parts.values())), parts


def safety_score(text: str, queue: dict[str, Any], rules: dict[str, Any]) -> tuple[int, dict[str, bool]]:
    blocked_hits = _contains_any(text, list(rules.get("blocked_terms", [])))
    sensitive_hits = _contains_any(text, list(rules.get("sensitive_terms", [])))
    risk, _ = risk_score(text, queue, rules)
    checks = {
        "no_income_guarantee": not any(k in text for k in ("絶対稼げる", "必ず稼げる", "保証")),
        "no_sensitive_personal_attack": not any(k in text for k in ("死ね", "晒す", "叩く")),
        "no_defamation": "詐欺" not in text,
        "no_third_party_rights_violation": not bool(str(queue.get("media_asset_id", "")).strip()),
        "no_adult_explicit": not any(k in text for k in ("性的", "裸", "アダルト")),
        "no_platform_policy_risk": "規約違反" not in text,
        "no_unverified_claim": not any(k in text for k in ("日本一", "業界No.1", "確実")),
        "no_private_info": not any(k in text for k in ("住所", "電話番号", "本名")),
        "no_blocked_terms": not blocked_hits,
        "no_sensitive_terms": not sensitive_hits,
        "low_risk": risk <= int(rules.get("max_risk_score", 10)),
    }
    return max(0, int(100 * sum(1 for ok in checks.values() if ok) / len(checks))), checks


def media_is_text_only(queue: dict[str, Any], draft: dict[str, Any] | None, derivative: dict[str, Any] | None) -> bool:
    values = [
        queue.get("media_asset_id", ""), queue.get("video_clip_id", ""), queue.get("source_video_url", ""),
        draft.get("media_asset_id", "") if draft else "", draft.get("video_clip_id", "") if draft else "",
        derivative.get("media_asset_id", "") if derivative else "",
    ]
    strategy = str((draft or {}).get("media_strategy") or queue.get("media_strategy") or "").strip().lower()
    return not any(str(v).strip() for v in values) and strategy in {"", "none", "text_only"}


def recommended_use_ok(draft: dict[str, Any] | None, scores_by_ref: dict[str, dict[str, Any]]) -> bool:
    ref = str((draft or {}).get("source_refs", "")).strip()
    rec = str(scores_by_ref.get(ref, {}).get("recommended_use", "REFERENCE_ONLY")).upper()
    return rec in {"REFERENCE_ONLY", "IDEA_SEED", "SAFE_TO_REWRITE", ""}


def evaluate_item(
    *,
    queue: dict[str, Any],
    draft: dict[str, Any] | None,
    derivative: dict[str, Any] | None,
    scores_by_ref: dict[str, dict[str, Any]],
    existing_texts: list[str],
    rules: dict[str, Any],
    source_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    account_id = str(queue.get("account_id", ""))
    platform = str(queue.get("platform", "")).lower()
    status = str(queue.get("status", "")).upper()
    text = text_for_item(queue, draft, derivative)
    q_score, q_parts = quality_score(text, account_id)
    r_score, r_parts = risk_score(text, queue, rules)
    s_score, s_parts = safety_score(text, queue, rules)
    public_validation = final_public_post_validator(text, account_id)
    voice_validation = dict(public_validation.get("voice_persona_check", {}))
    # The public validator is the stronger reader-facing quality contract. The
    # lightweight heuristic remains diagnostic and cannot reject a post that
    # already passes the public-quality evaluation.
    q_score = max(q_score, min(int(public_validation["public_post_quality_score"]), 90))
    r_score = max(r_score, int(public_validation["risk_score"]))
    reasons: list[str] = []

    if account_id not in ALLOWED_ACCOUNTS:
        reasons.append("account_not_allowed")
    if platform != "threads":
        reasons.append("platform_not_threads")
    if status != ELIGIBLE_STATUS:
        reasons.append("status_not_waiting_review")
    if str(queue.get("generation_mode", "")).strip() == "":
        reasons.append("not_generated_candidate")
    if requires_hybrid_ai_gate(queue):
        gate_ok, gate_reason = hybrid_ai_gate_passed(
            queue,
            source_context or {},
        )
        if not gate_ok:
            reasons.append(f"hybrid_ai_gate_{gate_reason}")
    if not recommended_use_ok(draft, scores_by_ref):
        reasons.append("recommended_use_not_allowed")
    if rules.get("kill_switch"):
        reasons.append("kill_switch")
    if not is_true(rules.get("auto_ready_enabled", False)):
        reasons.append("auto_ready_disabled")
    if rules.get("require_no_media_for_auto_ready", True) and not media_is_text_only(queue, draft, derivative):
        reasons.append("media_not_allowed_for_auto_ready")
    if not rules.get("allow_third_party_media", False) and str(queue.get("media_reuse_risk", "")).lower() in {"high", "unknown"} and not media_is_text_only(queue, draft, derivative):
        reasons.append("third_party_media_not_allowed")
    if _contains_any(text, list(rules.get("blocked_terms", []))):
        reasons.append("blocked_terms")
    if public_validation["status"] != "PASS":
        reasons.append("final_public_post_validator_blocked")
        reasons.extend(str(r) for r in public_validation["blocked_reasons"])
    if voice_validation.get("status") != "VOICE_PERSONA_PASS":
        reasons.append("voice_persona_not_pass")
        reasons.extend(str(r) for r in voice_validation.get("reasons", []))

    # New production-composition candidates carry an auditable generation
    # contract. Once present, every field must pass before AUTO_READY.
    if str(queue.get("feature_schema_version", "")).strip():
        if str(queue.get("feature_schema_version", "")) != "post_features_v1":
            reasons.append("feature_schema_version_unsupported")
        if str(queue.get("quality_gate_version", "")) != "generation_quality_v3":
            reasons.append("quality_gate_version_missing_or_stale")
        if str(queue.get("batch_diversity_status", "")).upper() != "PASS":
            reasons.append("batch_diversity_not_pass")
        if str(queue.get("topic_coherence_status", "")).upper() != "PASS":
            reasons.append("topic_coherence_not_pass")
        if not str(queue.get("primary_topic", "")).strip():
            reasons.append("primary_topic_missing")
        if not str(queue.get("structure_variant", "")).strip():
            reasons.append("structure_variant_missing")
        if str(queue.get("hook_topic_match", "")).lower() not in {"true", "1", "yes"}:
            reasons.append("hook_topic_mismatch")
        if str(queue.get("closing_topic_match", "")).lower() not in {"true", "1", "yes"}:
            reasons.append("closing_topic_mismatch")
        if str(queue.get("shared_hook_detected", "")).lower() in {"true", "1", "yes"}:
            reasons.append("shared_hook_detected")
        if str(queue.get("shared_closing_detected", "")).lower() in {"true", "1", "yes"}:
            reasons.append("shared_closing_detected")
    if q_score < int(rules.get("min_quality_score", 75)):
        reasons.append("quality_below_threshold")
    if s_score < int(rules.get("min_safety_score", 90)):
        reasons.append("safety_below_threshold")
    if r_score > int(rules.get("max_risk_score", 10)):
        reasons.append("risk_above_threshold")
    if int(public_validation["reader_value_score"]) < int(rules.get("min_reader_value_score", 80)):
        reasons.append("reader_value_below_threshold")
    if int(public_validation["naturalness_score"]) < int(rules.get("min_naturalness_score", 80)):
        reasons.append("naturalness_below_threshold")
    if int(public_validation["account_fit_score"]) < int(rules.get("min_account_fit_score", 80)):
        reasons.append("account_fit_below_threshold")
    if int(public_validation["cta_pressure_score"]) > int(rules.get("max_cta_pressure_score", 30)):
        reasons.append("cta_pressure_above_threshold")
    if near_duplicate(text, existing_texts):
        reasons.append("duplicate_or_near_duplicate")

    return {
        "queue_id": queue.get("queue_id", ""),
        "account_id": account_id,
        "status": "APPROVABLE" if not reasons else "REJECTED",
        "reasons": sorted(set(reasons)),
        "quality_score": q_score,
        "safety_score": s_score,
        "risk_score": r_score,
        "public_post_quality_score": public_validation["public_post_quality_score"],
        "internal_leak_score": public_validation["internal_leak_check"]["internal_leak_score"],
        "reader_value_score": public_validation["reader_value_score"],
        "naturalness_score": public_validation["naturalness_score"],
        "account_fit_score": public_validation["account_fit_score"],
        "cta_pressure_score": public_validation["cta_pressure_score"],
        "final_public_post_validator": public_validation["status"],
        "voice_persona_status": voice_validation.get("status", "BLOCKED"),
        "voice_persona_score": voice_validation.get("score", 0),
        "polite_ending_ratio": voice_validation.get("details", {}).get("business_polite_ratio", 1.0),
        "first_person_status": voice_validation.get("details", {}).get("first_person_status", "BLOCKED"),
        "formal_consultant_penalty": voice_validation.get("details", {}).get("formal_consultant_penalty", 100),
        "conversational_style_score": voice_validation.get("details", {}).get("conversational_style_score", 0),
        "feminine_warmth_score": voice_validation.get("details", {}).get("feminine_warmth_score", 0),
        "voice_blocked_reasons": voice_validation.get("reasons", []),
        "score_total": q_score + s_score - r_score,
        "quality_parts": q_parts,
        "safety_parts": s_parts,
        "risk_parts": r_parts,
        "text_length": len(text),
    }


def _parse_dt(value: Any) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def account_limits_ok(
    account_id: str,
    selected_times: dict[str, list[datetime]],
    logs: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    rules: dict[str, Any],
    *,
    exact_scheduled_candidate: bool = False,
) -> tuple[bool, str]:
    # The READY cap protects background inventory growth. An exact candidate
    # selected by a scheduled slot is already bounded to one row and remains
    # subject to the publisher's daily cap, cooldown and idempotency gates.
    # Existing READY inventory must not starve that scheduled slot.
    if exact_scheduled_candidate:
        return True, "exact_scheduled_candidate_uses_publish_limits"
    today = now_utc().date()
    daily_cap = int(rules.get("daily_ready_cap", 2))
    cooldown = int(rules.get("cooldown_minutes", 180))
    todays = 0
    times: list[datetime] = list(selected_times.get(account_id, []))
    canonical_queue_ids: set[str] = set()
    for row in queue_rows:
        if str(row.get("account_id", "")) != account_id:
            continue
        queue_id = str(row.get("queue_id", "")).strip()
        if queue_id:
            canonical_queue_ids.add(queue_id)
        at = _parse_dt(row.get("auto_ready_at"))
        if not at:
            continue
        status = str(row.get("status", "")).strip().upper()
        if status and status not in {"READY", "AUTO_READY", "PROCESSING"}:
            continue
        times.append(at)
        if at.date() == today:
            todays += 1
    counted_log_queue_ids: set[str] = set()
    for log in logs:
        if str(log.get("account_id", "")) != account_id:
            continue
        if str(log.get("operation", "")) != "queue_approved":
            continue
        if "auto_ready=true" not in str(log.get("details", "")):
            continue
        match = re.search(r"(?:^|\s)queue_id=([^\s,]+)", str(log.get("details", "")))
        queue_id = match.group(1) if match else ""
        if queue_id and (queue_id in canonical_queue_ids or queue_id in counted_log_queue_ids):
            continue
        if queue_id:
            counted_log_queue_ids.add(queue_id)
        at = _parse_dt(log.get("timestamp"))
        if at:
            times.append(at)
            if at.date() == today:
                todays += 1
    if todays >= daily_cap:
        return False, "daily_ready_cap_reached"
    if times and (now_utc() - max(times)) < timedelta(minutes=cooldown):
        return False, "cooldown_not_satisfied"
    return True, "ok"


def records(client: Any, logical: str) -> list[dict[str, Any]]:
    if hasattr(client, "_ws"):
        return [dict(r) for r in client._ws(logical).get_all_records()]
    attr = {
        "drafts": "_drafts",
        "social_derivatives": "_derivatives",
        "reference_post_scores": "_reference_post_scores",
        "posted_results": "_posted_results",
        "logs": "_logs",
        "queue": "_queue",
    }.get(logical, f"_{logical}")
    return [dict(r) for r in getattr(client, attr, [])]


def build_plan(client: Any, account_id: str, max_ready: int, rules: dict[str, Any], slot_id: str = "", queue_ids: set[str] | None = None) -> dict[str, Any]:
    all_queue_rows = records(client, "queue")
    queue_rows = [
        row for row in all_queue_rows
        if str(row.get("status", "")).upper() == ELIGIBLE_STATUS
    ]
    if account_id != "all":
        queue_rows = [r for r in queue_rows if r.get("account_id") == account_id]
    if slot_id:
        queue_rows = [r for r in queue_rows if str(r.get("slot_id", "")) == slot_id]
    if queue_ids:
        queue_rows = [r for r in queue_rows if str(r.get("queue_id", "")) in queue_ids]
    drafts = {str(r.get("draft_id", "")): r for r in records(client, "drafts")}
    derivatives = {
        (str(r.get("draft_id", "")), str(r.get("platform", "")).lower()): r
        for r in records(client, "social_derivatives")
    }
    scores_by_ref = {
        str(r.get("reference_post_id") or r.get("collected_post_id", "")): r
        for r in records(client, "reference_post_scores")
    }
    posted_texts = [str(r.get("posted_text", "")) for r in records(client, "posted_results") if str(r.get("posted_text", "")).strip()]
    ready_texts: list[str] = []
    logs = records(client, "logs")
    existing_for_dup = posted_texts + ready_texts
    evaluated = []
    approvable = []
    selected_times: dict[str, list[datetime]] = {}
    global_limit = max(0, max_ready)
    def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        gm = str(row.get("generation_mode", ""))
        generation_rank = 0 if gm == "reference_score_to_threads" else 1
        return (str(row.get("account_id", "")), generation_rank, int(str(row.get("priority", "999") or "999")), str(row.get("queue_id", "")))

    for q in sorted(queue_rows, key=_sort_key):
        acct = str(q.get("account_id", ""))
        acct_rules = rules_for_account(rules, acct)
        draft = drafts.get(str(q.get("draft_id", "")))
        deriv = derivatives.get((str(q.get("draft_id", "")), "threads"))
        ev = evaluate_item(
            queue=q,
            draft=draft,
            derivative=deriv,
            scores_by_ref=scores_by_ref,
            existing_texts=existing_for_dup,
            rules=acct_rules,
            source_context=build_source_context(client, q),
        )
        limit_ok, limit_reason = account_limits_ok(
            acct,
            selected_times,
            logs,
            all_queue_rows,
            acct_rules,
            exact_scheduled_candidate=bool(queue_ids and slot_id),
        )
        per_run = len(selected_times.get(acct, [])) < int(acct_rules.get("max_posts_per_run", 1))
        if ev["status"] == "APPROVABLE" and not limit_ok:
            ev["status"] = "REJECTED"
            ev["reasons"].append(limit_reason)
        if ev["status"] == "APPROVABLE" and not per_run:
            ev["status"] = "REJECTED"
            ev["reasons"].append("max_posts_per_run_reached")
        if ev["status"] == "APPROVABLE" and len(approvable) >= global_limit:
            ev["status"] = "REJECTED"
            ev["reasons"].append("max_ready_reached")
        evaluated.append(ev)
        if ev["status"] == "APPROVABLE":
            approvable.append(ev)
            selected_times.setdefault(acct, []).append(now_utc())
            text = text_for_item(q, draft, deriv)
            existing_for_dup.append(text)
    rejected = [r for r in evaluated if r["status"] != "APPROVABLE"]
    reason_counts: dict[str, int] = {}
    for row in rejected:
        for reason in row.get("reasons", []):
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    sample_rejected: list[dict[str, Any]] = []
    queue_by_id = {str(r.get("queue_id", "")): r for r in queue_rows}
    for row in rejected[:5]:
        q = queue_by_id.get(str(row.get("queue_id", "")), {})
        draft = drafts.get(str(q.get("draft_id", "")))
        deriv = derivatives.get((str(q.get("draft_id", "")), "threads"))
        sample_rejected.append({
            "queue_id": row.get("queue_id", ""),
            "account_id": row.get("account_id", ""),
            "reasons": row.get("reasons", []),
            "validator_status": row.get("final_public_post_validator", ""),
            "quality_score": row.get("quality_score", ""),
            "account_fit_score": row.get("account_fit_score", ""),
            "internal_leak_score": row.get("internal_leak_score", ""),
            "duplicate_status": "duplicate_or_near_duplicate" if "duplicate_or_near_duplicate" in row.get("reasons", []) else "PASS",
            "public_post_preview": text_for_item(q, draft, deriv)[:160],
        })
    return {
        "status": "PLAN_READY",
        "evaluated_count": len(evaluated),
        "approvable_count": len(approvable),
        "checked_count": len(evaluated),
        "approved_count": len(approvable),
        "rejected_count": len(rejected),
        "ready_count": len(approvable),
        "rejected_reasons": dict(sorted(reason_counts.items())),
        "sample_rejected_public_post_preview": sample_rejected,
        "selected_queue_ids": [r["queue_id"] for r in approvable],
        "results": evaluated,
    }


def apply_ready(client: Any, plan: dict[str, Any]) -> dict[str, Any]:
    ready = [r for r in plan["results"] if r["status"] == "APPROVABLE"]
    updated: list[str] = []
    at = now_iso()
    bulk_updates: list[tuple[str, dict[str, Any]]] = []
    for r in ready:
        qid = str(r["queue_id"])
        approval_policy = str(managed_account(str(r["account_id"])).get("review_policy", ""))
        reason = f"AUTO_READY quality={r['quality_score']} safety={r['safety_score']} risk={r['risk_score']}"
        fields = {
            "status": READY_STATUS,
            "auto_ready_by": AUTO_READY_BY,
            "auto_ready_reason": reason,
            "auto_ready_score": str(r["score_total"]),
            "auto_ready_at": at,
            "auto_publish": "true",
            "approval_source": approval_policy,
            "approval_policy": approval_policy,
            "approval_mode": "autonomous_safe",
            "automated_approved": "true",
            "human_approved": "false",
            "quality_score": str(r["quality_score"]),
            "safety_score": str(r["safety_score"]),
            "risk_score": str(r["risk_score"]),
            "validator_status": str(r.get("final_public_post_validator", "")),
            "internal_leak_status": "PASS" if int(r.get("internal_leak_score", 100)) == 0 else "BLOCKED",
            "account_fit_status": "PASS" if int(r.get("account_fit_score", 0)) >= 80 else "WARN",
            "public_post_quality_score": str(r.get("public_post_quality_score", "")),
            "reader_value_score": str(r.get("reader_value_score", "")),
            "naturalness_score": str(r.get("naturalness_score", "")),
            "cta_pressure_score": str(r.get("cta_pressure_score", "")),
            "voice_persona_status": str(r.get("voice_persona_status", "")),
            "voice_persona_score": str(r.get("voice_persona_score", "")),
            "polite_ending_ratio": str(r.get("polite_ending_ratio", "")),
            "first_person_status": str(r.get("first_person_status", "")),
            "formal_consultant_penalty": str(r.get("formal_consultant_penalty", "")),
            "conversational_style_score": str(r.get("conversational_style_score", "")),
            "feminine_warmth_score": str(r.get("feminine_warmth_score", "")),
            "voice_blocked_reasons": json.dumps(r.get("voice_blocked_reasons", []), ensure_ascii=False),
            "rejected_reason": "",
            "blocked_reason": "",
            "updated_at": at,
        }
        bulk_updates.append((qid, fields))
        client.log(
            operation="queue_approved",
            status="OK",
            message=f"queue_approved: queue_id={qid} WAITING_REVIEW→READY auto_ready=true",
            account_id=str(r["account_id"]),
            details=f"queue_id={qid} auto_ready=true reason={reason}",
            level="INFO",
        )
        updated.append(qid)
    for r in plan["results"]:
        if r["status"] == "APPROVABLE":
            continue
        qid = str(r.get("queue_id", ""))
        if not qid:
            continue
        reason = ",".join(str(x) for x in r.get("reasons", []))[:500]
        fields = {
            "validator_status": str(r.get("final_public_post_validator", "")),
            "internal_leak_status": "PASS" if int(r.get("internal_leak_score", 100)) == 0 else "BLOCKED",
            "account_fit_status": "PASS" if int(r.get("account_fit_score", 0)) >= 80 else "WARN",
            "quality_score": str(r.get("quality_score", "")),
            "safety_score": str(r.get("safety_score", "")),
            "risk_score": str(r.get("risk_score", "")),
            "public_post_quality_score": str(r.get("public_post_quality_score", "")),
            "reader_value_score": str(r.get("reader_value_score", "")),
            "naturalness_score": str(r.get("naturalness_score", "")),
            "cta_pressure_score": str(r.get("cta_pressure_score", "")),
            "rejected_reason": reason,
            "updated_at": at,
        }
        bulk_updates.append((qid, fields))
    if hasattr(client, "bulk_update_queue_items"):
        client.bulk_update_queue_items(bulk_updates)
    else:
        for queue_id, fields in bulk_updates:
            client.update_queue_item(queue_id, **fields)
    return {"updated_count": len(updated), "updated_queue_ids": updated}


def main() -> int:
    parser = argparse.ArgumentParser(description="AUTO_READY approve safe WAITING_REVIEW Threads queue rows")
    parser.add_argument("--dry-run", action="store_true", help="plan only (default)")
    parser.add_argument("--apply", action="store_true", help="write READY statuses (requires --confirm-auto-ready)")
    parser.add_argument("--confirm-auto-ready", action="store_true")
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--max-ready", type=int, default=1)
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--queue-id", action="append", default=[])
    parser.add_argument("--rules-file", default=str(RULES_FILE))
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--skip-setup", action="store_true", help="Assume Sheets tabs already exist and skip setup_all() to reduce read quota")
    args = parser.parse_args()

    rules = load_rules(args.rules_file)
    if args.use_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        if args.apply and args.confirm_auto_ready and not args.skip_setup:
            client.setup_all()
    else:
        from sheets_client import MockSheetsClient
        client = MockSheetsClient()

    plan = build_plan(client, args.account_id, args.max_ready, rules, args.slot_id, set(args.queue_id))
    if not args.apply:
        print(json.dumps({"mode": "dry-run", **plan}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_auto_ready:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-auto-ready", **plan}, ensure_ascii=False))
        return 1
    applied = apply_ready(client, plan)
    print(json.dumps({"status": "APPLIED", **plan, **applied}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
