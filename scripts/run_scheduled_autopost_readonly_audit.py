#!/usr/bin/env python3
"""Read-only audit of all ten scheduled autopost slots.

This command never writes to Sheets and never calls a publisher. It reads the
production queue, generates text-slot plans in dry-run mode, runs the Hybrid
Gemini gate in dry-run mode, and reads the activation gate.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
QUEUE_SHEET = "投稿キュー"

TEXT_SLOTS = [
    ("night_scout", "ns_1400_reference", "reference_text"),
    ("night_scout", "ns_1600_original", "original_text"),
    ("night_scout", "ns_2500_pdca", "pdca_text"),
    ("liver_manager", "lm_1000_original", "original_text"),
    ("liver_manager", "lm_1300_reference", "reference_text"),
    ("liver_manager", "lm_2100_pdca", "pdca_text"),
]
MEDIA_SLOTS = [
    ("night_scout", "ns_1800_direct_media", "direct_reference_media"),
    ("night_scout", "ns_2100_clip_media", "approved_source_clip"),
    ("liver_manager", "lm_1600_direct_media", "direct_reference_media"),
    ("liver_manager", "lm_1800_clip_media", "approved_source_clip"),
]
ALL_SLOTS = TEXT_SLOTS + MEDIA_SLOTS

PROTECTED_QUEUE_IDS = {
    "media_activation_liver_manager_approved_source_clip_c92d646a523bdbb5",
    "media_activation_liver_manager_direct_reference_media_177110184f553b45",
    "media_activation_night_scout_approved_source_clip_5698ff0b9340c2e7",
    "media_activation_night_scout_direct_reference_media_3921883bd6b80076",
}
PROTECTED_EXPECTED = {
    "excluded_from_activation": "true",
    "excluded_from_metrics_baseline": "true",
    "repost_prohibited": "true",
    "blocked_reason": "hybrid_ai_semantic_gate_pending",
    "superseded_reason": "audience_source_policy_and_text_quality_review_required",
    "error": "hybrid_ai_semantic_gate_pending",
}

REAL_ACTION_FLAGS = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_REAL_X_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API",
)

SAFE_QUEUE_FIELDS = (
    "queue_id",
    "account_id",
    "target_account_id",
    "platform",
    "status",
    "priority",
    "content_slot_id",
    "content_slot_date",
    "generation_mode",
    "media_strategy",
    "public_post_text",
    "source_id",
    "source_url",
    "source_post_id",
    "source_post_url",
    "source_post_text",
    "source_text",
    "source_caption",
    "original_post_text",
    "media_asset_id",
    "media_url",
    "media_type",
    "media_status",
    "media_ready",
    "duration_seconds",
    "aspect_ratio",
    "source_video_id",
    "clip_candidate_id",
    "clip_start_end",
    "rights_status",
    "permission_status",
    "validator_status",
    "internal_leak_status",
    "account_fit_status",
    "alignment_status",
    "hybrid_ai_status",
    "hybrid_ai_reason",
    "hybrid_ai_provider",
    "quality_score",
    "risk_score",
    "evidence_map",
    "blocked_reason",
    "rejected_reason",
    "superseded_reason",
    "error",
    "created_at",
    "updated_at",
    "scheduled_at",
)

SENSITIVE_KEY_PARTS = ("token", "secret", "credential", "authorization", "api_key", "private_key")
TEXT_KEYS = {
    "public_post_preview",
    "public_post_text",
    "planned_post_text",
    "post_text",
    "body_md",
}
NOISE_RE = re.compile(r"\[(?:音楽|拍手|笑い|無音|BGM|music|applause|laughter)\]", re.IGNORECASE)
ORG_RE = re.compile(r"(?:株式会社|合同会社|有限会社|[一-龥ァ-ヶA-Za-z0-9]{2,24}グループ|プロダクション)")
ACTION_RE = re.compile(r"(?:確認|決め|見直|分け|記録|振り返|質問|比べ|整理|試し|相談|伝え|設定|固定|選ぶ|変える)")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def normalized_bool(value: Any) -> str:
    return "true" if truthy(value) else "false"


def assert_fail_closed_environment() -> dict[str, str]:
    state = {name: str(os.environ.get(name, "")) for name in REAL_ACTION_FLAGS}
    unsafe = {name: value for name, value in state.items() if truthy(value)}
    if unsafe:
        raise RuntimeError(f"unsafe real-action flags enabled: {sorted(unsafe)}")
    return {name: normalized_bool(value) for name, value in state.items()}


def decode_service_account() -> dict[str, Any]:
    raw = (os.environ.get("GCP_SA_JSON_BASE64") or os.environ.get("SA_JSON_BASE64") or "").strip()
    if not raw:
        raise RuntimeError("Sheets service-account secret is missing")
    if raw.startswith("{"):
        return json.loads(raw)
    padding = "=" * (-len(raw) % 4)
    decoded = base64.b64decode(raw + padding).decode("utf-8")
    return json.loads(decoded)


def spreadsheet_id() -> str:
    value = (os.environ.get("SNS_MASTER_SHEET_ID") or os.environ.get("SPREADSHEET_ID") or "").strip()
    if not value:
        raise RuntimeError("Sheets spreadsheet ID secret is missing")
    return value


def read_queue_rows() -> list[dict[str, str]]:
    import gspread

    client = gspread.service_account_from_dict(decode_service_account())
    worksheet = client.open_by_key(spreadsheet_id()).worksheet(QUEUE_SHEET)
    values = worksheet.get_all_values()
    if not values:
        return []
    headers = [str(item).strip() for item in values[0]]
    rows: list[dict[str, str]] = []
    for raw_row in values[1:]:
        padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
        rows.append({header: str(padded[index]) for index, header in enumerate(headers) if header})
    return rows


def row_fingerprint(row: dict[str, Any] | None) -> str:
    if row is None:
        return "MISSING"
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def protected_snapshot(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_id = {row.get("queue_id", ""): row for row in rows}
    output: dict[str, Any] = {}
    for queue_id in sorted(PROTECTED_QUEUE_IDS):
        row = by_id.get(queue_id)
        actual = {key: (row or {}).get(key, "") for key in PROTECTED_EXPECTED}
        matches = {
            key: (normalized_bool(actual[key]) == expected if expected == "true" else str(actual[key]) == expected)
            for key, expected in PROTECTED_EXPECTED.items()
        }
        output[queue_id] = {
            "present": row is not None,
            "fingerprint": row_fingerprint(row),
            "required_values": actual,
            "required_values_match": all(matches.values()),
            "field_matches": matches,
        }
    return output


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found.append((index, index + end, value))
    found.sort(key=lambda item: (item[1], -item[0]))
    return [item[2] for item in found]


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "<depth-limited>"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in SENSITIVE_KEY_PARTS):
                out[key_text] = "<redacted>" if item else ""
            else:
                out[key_text] = sanitize(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(item, depth=depth + 1) for item in value[:25]]
    if isinstance(value, str):
        return value if len(value) <= 3000 else value[:3000] + "...<truncated>"
    return value


def run_json_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    objects = extract_json_objects(completed.stdout)
    payload = objects[-1] if objects else {}
    return {
        "command": [item for item in command if item not in {"--apply", "--confirm-autonomous", "--confirm-real-post"}],
        "returncode": completed.returncode,
        "payload": sanitize(payload),
        "stderr_tail": sanitize(completed.stderr[-1200:]),
        "json_found": bool(objects),
    }


def iter_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TEXT_KEYS and isinstance(item, str) and item.strip():
                yield item.strip()
            yield from iter_text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_text_values(item)


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def assess_text_quality(text: str, account_id: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", "", text)
    flags: list[str] = []
    observations: list[str] = []
    if NOISE_RE.search(text):
        flags.append("transcript_noise_present")
    if ORG_RE.search(text):
        flags.append("organization_or_brand_reference_present")
    quoted_segments = re.findall(r"[「『\"]([^」』\"]{8,})[」』\"]", text)
    quoted_chars = sum(len(item) for item in quoted_segments)
    if quoted_chars >= 24 or (quoted_segments and quoted_chars / max(1, len(compact)) >= 0.2):
        flags.append("quote_heavy_or_verbatim_risk")
    if len(compact) < 65:
        flags.append("too_short_for_context_and_action")
    if len(compact) > 520:
        flags.append("too_long_for_threads")
    if not ACTION_RE.search(text):
        flags.append("concrete_action_missing")
    if account_id == "night_scout":
        if "夜職" not in text and "キャバ" not in text and "店" not in text and "指名" not in text:
            flags.append("night_scout_domain_signal_missing")
        if "僕" not in text:
            observations.append("night_scout_first_person_boku_not_used")
    if account_id == "liver_manager":
        if "配信" not in text and "ライバー" not in text and "リスナー" not in text:
            flags.append("liver_manager_domain_signal_missing")
    return {
        "character_count_no_whitespace": len(compact),
        "flags": sorted(set(flags)),
        "observations": sorted(set(observations)),
        "pass": not flags,
    }


def source_text_from_row(row: dict[str, str]) -> str:
    for key in ("source_post_text", "source_text", "source_caption", "original_post_text"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    for key, value in row.items():
        low = key.lower()
        if "source" in low and any(part in low for part in ("text", "caption", "body")) and str(value).strip():
            return str(value).strip()
    return ""


def safe_queue_row(row: dict[str, str], account_id: str, post_type: str) -> dict[str, Any]:
    safe = {key: row.get(key, "") for key in SAFE_QUEUE_FIELDS if row.get(key, "") != ""}
    text = str(row.get("public_post_text", "")).strip()
    source_text = source_text_from_row(row)
    safe["quality_review"] = assess_text_quality(text, account_id) if text else {
        "pass": False,
        "flags": ["public_post_text_empty"],
        "observations": [],
        "character_count_no_whitespace": 0,
    }
    media_present = bool(row.get("media_asset_id") or row.get("media_url"))
    if post_type == "direct_reference_media":
        safe["direct_reuse_contract"] = {
            "media_present": media_present,
            "source_identity_present": bool(row.get("source_id") or row.get("source_url") or row.get("source_post_id") or row.get("source_post_url")),
            "source_text_available_for_reuse_check": bool(source_text),
            "source_text_similarity": round(SequenceMatcher(None, source_text, text).ratio(), 4) if source_text and text else None,
        }
    if post_type == "approved_source_clip":
        try:
            duration = float(str(row.get("duration_seconds", "") or 0))
        except ValueError:
            duration = 0.0
        safe["clip_contract"] = {
            "media_present": media_present,
            "clip_candidate_present": bool(row.get("clip_candidate_id")),
            "source_video_present": bool(row.get("source_video_id") or row.get("source_url")),
            "duration_seconds": duration or None,
            "duration_in_review_range_8_to_45_seconds": 8.0 <= duration <= 45.0 if duration else False,
            "evidence_present": bool(row.get("evidence_map")),
        }
    return safe


def row_sort_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(row.get("updated_at", "")),
        str(row.get("created_at", "")),
        str(row.get("scheduled_at", "")),
        str(row.get("queue_id", "")),
    )


def queue_candidates(rows: list[dict[str, str]], account_id: str, slot_id: str, post_type: str) -> dict[str, Any]:
    exact = [
        row for row in rows
        if row.get("queue_id", "") not in PROTECTED_QUEUE_IDS
        and str(row.get("account_id") or row.get("target_account_id") or "") == account_id
        and str(row.get("content_slot_id", "")) == slot_id
    ]
    exact.sort(key=row_sort_key, reverse=True)
    recent_account = [
        row for row in rows
        if row.get("queue_id", "") not in PROTECTED_QUEUE_IDS
        and str(row.get("account_id") or row.get("target_account_id") or "") == account_id
        and (str(row.get("media_asset_id", "")) or str(row.get("media_url", "")))
    ]
    recent_account.sort(key=row_sort_key, reverse=True)
    return {
        "exact_candidate_count": len(exact),
        "exact_candidates": [safe_queue_row(row, account_id, post_type) for row in exact[:5]],
        "recent_account_media_when_exact_missing": [] if exact else [safe_queue_row(row, account_id, post_type) for row in recent_account[:3]],
    }


def activation_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("reasons", "blocked_reasons", "missing", "errors"):
        value = payload.get(key)
        if isinstance(value, list):
            reasons.extend(str(item) for item in value)
        elif value:
            reasons.append(str(value))
    if payload.get("reason"):
        reasons.append(str(payload["reason"]))
    return unique(reasons)


def markdown_text(text: str) -> str:
    return text.replace("```", "''' ")


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Scheduled Autopost Read-Only Audit",
        "",
        f"- Overall status: `{report['status']}`",
        f"- Gemini key present: `{report['secret_presence']['gemini_api_key']}`",
        f"- Sheets credentials present: `{report['secret_presence']['sheets_credentials']}`",
        f"- Sheets ID present: `{report['secret_presence']['sheets_id']}`",
        f"- Protected rows unchanged during audit: `{report['protected_rows_unchanged_during_audit']}`",
        "",
        "### Activation gate",
        "",
        f"- Return code: `{report['activation_gate']['returncode']}`",
        f"- Allowed: `{report['activation_gate'].get('allowed')}`",
        f"- Reasons: `{json.dumps(report['activation_gate'].get('reasons', []), ensure_ascii=False)}`",
        "",
        "### Text slots",
    ]
    for item in report["text_slots"]:
        lines.extend(["", f"#### `{item['slot_id']}`", f"- Account: `{item['account_id']}`", f"- Dry-run return code: `{item['dry_run']['returncode']}`"])
        if not item["planned_texts"]:
            lines.append("- Planned text: **not found**")
        for index, text in enumerate(item["planned_texts"], 1):
            lines.extend([f"- Planned text {index}:", "", "```text", markdown_text(text), "```"])
            lines.append(f"- Quality: `{json.dumps(item['quality_reviews'][index - 1], ensure_ascii=False)}`")
        lines.append(f"- Hybrid dry-run: `{json.dumps(item['hybrid_gate_summary'], ensure_ascii=False)}`")
    lines.extend(["", "### Media slots"])
    for item in report["media_slots"]:
        lines.extend([
            "",
            f"#### `{item['slot_id']}`",
            f"- Account: `{item['account_id']}`",
            f"- Exact candidate count: `{item['queue']['exact_candidate_count']}`",
            f"- Hybrid dry-run: `{json.dumps(item['hybrid_gate_summary'], ensure_ascii=False)}`",
        ])
        for candidate in item["queue"]["exact_candidates"]:
            lines.extend([
                f"- Queue ID: `{candidate.get('queue_id', '')}`",
                f"- Status: `{candidate.get('status', '')}`",
                "- Planned caption:",
                "",
                "```text",
                markdown_text(str(candidate.get("public_post_text", ""))),
                "```",
                f"- Quality: `{json.dumps(candidate.get('quality_review', {}), ensure_ascii=False)}`",
                f"- Media contract: `{json.dumps(candidate.get('direct_reuse_contract') or candidate.get('clip_contract') or {}, ensure_ascii=False)}`",
            ])
    lines.extend(["", "### Protected rows", ""])
    for queue_id, item in report["protected_rows_after"].items():
        lines.append(f"- `{queue_id}` present=`{item['present']}` required-values-match=`{item['required_values_match']}` fingerprint=`{item['fingerprint']}`")
    lines.append("")
    return "\n".join(lines)


def create_readonly_hybrid_runtime() -> tuple[Any, Any, Any, list[dict[str, Any]]]:
    """Create a Gemini gate with an in-memory budget ledger only.

    The production Hybrid CLI uses a Sheets-backed reservation ledger even in
    dry-run mode. This audit deliberately bypasses that writer and records
    request reservations only in memory.
    """
    sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]
    from config_loader import get_config
    from gemini_hybrid_client import GeminiHybridClient
    from hybrid_ai_gate import HybridAiGate
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
    reservations: list[dict[str, Any]] = []

    def reserve_request(metadata: dict[str, Any]) -> None:
        if len(reservations) >= 20:
            raise RuntimeError("readonly_hybrid_execution_limit_exceeded")
        reservations.append(dict(metadata))

    gemini = GeminiHybridClient(reserve_request=reserve_request)
    gate = HybridAiGate(gemini)
    return client, gate, gemini, reservations


def readonly_hybrid_review(
    client: Any,
    gate: Any,
    gemini: Any,
    reservations: list[dict[str, Any]],
    rows: list[dict[str, str]],
    account_id: str,
    slot_id: str,
) -> dict[str, Any]:
    from hybrid_ai_policy import requires_hybrid_ai_gate
    from hybrid_ai_source_context import build_source_context

    eligible = [
        row
        for row in rows
        if row.get("queue_id", "") not in PROTECTED_QUEUE_IDS
        and str(row.get("account_id") or row.get("target_account_id") or "") == account_id
        and str(row.get("status", "")).upper() == "WAITING_REVIEW"
        and str(row.get("content_slot_id") or row.get("slot_id") or "") == slot_id
        and str(row.get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
        and str(row.get("repost_prohibited", "")).lower() not in {"true", "1", "yes"}
        and requires_hybrid_ai_gate(row)
    ]
    eligible.sort(key=row_sort_key, reverse=True)
    if not eligible:
        return {
            "status": "NO_EXACT_CANDIDATE",
            "queue_id": "",
            "account_id": account_id,
            "slot_id": slot_id,
            "actual_requests": 0,
            "no_ready_transition": True,
            "no_post": True,
        }

    queue = dict(eligible[0])
    queue_id = str(queue.get("queue_id", ""))
    before_requests = len(reservations)
    try:
        source_context = build_source_context(client, queue)
        result = gate.evaluate(queue, source_context)
    except Exception as exc:
        return {
            "status": "RUNTIME_ERROR",
            "queue_id": queue_id,
            "account_id": account_id,
            "slot_id": slot_id,
            "error_type": type(exc).__name__,
            "actual_requests": len(reservations) - before_requests,
            "no_ready_transition": True,
            "no_post": True,
        }

    return sanitize({
        "status": result.status,
        "queue_id": queue_id,
        "account_id": account_id,
        "slot_id": slot_id,
        "route": result.route,
        "blocked_reasons": list(result.blocked_reasons),
        "public_post_text": result.public_post_text,
        "actual_requests": len(reservations) - before_requests,
        "gemini_actual_request_count_total": getattr(gemini, "actual_request_count", None),
        "audit": result.audit(),
        "no_ready_transition": True,
        "no_post": True,
    })


def hybrid_gate_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", ""),
        "queue_id": result.get("queue_id", ""),
        "route": result.get("route", ""),
        "blocked_reasons": result.get("blocked_reasons", []),
        "actual_requests": result.get("actual_requests", 0),
        "gemini_key_missing_signal": "NO_GEMINI" in json.dumps(result, ensure_ascii=False).upper(),
        "reviewed_public_post_text": result.get("public_post_text", ""),
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    flag_state = assert_fail_closed_environment()
    presence = {
        "gemini_api_key": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "sheets_credentials": bool((os.environ.get("GCP_SA_JSON_BASE64") or os.environ.get("SA_JSON_BASE64") or "").strip()),
        "sheets_id": bool((os.environ.get("SNS_MASTER_SHEET_ID") or os.environ.get("SPREADSHEET_ID") or "").strip()),
    }

    rows_before = read_queue_rows()
    protected_before = protected_snapshot(rows_before)

    hybrid_client, hybrid_gate, hybrid_gemini, hybrid_reservations = create_readonly_hybrid_runtime()

    text_reports: list[dict[str, Any]] = []
    for account_id, slot_id, post_type in TEXT_SLOTS:
        dry_run = run_json_command([
            sys.executable,
            "scripts/run_autonomous_loop.py",
            "--account-id",
            account_id,
            "--slot-id",
            slot_id,
            "--dry-run",
        ])
        planned_texts = unique(iter_text_values(dry_run.get("payload", {})))[:5]
        hybrid = readonly_hybrid_review(
            hybrid_client,
            hybrid_gate,
            hybrid_gemini,
            hybrid_reservations,
            rows_before,
            account_id,
            slot_id,
        )
        text_reports.append({
            "account_id": account_id,
            "slot_id": slot_id,
            "post_type": post_type,
            "planned_texts": planned_texts,
            "quality_reviews": [assess_text_quality(text, account_id) for text in planned_texts],
            "dry_run": dry_run,
            "hybrid_gate": hybrid,
            "hybrid_gate_summary": hybrid_gate_summary(hybrid),
        })

    media_reports: list[dict[str, Any]] = []
    for account_id, slot_id, post_type in MEDIA_SLOTS:
        hybrid = readonly_hybrid_review(
            hybrid_client,
            hybrid_gate,
            hybrid_gemini,
            hybrid_reservations,
            rows_before,
            account_id,
            slot_id,
        )
        media_reports.append({
            "account_id": account_id,
            "slot_id": slot_id,
            "post_type": post_type,
            "queue": queue_candidates(rows_before, account_id, slot_id, post_type),
            "hybrid_gate": hybrid,
            "hybrid_gate_summary": hybrid_gate_summary(hybrid),
        })

    activation = run_json_command([
        sys.executable,
        "scripts/scheduled_publish_activation_gate.py",
        "--use-sheets",
    ])
    activation_payload = activation.get("payload") if isinstance(activation.get("payload"), dict) else {}

    rows_after = read_queue_rows()
    protected_after = protected_snapshot(rows_after)
    protected_unchanged = all(
        protected_before[queue_id]["fingerprint"] == protected_after[queue_id]["fingerprint"]
        for queue_id in PROTECTED_QUEUE_IDS
    )

    report: dict[str, Any] = {
        "status": "AUDIT_COMPLETE",
        "would_post": False,
        "writes_performed": False,
        "real_action_flags": flag_state,
        "secret_presence": presence,
        "slot_count": len(ALL_SLOTS),
        "text_slots": text_reports,
        "media_slots": media_reports,
        "hybrid_in_memory_reservation_count": len(hybrid_reservations),
        "activation_gate": {
            "returncode": activation.get("returncode"),
            "allowed": activation_payload.get("allowed", False),
            "status": activation_payload.get("status", ""),
            "reasons": activation_reasons(activation_payload),
            "payload": activation_payload,
            "stderr_tail": activation.get("stderr_tail", ""),
            "json_found": activation.get("json_found", False),
        },
        "protected_rows_before": protected_before,
        "protected_rows_after": protected_after,
        "protected_rows_unchanged_during_audit": protected_unchanged,
        "protected_required_values_all_match": all(item["required_values_match"] for item in protected_after.values()),
        "queue_row_count_before": len(rows_before),
        "queue_row_count_after": len(rows_after),
    }

    json_path = Path(args.json_output)
    markdown_path = Path(args.markdown_output)
    rendered = json.dumps(sanitize(report), ensure_ascii=False, indent=2, sort_keys=True)
    json_path.write_text(rendered + "\n", encoding="utf-8")
    markdown_path.write_text(build_markdown(report) + "\n", encoding="utf-8")

    print("=== SCHEDULED_AUTOPOST_AUDIT_REPORT_BEGIN ===")
    print(rendered)
    print("=== SCHEDULED_AUTOPOST_AUDIT_REPORT_END ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
