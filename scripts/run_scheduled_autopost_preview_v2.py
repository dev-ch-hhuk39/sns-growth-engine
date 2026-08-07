#!/usr/bin/env python3
"""Generate and Gemini-review all ten scheduled slots without persistence.

The preview reads production Sheets, uses the same pure candidate builders as
production, evaluates ephemeral queue rows through the Hybrid Gemini gate, and
never invokes a publisher or a Sheets mutation method.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config
from gemini_hybrid_client import GeminiHybridClient
from hybrid_ai_gate import HybridAiGate
from hybrid_ai_source_context import build_source_context
from run_direct_reference_media_pipeline import build_plan as build_direct_plan
from run_media_production_pipeline import (
    _generate_final_media_caption,
    _recent_public_posts,
    build_plan as build_clip_plan,
)
from generate_threads_ideas_from_references import run_reference_generation
from sheets_client import SheetsClient
from sheets_record_reader import enable_readonly_record_cache, read_records_safely  # noqa: E402

JST = timezone(timedelta(hours=9))
TEXT_SLOTS = (
    ("night_scout", "ns_1400_reference", "reference_text"),
    ("night_scout", "ns_1600_original", "original_text"),
    ("night_scout", "ns_2500_pdca", "pdca_text"),
    ("liver_manager", "lm_1000_original", "original_text"),
    ("liver_manager", "lm_1300_reference", "reference_text"),
    ("liver_manager", "lm_2100_pdca", "pdca_text"),
)
MEDIA_SLOTS = (
    ("night_scout", "ns_1800_direct_media", "direct_reference_media"),
    ("night_scout", "ns_2100_clip_media", "approved_source_clip"),
    ("liver_manager", "lm_1600_direct_media", "direct_reference_media"),
    ("liver_manager", "lm_1800_clip_media", "approved_source_clip"),
)
PROTECTED_QUEUE_IDS = {
    "media_activation_liver_manager_approved_source_clip_c92d646a523bdbb5",
    "media_activation_liver_manager_direct_reference_media_177110184f553b45",
    "media_activation_night_scout_approved_source_clip_5698ff0b9340c2e7",
    "media_activation_night_scout_direct_reference_media_3921883bd6b80076",
}
REAL_ACTION_FLAGS = (
    "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
    "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API",
)
GENERIC_PHRASES = (
    "確認することは一つ。", "この順番で考える理由はシンプル。",
    "見るポイントは次の通り。", "次に試すこと：",
)
NOISE_RE = re.compile(r"\[(?:音楽|拍手|笑い|無音|BGM|music|applause|laughter)\]", re.I)
ORG_RE = re.compile(r"(?:株式会社|合同会社|有限会社|[一-龥ァ-ヶA-Za-z0-9]{2,24}グループ|プロダクション)")


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}



def _normalize_public_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\n", "\n").strip()


def _safe(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "<depth-limited>"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(token in low for token in ("token", "secret", "credential", "authorization", "api_key", "private_key")):
                out[str(key)] = "<redacted>" if item else ""
            else:
                out[str(key)] = _safe(item, depth + 1)
        return out
    if isinstance(value, list):
        return [_safe(item, depth + 1) for item in value[:30]]
    if isinstance(value, str):
        return value[:5000] + ("...<truncated>" if len(value) > 5000 else "")
    return value


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    try:
        return read_records_safely(client, logical)
    except Exception:
        return []


def _queue_fingerprint(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _action_flags() -> dict[str, bool]:
    state = {name: _true(os.environ.get(name)) for name in REAL_ACTION_FLAGS}
    enabled = [name for name, value in state.items() if value]
    if enabled:
        raise RuntimeError(f"real action flags enabled: {enabled}")
    return state


def _runtime() -> dict[str, Any]:
    reservations: list[dict[str, Any]] = []
    def reserve(metadata: dict[str, Any]) -> None:
        if len(reservations) >= 20:
            raise RuntimeError("readonly_account_request_limit_exceeded")
        reservations.append(dict(metadata))
    gemini = GeminiHybridClient(reserve_request=reserve)
    return {"gate": HybridAiGate(gemini), "gemini": gemini, "reservations": reservations}


def _quality(text: str, account_id: str, post_type: str) -> dict[str, Any]:
    text = _normalize_public_text(text)
    compact = re.sub(r"\s+", "", text)
    flags: list[str] = []
    observations: list[str] = []
    if not text:
        flags.append("public_post_text_empty")
    if NOISE_RE.search(text):
        flags.append("transcript_noise_present")
    if ORG_RE.search(text):
        flags.append("organization_or_brand_reference_present")
    if any(phrase in text for phrase in GENERIC_PHRASES):
        flags.append("generic_template_phrase_present")
    if len(compact) < 65:
        flags.append("too_short")
    if len(compact) > 500:
        flags.append("too_long")
    if account_id == "night_scout":
        if not any(term in text for term in ("キャバ", "夜職", "店", "指名", "時給", "手取り")):
            flags.append("night_scout_domain_signal_missing")
        if "僕" not in text:
            flags.append("night_scout_first_person_boku_missing")
    else:
        if not any(term in text for term in ("配信", "ライバー", "リスナー", "コメント", "初見")):
            flags.append("liver_manager_domain_signal_missing")
    if post_type == "pdca_text" and not any(term in text for term in ("結果", "数字", "反応", "前回", "仮説", "次は", "改善")):
        flags.append("pdca_observation_hypothesis_next_test_missing")
    return {"pass": not flags, "flags": sorted(set(flags)), "observations": observations, "character_count": len(compact)}


def _review(runtime: dict[str, Any], client: SheetsClient, candidate: dict[str, Any]) -> dict[str, Any]:
    before = len(runtime["reservations"])
    context = build_source_context(client, candidate)
    if not any(str(context.get(key, "")).strip() for key in ("original_post_text", "transcript_excerpt", "transcript", "description", "source_text")):
        context["source_text"] = str(candidate.get("public_post_text", ""))
    try:
        result = runtime["gate"].evaluate(candidate, context)
        return _safe({
            "status": result.status,
            "route": result.route,
            "public_post_text": result.public_post_text,
            "blocked_reasons": result.blocked_reasons,
            "actual_requests": len(runtime["reservations"]) - before,
            "source_context": context,
            "audit": result.audit(),
        })
    except Exception as exc:
        return {
            "status": "RUNTIME_ERROR", "route": "", "public_post_text": "",
            "blocked_reasons": [f"{type(exc).__name__}:hybrid_preview_failed"],
            "actual_requests": len(runtime["reservations"]) - before,
            "source_context": _safe(context),
        }


def _text_preview(client: SheetsClient, runtime: dict[str, Any], account_id: str, slot_id: str, post_type: str) -> dict[str, Any]:
    result = run_reference_generation(
        account_id, 1, apply=False, slot_id=slot_id, post_type=post_type,
        theme="", schedule_date_jst=datetime.now(JST).strftime("%Y-%m-%d"),
        require_measured_pdca=(post_type == "pdca_text"),
        include_preview_rows=True,
        client=client,
    )
    candidates = [dict(row) for row in result.get("preview_queue", [])]
    if not candidates:
        return {
            "account_id": account_id, "slot_id": slot_id, "post_type": post_type,
            "status": "NO_PREVIEW_CANDIDATE", "generation": _safe(result),
            "gemini": {"status": "NOT_RUN", "actual_requests": 0},
        }
    candidate = candidates[0]
    candidate.update({
        "account_id": account_id, "target_account_id": account_id,
        "platform": "threads", "slot_id": slot_id, "content_type": post_type,
    })
    reviewed = _review(runtime, client, candidate)
    final_text = str(reviewed.get("public_post_text") or candidate.get("public_post_text") or "")
    lineage_flags: list[str] = []
    if post_type == "reference_text" and not str(candidate.get("source_id", "")):
        lineage_flags.append("reference_source_missing")
    if post_type == "pdca_text" and str(candidate.get("generation_mode", "")) != "metrics_driven_pdca_text":
        lineage_flags.append("measured_pdca_lineage_missing")
    return {
        "account_id": account_id, "slot_id": slot_id, "post_type": post_type,
        "status": reviewed.get("status", ""), "candidate": _safe(candidate),
        "generation": _safe({key: value for key, value in result.items() if key != "preview_queue"}),
        "gemini": reviewed, "final_text": final_text,
        "quality": _quality(final_text, account_id, post_type),
        "lineage_flags": lineage_flags,
    }


def _direct_preview(client: SheetsClient, runtime: dict[str, Any], account_id: str, slot_id: str) -> dict[str, Any]:
    try:
        plan = build_direct_plan(account_id, slot_id, client, apply=False, prepare_only=True)
    except Exception as exc:
        return {"account_id": account_id, "slot_id": slot_id, "post_type": "direct_reference_media", "status": "RUNTIME_ERROR", "blocked_reasons": [f"{type(exc).__name__}:direct_preview_failed"]}
    if str(plan.get("status", "")) != "PLAN_ONLY" or not str(plan.get("public_post_text", "")):
        return {"account_id": account_id, "slot_id": slot_id, "post_type": "direct_reference_media", "status": str(plan.get("status", "NO_CANDIDATE")), "plan": _safe(plan), "gemini": {"status": "NOT_RUN", "actual_requests": 0}}
    post = dict(plan.get("source_post") or {})
    media = dict(plan.get("source_post_media") or {})
    candidate = {
        "queue_id": f"preview_{account_id}_{slot_id}_{post.get('source_post_id', '')}",
        "account_id": account_id, "target_account_id": account_id, "platform": "threads",
        "generation_mode": "direct_reference_media", "content_type": "direct_reference_media",
        "media_origin": "direct_reference", "caption_mode": plan.get("caption_mode", "transform"),
        "transformation_type": plan.get("transformation_type", "transform"),
        "source_id": post.get("source_id", ""), "source_post_id": post.get("source_post_id", ""),
        "media_asset_id": plan.get("media_asset_id", ""),
        "media_url": (plan.get("media_urls") or [media.get("storage_url", "")])[0],
        "media_type": media.get("media_type", ""), "duration_seconds": media.get("duration_seconds", ""),
        "rights_status": post.get("rights_status") or media.get("rights_status", ""),
        "permission_status": post.get("permission_status") or media.get("permission_status", ""),
        "public_post_text": plan.get("public_post_text", ""),
        "claim_support_json": json.dumps(plan.get("claim_support", []), ensure_ascii=False),
        "slot_id": slot_id,
    }
    reviewed = _review(runtime, client, candidate)
    final_text = str(reviewed.get("public_post_text") or candidate["public_post_text"])
    return {
        "account_id": account_id, "slot_id": slot_id, "post_type": "direct_reference_media",
        "status": reviewed.get("status", ""), "candidate": _safe(candidate),
        "source_post_url": post.get("canonical_post_url") or post.get("post_url") or post.get("source_post_url", ""),
        "source_original_text": post.get("original_post_text") or post.get("text", ""),
        "plan": _safe({key: value for key, value in plan.items() if key not in {"source_post", "source_post_media"}}),
        "gemini": reviewed, "final_text": final_text,
        "quality": _quality(final_text, account_id, "direct_reference_media"),
    }


def _clip_fallback_rows(client: SheetsClient, account_id: str) -> list[dict[str, Any]]:
    rows = [row for row in _records(client, "video_clip_candidates") if str(row.get("account_id", "")) == account_id]
    rows.sort(key=lambda row: (str(row.get("created_at", "")), str(row.get("clip_candidate_id", ""))), reverse=True)
    safe = []
    for row in rows[:5]:
        safe.append({
            "clip_candidate_id": row.get("clip_candidate_id") or row.get("clip_id", ""),
            "source_video_id": row.get("source_video_id", ""),
            "clip_status": row.get("clip_status") or row.get("reviewer_status", ""),
            "start_seconds": row.get("start_seconds") or row.get("start_time", ""),
            "end_seconds": row.get("end_seconds") or row.get("end_time", ""),
            "duration_seconds": row.get("duration_seconds", ""),
            "transcript_excerpt": str(row.get("transcript_excerpt") or row.get("transcript_text") or "")[:900],
            "rights_status": row.get("rights_status", ""),
            "permission_status": row.get("permission_status", ""),
            "blocked_reason": row.get("blocked_reason") or row.get("last_error", ""),
        })
    return safe


def _clip_preview(client: SheetsClient, runtime: dict[str, Any], account_id: str, slot_id: str) -> dict[str, Any]:
    try:
        plan = build_clip_plan(apply=False, confirm=False, client=client, account_id=account_id, prepare_only=True, slot_id=slot_id)
    except Exception as exc:
        return {"account_id": account_id, "slot_id": slot_id, "post_type": "approved_source_clip", "status": "RUNTIME_ERROR", "blocked_reasons": [f"{type(exc).__name__}:clip_preview_failed"]}
    clip = dict(plan.get("selected_clip") or {})
    source_video = dict(plan.get("selected_source_video") or {})
    if not clip or not source_video:
        return {
            "account_id": account_id, "slot_id": slot_id, "post_type": "approved_source_clip",
            "status": str(plan.get("status", "NO_CANDIDATE")), "plan": _safe(plan),
            "recent_clip_candidates": _safe(_clip_fallback_rows(client, account_id)),
            "gemini": {"status": "NOT_RUN", "actual_requests": 0},
        }
    duration = clip.get("duration_seconds", "")
    caption = _generate_final_media_caption(
        clip=clip, source_video=source_video,
        media_asset={"duration_seconds": duration, "aspect_ratio": "9:16"},
        account_id=account_id,
        recent_posts=_recent_public_posts(_records(client, "posted_results"), account_id),
        max_attempts=3,
    )
    candidate = {
        "queue_id": f"preview_{account_id}_{slot_id}_{clip.get('clip_candidate_id') or clip.get('clip_id', '')}",
        "account_id": account_id, "target_account_id": account_id, "platform": "threads",
        "generation_mode": "approved_source_clip", "content_type": "approved_source_clip",
        "media_origin": "approved_source_clip",
        "source_id": source_video.get("source_id", ""),
        "source_video_id": source_video.get("source_video_id", ""),
        "clip_candidate_id": clip.get("clip_candidate_id") or clip.get("clip_id", ""),
        "source_url": source_video.get("canonical_video_url") or source_video.get("source_video_url", ""),
        "source_time_range": f"{clip.get('start_seconds') or clip.get('start_time', '')}-{clip.get('end_seconds') or clip.get('end_time', '')}",
        "duration_seconds": duration,
        "rights_status": clip.get("rights_status") or source_video.get("rights_status", ""),
        "permission_status": clip.get("permission_status") or source_video.get("permission_status", ""),
        "public_post_text": caption.get("public_post_text", ""),
        "claim_support_json": caption.get("claim_support_json", "[]"),
        "slot_id": slot_id,
    }
    reviewed = _review(runtime, client, candidate) if caption.get("status") == "PASS" else {"status": "NOT_RUN", "actual_requests": 0, "blocked_reasons": caption.get("blocked_reasons", [])}
    final_text = str(reviewed.get("public_post_text") or candidate.get("public_post_text") or "")
    return {
        "account_id": account_id, "slot_id": slot_id, "post_type": "approved_source_clip",
        "status": reviewed.get("status", caption.get("status", "")), "candidate": _safe(candidate),
        "source_video_url": candidate["source_url"],
        "clip_start_seconds": clip.get("start_seconds") or clip.get("start_time", ""),
        "clip_end_seconds": clip.get("end_seconds") or clip.get("end_time", ""),
        "transcript_excerpt": str(clip.get("transcript_excerpt") or clip.get("transcript_text") or "")[:1600],
        "caption": _safe(caption), "gemini": reviewed, "final_text": final_text,
        "quality": _quality(final_text, account_id, "approved_source_clip"),
        "plan": _safe({key: value for key, value in plan.items() if key not in {"selected_clip", "selected_source_video", "selected_media_asset"}}),
    }


def _activation() -> dict[str, Any]:
    completed = subprocess.run([sys.executable, "scripts/scheduled_publish_activation_gate.py", "--use-sheets"], cwd=ROOT, text=True, capture_output=True, check=False)
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        pass
    return _safe({"returncode": completed.returncode, "payload": payload, "stderr_tail": completed.stderr[-1200:]})


def _diversity(items: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            if left.get("account_id") != right.get("account_id"):
                continue
            a = re.sub(r"\s+", "", str(left.get("final_text", "")))
            b = re.sub(r"\s+", "", str(right.get("final_text", "")))
            if not a or not b:
                continue
            similarity = SequenceMatcher(None, a, b).ratio()
            if similarity >= 0.68:
                issues.append({"account_id": left["account_id"], "left_slot": left["slot_id"], "right_slot": right["slot_id"], "similarity": round(similarity, 4)})
    return {"status": "PASS" if not issues else "BLOCKED", "threshold": 0.68, "issues": issues}


def main() -> int:
    flags = _action_flags()
    cfg = get_config()
    client = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
    enable_readonly_record_cache(client)
    queue_before = _records(client, "queue")
    protected_before = {str(row.get("queue_id", "")): dict(row) for row in queue_before if str(row.get("queue_id", "")) in PROTECTED_QUEUE_IDS}
    runtimes = {account: _runtime() for account in ("night_scout", "liver_manager")}

    slots: list[dict[str, Any]] = []
    for account_id, slot_id, post_type in TEXT_SLOTS:
        slots.append(_text_preview(client, runtimes[account_id], account_id, slot_id, post_type))
    for account_id, slot_id, post_type in MEDIA_SLOTS:
        if post_type == "direct_reference_media":
            slots.append(_direct_preview(client, runtimes[account_id], account_id, slot_id))
        else:
            slots.append(_clip_preview(client, runtimes[account_id], account_id, slot_id))

    slot_status_counts: dict[str, int] = {}
    for slot in slots:
        if "final_text" in slot:
            slot["final_text"] = _normalize_public_text(slot.get("final_text", ""))
        for key in ("candidate", "gemini"):
            payload = slot.get(key)
            if isinstance(payload, dict) and "public_post_text" in payload:
                payload["public_post_text"] = _normalize_public_text(
                    payload.get("public_post_text", "")
                )
        preview_reasons = [str(item) for item in slot.get("lineage_flags", []) if str(item)]
        quality = slot.get("quality")
        if isinstance(quality, dict) and not bool(quality.get("pass")):
            preview_reasons.extend(str(item) for item in quality.get("flags", []) if str(item))
        if preview_reasons:
            slot["preview_blocked_reasons"] = sorted(set(preview_reasons))
            if str(slot.get("status", "")).upper() == "PASS":
                slot["status"] = "BLOCKED"
        status_key = str(slot.get("status", "UNKNOWN")).upper() or "UNKNOWN"
        slot_status_counts[status_key] = slot_status_counts.get(status_key, 0) + 1

    queue_after = _records(client, "queue")
    protected_after = {str(row.get("queue_id", "")): dict(row) for row in queue_after if str(row.get("queue_id", "")) in PROTECTED_QUEUE_IDS}
    report = {
        "schema_version": "scheduled_autopost_preview_v2",
        "status": (
            "PREVIEW_COMPLETE"
            if slot_status_counts == {"PASS": len(slots)}
            else "PREVIEW_COMPLETE_WITH_BLOCKS"
        ),
        "slot_status_counts": slot_status_counts,
        "generated_at_jst": datetime.now(JST).isoformat(),
        "slot_count": len(slots),
        "would_post": False,
        "writes_performed": False,
        "real_action_flags": flags,
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "gemini_request_counts": {account: len(runtime["reservations"]) for account, runtime in runtimes.items()},
        "slots": slots,
        "cross_slot_diversity": _diversity(slots),
        "activation_gate": _activation(),
        "queue_row_count_before": len(queue_before),
        "queue_row_count_after": len(queue_after),
        "queue_unchanged": _queue_fingerprint(queue_before) == _queue_fingerprint(queue_after),
        "protected_rows_unchanged": _queue_fingerprint(list(protected_before.values())) == _queue_fingerprint(list(protected_after.values())),
    }
    rendered = json.dumps(_safe(report), ensure_ascii=False, indent=2, sort_keys=True)
    print("=== SCHEDULED_AUTOPOST_PREVIEW_V2_BEGIN ===")
    print(rendered)
    print("=== SCHEDULED_AUTOPOST_PREVIEW_V2_END ===")
    output = os.environ.get("SCHEDULED_AUTOPOST_PREVIEW_V2_OUTPUT", "").strip()
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
