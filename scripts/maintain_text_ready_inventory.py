#!/usr/bin/env python3
"""Prepare buffered, strictly approved text inventory outside the publish path."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import account_choices  # noqa: E402
from config_loader import get_config  # noqa: E402
from content_schedule import TEXT_POST_TYPES, text_slots  # noqa: E402
from production_inventory import eligible_ready, has_media, scheduled_slots, usable_evergreen_entries  # noqa: E402
from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import (  # noqa: E402
    READONLY_RECORD_CACHE_ATTR,
    enable_readonly_record_cache,
    prime_readonly_record_cache,
    read_records_safely,
)
from production_inventory import policy  # noqa: E402

JST = timezone(timedelta(hours=9))
PREPARED_ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")


def verified_bank_admission(
    client: Any, rows: list[dict[str, Any]], *, now: datetime,
    runtime_check: Any,
) -> dict[str, Any]:
    """Require the canonical batch writer's readback before counting reserves.

    admit_bank_batch already clears temporary dates, appends the reserve
    evidence and rereads BOTH source Sheets. No extra legacy date mutation
    may run afterward: it increases quota exposure and can fail after the
    bank writer has already committed.
    """
    from evergreen_inventory import admit_bank_batch

    if not rows or len(rows) > 30:
        raise ValueError("EVERGREEN_ADMISSION_BATCH_SCOPE_INVALID")
    receipt = admit_bank_batch(
        client, rows, now=now, runtime_check=runtime_check, apply=True,
    )
    if (not isinstance(receipt, dict)
            or receipt.get("status") != "SAVED"
            or receipt.get("read_after_write") != "PASS"
            or receipt.get("would_post") is not False
            or type(receipt.get("count")) is not int
            or receipt["count"] != len(rows)):
        raise RuntimeError("EVERGREEN_ADMISSION_RECEIPT_UNVERIFIED")
    return receipt


def classified_generated_bank_admissions(
    rows: list[dict[str, Any]], queue_ids: Any, account_id: str,
    slot_id: str, runtime_check: Any,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Never admit an unverified generated READY; return fixed reason counts.

    A generator's success is NOT proof of the durable queue or downstream
    approval. Reasons contain only fixed codes, never queue IDs or drafts.
    Ambiguous or partially failed batches are not admitted.
    """
    if (type(queue_ids) is not list or len(queue_ids) > 3
            or any(type(qid) is not str or not 1 <= len(qid) <= 256
                   or any(not 33 <= ord(ch) <= 126 for ch in qid)
                   for qid in queue_ids)
            or len(set(queue_ids)) != len(queue_ids)):
        return [], {"GENERATED_ID_LIST_UNVERIFIABLE": 1}

    candidates: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for qid in queue_ids:
        matches = [row for row in rows if row.get("queue_id") == qid]
        if len(matches) != 1:
            reasons["GENERATED_READBACK_UNVERIFIED"] += 1
            continue
        row = matches[0]
        if (str(row.get("account_id") or "") != account_id
                or str(row.get("slot_id") or "") != slot_id):
            reasons["GENERATED_IDENTITY_MISMATCH"] += 1
        elif str(row.get("status") or "") != "READY":
            reasons["GENERATED_NOT_READY"] += 1
        elif not eligible_ready(row, account_id) or has_media(row):
            reasons["GENERATED_APPROVAL_INCOMPLETE"] += 1
        elif not runtime_check(row):
            reasons["GENERATED_RUNTIME_GATE_REJECTED"] += 1
        else:
            candidates.append(row)
    # A mixed batch is uncertain; no partial bank append is authorized.
    return ([], dict(sorted(reasons.items()))) if reasons else (candidates, {})


def is_explicit_staged_beauty_reserve(
    row: dict[str, Any], *, now: datetime,
    posted_ids: set[str], bank_ids: set[str], used_run_ids: set[str],
) -> bool:
    """Recover only uncommitted, distinctly marked Beauty reserve drafts.

    The reserve generator uses _reserve_1/_reserve_2 IDs; its candidate 0
    has NO reserve marker and may be an intended scheduled primary post.
    Never rewrite a primary, already posted, used, mismatched, or near-due
    queue merely to improve a reserve KPI.
    """
    if (str(row.get("account_id") or "") != "beauty_account"
            or str(row.get("slot_id") or "") != "beauty_1130"
            or row.get("generated_by") != "prepare_beauty_review_candidates.py"
            or row.get("status") != "READY"):
        return False
    queue_id = row.get("queue_id")
    if type(queue_id) is not str:
        return False
    match = re.fullmatch(
        r"q_beauty_(\d{8})_1_chadult_v1_reserve_[12]_[0-9a-f]{8}"
        r"(?:_r_[0-9a-f]{8})?",
        queue_id,
    )
    if not match or queue_id in posted_ids | bank_ids | used_run_ids:
        return False
    business_date = str(row.get("business_date_jst") or "")
    schedule_date = str(row.get("schedule_date_jst") or "")
    try:
        staged_date = datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return False
    # Bound recovery to previous reserve-run dates (T+2 through T+7).
    # Anything imminently due, past-due, or farther out is untouched.
    return (
        2 <= (staged_date - now.date()).days <= 7
        and business_date == staged_date.isoformat()
        and schedule_date in ("", business_date)
    )


def release_temporary_bank_allocations(client: Any, rows: list[dict[str, Any]]) -> None:
    from process_threads_queue import records, update_row

    for row in rows:
        # The approved queue is bound to its original slot_id forever.
        # Clearing only its temporary future dates keeps it out of the live
        # scheduler while preserving the immutable source identity.
        if not str(row.get("slot_id") or "").strip():
            raise RuntimeError("EVERGREEN_TEMPORARY_SLOT_IDENTITY_MISSING")
        if not update_row(client, "queue", "queue_id", row["queue_id"], {
            "business_date_jst": "",
            "schedule_date_jst": "",
        }):
            raise RuntimeError("EVERGREEN_TEMPORARY_ALLOCATION_RELEASE_FAILED")
    released_rows = records(client, "queue")
    for row in rows:
        matches = [item for item in released_rows if item.get("queue_id") == row["queue_id"]]
        if (len(matches) != 1
                or str(matches[0].get("slot_id") or "") != str(row.get("slot_id") or "")
                or matches[0].get("business_date_jst") or matches[0].get("schedule_date_jst")):
            raise RuntimeError("EVERGREEN_ALLOCATION_RELEASE_READ_AFTER_WRITE_FAILED")


def _extract_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    values: list[tuple[int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append((index + end, value))
    return [value for _end, value in sorted(values, key=lambda item: item[0])]


def next_text_slot(account_id: str, *, now: datetime | None = None) -> dict[str, str]:
    return future_text_slots(account_id, now=now, horizon_hours=24)[0]


def future_text_slots(
    account_id: str,
    *,
    now: datetime | None = None,
    horizon_hours: int = 24,
) -> list[dict[str, str]]:
    local = (now or datetime.now(JST)).astimezone(JST)
    choices: list[tuple[datetime, dict[str, str]]] = []
    if not 1 <= horizon_hours <= 168:
        raise ValueError("inventory_horizon_must_be_1_to_168_hours")
    for offset in range(-1, horizon_hours // 24 + 2):
        business_day = local.date() + timedelta(days=offset)
        for slot in text_slots(account_id):
            hour, minute = map(int, str(slot["target_jst"]).split(":"))
            target_day = business_day
            if hour >= 24:
                target_day += timedelta(days=1)
                hour -= 24
            target = datetime.combine(target_day, time(hour, minute), JST)
            if target >= local + timedelta(minutes=30):
                if target <= local + timedelta(hours=horizon_hours):
                    choices.append((target, {**slot, "business_date_jst": business_day.isoformat()}))
    if not choices:
        raise RuntimeError(f"no_future_text_slot:{account_id}")
    return [slot for _target, slot in sorted(choices, key=lambda item: item[0])]


def _ready_exists(rows: list[dict[str, Any]], account_id: str, slot: dict[str, str]) -> bool:
    target_date = str(slot["business_date_jst"])
    return any(
        str(row.get("account_id", "")) == account_id
        and str(row.get("slot_id", "")) == str(slot["slot_id"])
        and str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
        == target_date
        and str(row.get("status", "")).upper() == "READY"
        and str(row.get("validator_status", "")).upper() == "PASS"
        and str(row.get("internal_leak_status", "")).upper() == "PASS"
        and str(row.get("account_fit_status", "")).upper() == "PASS"
        for row in rows
    )



def _persisted_text_route(row: dict[str, Any]) -> str:
    """Use the persisted queue schema, not an unpersisted synthetic post_type.

    SheetsClient.TAB_DEFINITIONS["queue"] persists content_type, while
    publication_review (a different sheet) persists post_type. Legacy
    in-memory unit rows may still specify post_type alone. If both appear
    and disagree, reject the ambiguous row rather than weakening gates.
    """
    persisted = str(row.get("content_type") or "").strip()
    legacy = str(row.get("post_type") or "").strip()
    if persisted and legacy and persisted != legacy:
        return ""
    return persisted or legacy


def _publishable_ready_rows(
    snapshot: Any,
    rows: list[dict[str, Any]],
    account_id: str,
    slot: dict[str, str],
) -> list[dict[str, Any]]:
    """Count only exact-slot text rows that pass the same no-publish runtime check."""
    from process_threads_queue import process_one

    selected = []
    for row in rows:
        if (str(slot.get("post_type") or "") not in TEXT_POST_TYPES
                or _persisted_text_route(row) not in TEXT_POST_TYPES
                or not eligible_ready(row, account_id) or has_media(row)
                or not _ready_exists([row], account_id, slot)):
            continue
        if final_public_post_validator(str(row.get("public_post_text", "")), account_id).get("status") != "PASS":
            continue
        context = build_source_context(snapshot, row) if snapshot is not None else {}
        if not hybrid_ai_gate_passed(row, context)[0]:
            continue
        if snapshot is not None and process_one(
            snapshot, row, dry_run=True, confirm_real_post=False,
        ).get("status") != "DRY_RUN":
            continue
        selected.append(row)
    return selected


def generated_ready_rejection_counts(
    snapshot: Any,
    rows: list[dict[str, Any]],
    account_id: str,
    slot: dict[str, str],
    generated_ids: list[Any],
) -> dict[str, int]:
    """Explain a generated READY that fails the exact no-post publisher gates.

    Report ONLY fixed rejection reason categories and aggregate counts. Never
    reveal queue IDs, captions, unpublished drafts, model prompts or secrets.
    This is optional READ-ONLY diagnostics; it cannot approve or post content.
    """
    from collections import Counter
    from process_threads_queue import process_one

    reasons: Counter[str] = Counter()
    if not generated_ids:
        return {"GENERATION_REPORTED_NO_IDS": 1}
    if len(generated_ids) > 12 or not all(isinstance(v, str) and 0 < len(v) <= 180
                                         for v in generated_ids):
        return {"GENERATED_ID_LIST_UNVERIFIABLE": 1}
    for queue_id in dict.fromkeys(generated_ids):
        matches = [row for row in rows if str(row.get("queue_id") or "") == queue_id]
        if len(matches) != 1:
            reasons["QUEUE_ID_NOT_UNIQUE_OR_NOT_VISIBLE"] += 1
            continue
        row = matches[0]
        if str(row.get("account_id") or "") != account_id:
            reason = "ACCOUNT_ID_MISMATCH"
        elif str(row.get("slot_id") or "") != str(slot.get("slot_id") or "") or (
            str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
            != str(slot.get("business_date_jst") or "")
        ):
            reason = "EXACT_SLOT_OR_DATE_MISMATCH"
        elif str(row.get("status") or "").upper() != "READY":
            reason = "STATUS_NOT_READY"
        elif not _ready_exists([row], account_id, slot):
            reason = "READY_APPROVAL_FLAGS_INCOMPLETE"
        elif str(slot.get("post_type") or "") not in TEXT_POST_TYPES or (
            _persisted_text_route(row) not in TEXT_POST_TYPES
        ):
            reason = "NON_TEXT_POST_TYPE"
        else:
            try:
                if not eligible_ready(row, account_id) or has_media(row):
                    reason = "RUNTIME_ELIGIBILITY_OR_MEDIA_GATE"
                elif final_public_post_validator(
                    str(row.get("public_post_text") or ""), account_id
                ).get("status") != "PASS":
                    reason = "FINAL_PUBLIC_TEXT_VALIDATOR"
                elif not hybrid_ai_gate_passed(
                    row, build_source_context(snapshot, row) if snapshot is not None else {}
                )[0]:
                    reason = "HYBRID_AI_SOURCE_GATE"
                elif snapshot is None or process_one(
                    snapshot, row, dry_run=True, confirm_real_post=False
                ).get("status") != "DRY_RUN":
                    reason = "RUNTIME_DRY_RUN_GATE"
                else:
                    reason = "PUBLISHABILITY_AUDIT_INCONSISTENT"
            except Exception:
                # Diagnostics may not leak exception text from private content
                # or backend payloads. Keep the original SLO failure decisive.
                reason = "RUNTIME_DIAGNOSTIC_UNAVAILABLE"
        reasons[reason] += 1
    return dict(sorted(reasons.items()))


def _reserve_status(delivery_count: int, reserve_target: int) -> str:
    if delivery_count < 1:
        return "DELIVERY_SLO_FAILED"
    if delivery_count < reserve_target:
        return "RESERVE_DEGRADED"
    return "DELIVERY_READY"


def delivery_generation_required(publishable_ready: int) -> int:
    """Recover the delivery SLO before spending effort on reserve inventory."""
    return 1 if publishable_ready < 1 else 0


def reserve_generation_required(publishable_ready: int, reserve_target: int) -> int:
    """Return only the best-effort shortfall after one deliverable is secured."""
    if publishable_ready < 1:
        return 0
    return max(0, reserve_target - publishable_ready)


# A provider outage/limit on one slot should not trigger another paid
# generation on the next slot for the same account and inventory run.
# It does NOT waive the existing review or publisher validation gates.
PAID_GENERATION_PAUSE_REASONS = frozenset({
    "AI_APPROVAL_BUDGET_EXHAUSTED",
    "GENERATION_PROCESS_TIMEOUT",
    "PROVIDER_TIMEOUT",
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_CONFIGURATION_ERROR",
    "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED",
})


def paid_generation_pause_required(result: dict[str, Any]) -> bool:
    """Pure, sanitized account-scope circuit breaker for paid generation."""
    if not isinstance(result, dict):
        return False
    reasons = {str(result.get("failure_category") or "")}
    attempts = result.get("attempts", [])
    if isinstance(attempts, list):
        reasons.update(
            str(item.get("reason") or item.get("failure_category") or "")
            for item in attempts if isinstance(item, dict)
        )
    return bool(reasons & PAID_GENERATION_PAUSE_REASONS)


def hard_replenishment_blocker(result: dict[str, Any]) -> bool:
    """Only stop bounded evergreen attempts for known operational hard blocks."""
    hard_categories = {
        "AI_APPROVAL_BUDGET_EXHAUSTED",
        "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED",
        "SHEETS_QUOTA_EXHAUSTED",
        "KILL_SWITCH_ACTIVE",
        "PERMISSION_OR_SAFETY_FAILURE",
        "OWNER_REVIEW_REQUIRED",
    }
    if str(result.get("failure_category", "")) in hard_categories:
        return True
    attempts = result.get("attempts", [])
    return any(
        isinstance(attempt, dict)
        and str(attempt.get("reason") or attempt.get("failure_category") or "") in hard_categories
        for attempt in attempts
    )


def _coverage_result(required: int, covered: int) -> tuple[str, float, str]:
    if required <= 0:
        return "FAILED", 0.0, "NO_REQUIRED_TEXT_SLOTS"
    coverage = round(100 * covered / required, 2)
    return ("PASS" if covered == required else "FAILED"), coverage, ""


def _required_text_slots(account_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Use each scheduled slot's resolved route, not its static/base route."""
    return [slot for slot in scheduled_slots(account_id, start, end)
            if str(slot.get("post_type") or "") in TEXT_POST_TYPES]


def approval_budget_exhausted(payload: dict[str, Any]) -> bool:
    """Untrusted generator stages cannot crash the paid-budget gate."""
    reasons = {"HYBRID_AI_EXECUTION_LIMIT_EXCEEDED", "HYBRID_AI_DAILY_LIMIT_EXCEEDED",
               "HYBRID_AI_MONTHLY_LIMIT_EXCEEDED"}
    if not isinstance(payload, dict):
        return False
    stages = payload.get("stages")
    stages = stages if isinstance(stages, list) else []
    packets = [payload, *(
        stage["payload"] for stage in stages
        if isinstance(stage, dict) and isinstance(stage.get("payload"), dict)
    )]
    for packet in packets:
        errors = packet.get("runtime_errors")
        if isinstance(errors, list) and any(
            isinstance(error, dict) and error.get("reason") in reasons
            for error in errors
        ):
            return True
    return False


def _validated_generation_queue_ids(payload: dict[str, Any], account_id: str) -> tuple[list[str], bool]:
    """A malformed provider envelope never becomes a queue approval target."""
    raw = payload.get("effective_queue_ids", payload.get("queue_ids", []))
    if not isinstance(raw, list) or len(raw) > 30:
        return [], False
    if any(type(qid) is not str or not 1 <= len(qid) <= 256
           or any(not 33 <= ord(c) <= 126 for c in qid) for qid in raw):
        return [], False
    if len(set(raw)) != len(raw):
        return [], False
    if account_id == "beauty_account" and "apply_result" in payload:
        result = payload["apply_result"]
        if not isinstance(result, dict):
            return [], False
        if result.get("read_after_write") is True or result.get("read_after_write") == "PASS":
            qid = result.get("queue_id")
            if (type(qid) is not str or not 1 <= len(qid) <= 256
                    or any(not 33 <= ord(c) <= 126 for c in qid)):
                return [], False
            return [qid], True
        # In particular "FAILED" is a non-empty string but NOT verified.
        # No other effective IDs can bypass a failed Beauty readback.
        return [], False
    return raw, True


def generation_failure_category(payload: dict[str, Any]) -> str:
    """Read structured generator failures without emitting provider responses."""
    candidate = payload.get("candidate")
    outcome = candidate if isinstance(candidate, dict) else payload
    reasons = outcome.get("blocked_reasons", [])
    reasons = reasons if isinstance(reasons, list) else []
    codes = {str(value) for value in reasons}
    codes.add(str(outcome.get("reason") or ""))
    categories = (
        ({"content_quality_v2_owner_review_required"}, "OWNER_REVIEW_REQUIRED"),
        ({"gemini_auth_rejected", "GEMINI_API_KEY_MISSING"}, "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED"),
        ({"gemini_rate_limited"}, "PROVIDER_RATE_LIMITED"),
        ({"gemini_connection_error", "gemini_retryable_server_error"}, "PROVIDER_UNAVAILABLE"),
        ({"gemini_model_not_found", "gemini_request_rejected"}, "PROVIDER_CONFIGURATION_ERROR"),
        ({"beauty_reference_source_post_missing", "beauty_reference_topic_match_missing"}, "REFERENCE_CONTEXT_UNAVAILABLE"),
        ({"duplicate_or_near_duplicate"}, "DUPLICATE_GENERATION_EXHAUSTED"),
    )
    for matches, category in categories:
        if codes & matches:
            return category
    if any(code.startswith("beauty_route_context_unavailable:") for code in codes):
        return "SOURCE_CONTEXT_READ_FAILED"
    return "QUALITY_EXHAUSTED" if outcome.get("status") == "QUALITY_EXHAUSTED" else "GENERATION_PROCESS_FAILED"


def _run(command: list[str]) -> tuple[int, dict[str, Any]]:
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=480,
            env={**os.environ, "BUFFERED_PREPARATION": "true", "PUBLISH_ENABLED": "false", "ALLOW_REAL_THREADS_POST": "false"})
    except subprocess.TimeoutExpired:
        return 124, {"status": "FAILED", "failure_category": "GENERATION_PROCESS_TIMEOUT"}
    payloads = _extract_objects(completed.stdout)
    payload = payloads[-1] if payloads else {}
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        payload.setdefault("status", candidate.get("status", ""))
    # Preserve a safe error category, never the provider response or credentials.
    error = completed.stderr
    # Repeating generation/fallback on an exhausted Sheets read quota amplifies
    # the incident and cannot produce a verifiable READY row. Do not log body.
    sheets_rate_limited = "[SHEETS_RETRY]" in error and any(
        marker in error.lower() for marker in ("rate_limit", "quota", "429", "resource_exhausted")
    )
    if sheets_rate_limited:
        payload["failure_category"] = "SHEETS_QUOTA_EXHAUSTED"
    elif "hybrid_ai_budget_blocked:" in error or approval_budget_exhausted(payload):
        payload["failure_category"] = "AI_APPROVAL_BUDGET_EXHAUSTED"
    elif "RESOURCE_EXHAUSTED" in error or "HTTP 429" in error:
        payload["failure_category"] = "PROVIDER_RATE_LIMITED"
    elif "Timeout" in error or "timed out" in error:
        payload["failure_category"] = "PROVIDER_TIMEOUT"
    elif completed.returncode:
        payload.setdefault("failure_category", generation_failure_category(payload))
    return completed.returncode, payload


def _run_isolated_ready_review(command: list[str]) -> tuple[int, dict[str, Any]]:
    """Accept only a fresh, identity-matched and no-post hybrid READY receipt.

    Concurrent AUTO_READY and Aftercare must not share a predictable /tmp
    result or trust a subprocess's stdout when its durable receipt is missing.
    """
    def argument(flag: str) -> str:
        try:
            value = command[command.index(flag) + 1]
        except (ValueError, IndexError):
            return ""
        return value if type(value) is str else ""

    expected = (
        argument("--account-id"), argument("--slot-id"), argument("--queue-id"),
    )
    if not all(expected) or "--json-output" in command:
        return 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
    with tempfile.TemporaryDirectory(prefix="sns-ready-review-") as directory:
        receipt = Path(directory) / "review.json"
        rc, review = _run([*command, "--json-output", str(receipt)])
        failure = str(review.get("failure_category", ""))
        # A successful stdout alone is not a persisted approval decision.
        if not receipt.exists():
            if rc:
                return rc, review
            return 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
        try:
            if (receipt.is_symlink() or not receipt.is_file()
                    or receipt.stat().st_size > 5_000_000):
                raise ValueError("untrusted_review_receipt")
            parsed = json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("nonobject_review")
        except (OSError, UnicodeError, ValueError, TypeError):
            return rc or 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
        if (parsed.get("account_id"), parsed.get("slot_id")) != expected[:2]:
            return rc or 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
        if (parsed.get("status") == "READY"
                and (parsed.get("selected_queue_id") != expected[2]
                     or parsed.get("would_post") is not False)):
            return rc or 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
        if parsed.get("status") not in {"READY", "NO_READY_CANDIDATE", "FAILED"}:
            return rc or 2, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"}
        if failure == "SHEETS_QUOTA_EXHAUSTED":
            parsed["failure_category"] = failure
        if rc and parsed.get("status") == "READY":
            parsed["status"] = "FAILED"
            parsed["failure_category"] = failure or "READY_REVIEW_REPORT_INVALID"
        return rc, parsed


def _primary_generation_commands(account_id: str, slot: dict[str, str]) -> list[tuple[str, list[str]]]:
    if account_id == "beauty_account":
        from content_schedule import slots_for_account
        index = next(i for i, row in enumerate(slots_for_account(account_id)) if row["slot_id"] == slot["slot_id"])
        return [(f"beauty_reserve_{candidate}", [sys.executable, "scripts/prepare_beauty_review_candidates.py",
            "--slot-index", str(index), "--schedule-date-jst", str(slot["business_date_jst"]),
            "--candidate-index", str(candidate), "--apply", "--confirm-prepare"]) for candidate in range(3)]
    base = [
        sys.executable,
        "scripts/generate_threads_ideas_from_references.py",
        "--account-id",
        account_id,
        "--apply",
        "--confirm-generate",
        "--autonomous-text-generation",
        "--top-n",
        "3",
        "--slot-id",
        str(slot["slot_id"]),
        "--post-type",
        str(slot["post_type"]),
        "--theme",
        str(slot.get("theme", "")),
        "--schedule-date-jst",
        str(slot["business_date_jst"]),
    ]
    original_fallback = [
        *base[: base.index("--post-type") + 1],
        "original_text",
        *base[base.index("--post-type") + 2 :],
    ]
    if slot["post_type"] == "pdca_text":
        return [
            ("measured_pdca", [*base, "--require-measured-pdca"]),
            ("safe_original_fallback", original_fallback),
        ]
    if slot["post_type"] == "reference_text":
        return [
            ("primary", base),
            ("safe_original_fallback", original_fallback),
        ]
    return [("primary", base)]


def _generation_commands(account_id: str, slot: dict[str, str], *, offline_only: bool = False) -> list[tuple[str, list[str]]]:
    offline = ("offline_original_bank", [sys.executable, "scripts/generate_threads_ideas_from_references.py",
        "--account-id", account_id, "--apply", "--confirm-generate",
        "--autonomous-text-generation", "--top-n", "3",
        "--slot-id", str(slot["slot_id"]), "--post-type", "original_text",
        "--schedule-date-jst", str(slot["business_date_jst"]), "--offline-original"])
    if slot.get("theme"):
        offline[1].extend(["--theme", str(slot["theme"])])
    return [offline] if offline_only else [*_primary_generation_commands(account_id, slot), offline]


def evergreen_theme_variants(account_id: str) -> list[str]:
    """Build bounded, persona-scoped generation angles from the canonical account taxonomy."""
    account_path = ROOT / "config" / "accounts" / f"{account_id}.json"
    try:
        config = json.loads(account_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    categories = [str(value).strip() for value in config.get("content_categories", []) if str(value).strip()]
    framings = ("見落としやすい判断材料", "最初に試せる小さな工夫", "続ける前に確認したいこと")
    return [f"{category} / {framing}" for category in categories for framing in framings]


def replenish(account_id: str, slot: dict[str, str], *, apply: bool,
              required: int = 1, offline_only: bool = False) -> dict[str, Any]:
    if not 1 <= required <= 3:
        raise ValueError("inventory_required_must_be_1_to_3")
    result: dict[str, Any] = {
        "account_id": account_id,
        "slot_id": slot["slot_id"],
        "business_date_jst": slot["business_date_jst"],
        "post_type": slot["post_type"],
        "would_post": False,
    }
    if not apply:
        return {**result, "status": "PLAN_ONLY"}
    attempts: list[dict[str, str]] = []
    approved: list[str] = []
    last_payload: dict[str, Any] = {}
    budget_blocked = False
    sheets_quota_blocked = False
    owner_review_blocked = False
    # Repeated paid generation cannot recover the same provider budget/rate
    # failure or a timed-out generation. Keep one existing deterministic
    # offline route, with exactly the same downstream approval gates.
    paid_provider_blocker = ""
    paid_stop_categories = {
        "GENERATION_PROCESS_TIMEOUT", "PROVIDER_TIMEOUT",
        "PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE",
        "PROVIDER_CONFIGURATION_ERROR",
        "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED",
        "GENERATION_OUTPUT_INVALID",
    }
    for generation_route, generation in _generation_commands(account_id, slot, offline_only=offline_only):
        if (budget_blocked or paid_provider_blocker) and generation_route != "offline_original_bank":
            continue
        rc, payload = _run(generation)
        last_payload = payload
        queue_ids, envelope_valid = _validated_generation_queue_ids(payload, account_id)
        if not envelope_valid:
            # Do not treat null, scalar, duplicate, or unverified readback
            # IDs as target queue records, even if the provider exits 0.
            payload["failure_category"] = "GENERATION_OUTPUT_INVALID"
            rc = rc or 1
        attempts.append({
            "route": generation_route,
            "status": str(payload.get("status", "")),
            "reason": str(payload.get("failure_category") or payload.get("reason") or ""),
        })
        if rc != 0:
            failure_category = str(payload.get("failure_category") or "")
            if failure_category == "OWNER_REVIEW_REQUIRED":
                owner_review_blocked = True
                break
            if failure_category == "SHEETS_QUOTA_EXHAUSTED":
                sheets_quota_blocked = True
                break
            if (failure_category == "AI_APPROVAL_BUDGET_EXHAUSTED"
                    or approval_budget_exhausted(payload)):
                budget_blocked = True
                paid_provider_blocker = "AI_APPROVAL_BUDGET_EXHAUSTED"
            elif failure_category in paid_stop_categories:
                paid_provider_blocker = paid_provider_blocker or failure_category
            continue
        for queue_id in queue_ids[:3]:
            if queue_id in approved:
                continue
            command = [
                sys.executable,
                "scripts/run_hybrid_ready_pipeline.py",
                "--account-id",
                account_id,
                "--slot-id",
                str(slot["slot_id"]),
                "--queue-id",
                queue_id,
                "--max-candidates",
                "1",
                "--approval-mode",
                "text",
                "--autonomous-low-risk",
                "--apply",
                "--use-sheets",
            ]
            review_rc, review = _run_isolated_ready_review(command)
            budget_blocked = approval_budget_exhausted(review)
            if budget_blocked:
                review["failure_category"] = "AI_APPROVAL_BUDGET_EXHAUSTED"
            attempts.append({
                "route": generation_route,
                "queue_id": queue_id,
                "status": str(review.get("status", "")),
                "reason": str(review.get("failure_category") or review.get("reason") or ""),
            })
            if str(review.get("failure_category", "")) == "SHEETS_QUOTA_EXHAUSTED":
                sheets_quota_blocked = True
                break
            if budget_blocked:
                break
            if review_rc == 0 and review.get("status") == "READY":
                approved.append(queue_id)
                if len(approved) >= required:
                    return {
                        **result,
                        "status": "READY_REPLENISHED",
                        "queue_id": approved[0],
                        "queue_ids": approved,
                        "generation_route": generation_route,
                        "attempts": attempts,
                    }
        if sheets_quota_blocked:
            break
    return {
        **result,
        "status": "OWNER_REVIEW_REQUIRED" if owner_review_blocked else "QUALITY_EXHAUSTED",
        "queue_ids": approved,
        "missing": required - len(approved),
        "generation_status": str(last_payload.get("status", "")),
        "failure_category": ("OWNER_REVIEW_REQUIRED" if owner_review_blocked else
                             "SHEETS_QUOTA_EXHAUSTED" if sheets_quota_blocked else
                             ("AI_APPROVAL_BUDGET_EXHAUSTED" if budget_blocked else
                              paid_provider_blocker or
                              str(last_payload.get("failure_category") or "QUALITY_EXHAUSTED"))),
        "attempts": attempts,
    }


def evergreen_active_text_slots(account_id: str) -> list[dict[str, Any]]:
    """Respect route cycles: an exclusively-media slot needs no text bank."""
    cycles = policy().get("slot_route_cycles", {}).get(account_id, {})
    result = []
    for slot in text_slots(account_id):
        sid = str(slot["slot_id"])
        overrides = cycles.get(sid)
        if slot["post_type"] not in TEXT_POST_TYPES:
            continue
        if overrides and not any(route in TEXT_POST_TYPES for route in overrides):
            continue
        result.append(slot)
    return result


def evergreen_canonical_slot_health(
    usable: list[dict[str, Any]], account_id: str, minimum: int,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Count only reserves usable by each currently active text route."""
    canonical = [
        str(slot["slot_id"]) for slot in evergreen_active_text_slots(account_id)
    ]
    if (not canonical or len(canonical) > 16 or len(set(canonical)) != len(canonical)
            or minimum < len(canonical) or minimum > 10000):
        raise ValueError("CANONICAL_EVERGREEN_SLOT_POLICY_INVALID")
    targets = {
        slot_id: minimum // len(canonical) + (i < minimum % len(canonical))
        for i, slot_id in enumerate(canonical)
    }
    by_slot = {slot_id: 0 for slot_id in canonical}
    for entry in usable:
        queue = entry.get("canonical_queue", {})
        if not isinstance(queue, dict):
            continue
        slot_id = str(queue.get("slot_id") or "")
        if slot_id in by_slot:
            by_slot[slot_id] += 1
    effective = sum(min(by_slot[key], targets[key]) for key in canonical)
    deficits = {key: max(0, targets[key] - by_slot[key]) for key in canonical}
    return effective, deficits, by_slot


def replenish_bank(client, account_id: str, *, apply: bool,
                   reuse_only: bool = False) -> dict[str, Any]:
    from evergreen_inventory import (
        expired_unpublished_bank_allocations,
        release_expired_unpublished_bank_allocations,
    )
    from process_threads_queue import process_one, records
    from sheets_client import TAB_DEFINITIONS
    from generate_threads_ideas_from_references import original_text_similarity_guard

    now = datetime.now(JST)
    minimum = policy()["minimum_evergreen_per_account"]
    if not apply:
        return {"status": "PLAN_ONLY", "account_id": account_id, "minimum": minimum, "would_post": False}
    client._ensure_tab("evergreen_bank", TAB_DEFINITIONS["evergreen_bank"])
    snapshot = copy.copy(client)
    enable_readonly_record_cache(snapshot)
    # A production bank invocation previously fetched these four large
    # tabs with separate Sheets values calls. The existing read-only batch
    # API captures them together, reducing 429/quota exposure without
    # weakening any canonical identity or runtime-publishability gate.
    # Keep synthetic/mock clients on their existing record adapter.
    if isinstance(client, SheetsClient):
        prime_readonly_record_cache(
            snapshot, ("queue", "evergreen_bank", "posted_results", "content_slot_runs")
        )
    initial_queues = records(snapshot, "queue")
    initial_bank = records(snapshot, "evergreen_bank")
    initial_posts = records(snapshot, "posted_results")
    initial_slot_runs = records(snapshot, "content_slot_runs")
    def check(row):
        return (final_public_post_validator(str(row.get("public_post_text", "")), account_id).get("status") == "PASS"
                and hybrid_ai_gate_passed(row, build_source_context(snapshot, row))[0]
                and process_one(snapshot, row, dry_run=True, confirm_real_post=False).get("status") == "DRY_RUN")

    canonical_slots = evergreen_active_text_slots(account_id)
    canonical_ids = {str(slot["slot_id"]) for slot in canonical_slots}

    def current_bank_health() -> tuple[int, dict[str, int], dict[str, int]]:
        bank = records(snapshot, "evergreen_bank")
        queues = records(snapshot, "queue")
        posted = records(snapshot, "posted_results")
        unallocated = [
            row for row in queues
            if str(row.get("account_id") or "") == account_id
            and str(row.get("slot_id") or "") in canonical_ids
            and not (row.get("business_date_jst") or row.get("schedule_date_jst"))
        ]
        exact_ids = {str(row.get("queue_id") or "") for row in unallocated}
        matching_bank = [
            item for item in bank
            if str(item.get("account_id") or "") == account_id
            and str(item.get("queue_id") or "") in exact_ids
        ]
        eligible = usable_evergreen_entries(
            matching_bank, unallocated, posted, account=account_id, now=now,
            runtime_check=check,
            similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED",
        )
        return evergreen_canonical_slot_health(eligible, account_id, minimum)

    def sufficient_result(usable: int, release: Any) -> dict[str, Any]:
        return {
            "status": "READY_INVENTORY_OK", "account_id": account_id,
            "usable_evergreen": usable, "minimum": minimum,
            "expired_allocation_release": release,
            "attempts": [], "would_post": False,
        }


    # The READY supply is already sufficient: short-circuit BEFORE any write,
    # expiry-release mutation, broad historical candidate scan or paid AI call.
    # This is critical for per-2-hour scheduled jobs and Sheets write quota.
    current, deficits, by_slot = current_bank_health()
    if current >= minimum:
        return sufficient_result(current, {"status": "SKIPPED_HEALTHY_BANK"})

    from content_slot_runs import business_date
    releases = expired_unpublished_bank_allocations(
        initial_bank, initial_queues, initial_posts, initial_slot_runs,
        current_business_date=business_date(now),
    )
    release_result = release_expired_unpublished_bank_allocations(client, releases, apply=apply)
    if releases:
        prime_readonly_record_cache(snapshot, ("queue", "evergreen_bank"))
        current, deficits, by_slot = current_bank_health()
        if current >= minimum:
            return sufficient_result(current, release_result)

    posted_ids = {str(r.get("queue_id") or "") for r in records(snapshot, "posted_results")}
    existing_bank_ids = {str(r.get("queue_id") or "") for r in records(snapshot, "evergreen_bank")}
    used_slot_run_ids = {
        str(r.get(key) or "") for r in initial_slot_runs
        for key in ("queue_id", "ready_queue_id", "selected_queue_id", "candidate_queue_id")
    }
    canonical_queues = records(snapshot, "queue")
    queue_id_counts = Counter(str(row.get("queue_id") or "") for row in canonical_queues)
    admissions = []
    for row in canonical_queues:
        date = str(row.get("business_date_jst") or row.get("schedule_date_jst") or "")
        sid = str(row.get("slot_id") or "")
        queue_id = str(row.get("queue_id") or "")
        if (not queue_id or queue_id_counts[queue_id] != 1
                or row.get("queue_id") in posted_ids or row.get("queue_id") in existing_bank_ids
                or row.get("generation_mode") not in {"original_text", "beauty_new_text_generation", "new_text_generation"}
                or not eligible_ready(row, account_id) or has_media(row)
                or deficits.get(sid, 0) <= sum(
                    str(saved.get("slot_id") or "") == sid for saved in admissions
                )
                or (bool(date) and not is_explicit_staged_beauty_reserve(
                    row, now=now,
                    posted_ids=posted_ids,
                    bank_ids=existing_bank_ids,
                    used_run_ids=used_slot_run_ids,
                ))
                or not check(row)):
            continue
        admissions.append(row)
        if len(admissions) >= max(0, minimum - current):
            break
    if admissions:
        verified_bank_admission(client, admissions, now=now, runtime_check=check)
        prime_readonly_record_cache(snapshot, ("queue", "evergreen_bank"))

    current, deficits, by_slot = current_bank_health()
    if reuse_only:
        # Explicitly approved low-cost bank recovery. Even with a remaining
        # shortfall, do not call the paid/AI generator or claim a false PASS.
        return {
            "status": "READY_INVENTORY_OK" if current >= minimum else "QUALITY_EXHAUSTED",
            "account_id": account_id, "usable_evergreen": current,
            "minimum": minimum, "reuse_only": True,
            "failure_category": "" if current >= minimum else "NO_VALIDATED_BANK_CANDIDATE",
            "expired_allocation_release": release_result,
            "attempts": [], "would_post": False,
        }
    attempts: list[dict[str, Any]] = []
    # New bank candidates must be generated for an actual immutable slot_id,
    # not an account-wide generic reserve identity.
    future_date = (now.date() + timedelta(days=7)).isoformat()
    theme_variants = evergreen_theme_variants(account_id)
    # Quality rejection may still try the existing bounded ten distinct themes.
    # Prefer slots attempted least so a single hard-to-satisfy route cannot
    # monopolize the refill budget. Provider/paid-budget blockers still stop.
    attempts_by_slot: dict[str, int] = {}
    for attempt_number in range(10):
        if current >= minimum:
            break
        possible = [
            slot for slot in canonical_slots
            if deficits.get(str(slot["slot_id"]), 0) > 0
        ]
        if not possible:
            break
        selected = min(
            possible,
            key=lambda item: (
                attempts_by_slot.get(str(item["slot_id"]), 0),
                by_slot.get(str(item["slot_id"]), 0),
                -deficits[str(item["slot_id"])],
                canonical_slots.index(item),
            ),
        )
        sid = str(selected["slot_id"])
        attempts_by_slot[sid] = attempts_by_slot.get(sid, 0) + 1
        # The original-text fallback is approved for reference and PDCA
        # delivery, but the immutable slot identity must remain canonical.
        target = {
            **selected,
            "post_type": "original_text",
            "business_date_jst": future_date,
        }
        if theme_variants:
            target["theme"] = theme_variants[attempt_number % len(theme_variants)]
        result = replenish(
            account_id, target, apply=True,
            required=min(3, deficits[sid]), offline_only=False,
        )
        attempts.append({
            "status": result["status"], "slot_id": sid,
            "queue_ids": result.get("queue_ids", []),
            "failure_category": result.get("failure_category", ""),
            "generation_attempts": result.get("attempts", []),
        })
        generated_ids = result.get("queue_ids", [])
        if not generated_ids and result.get("status") == "READY_REPLENISHED":
            attempts[-1]["status"] = "READBACK_REJECTED"
            attempts[-1]["failure_category"] = "GENERATED_READBACK_UNVERIFIED"
            attempts[-1]["verification_rejection_counts"] = {
                "GENERATION_REPORTED_NO_IDS": 1,
            }
            break
        if generated_ids:
            prime_readonly_record_cache(snapshot, ("queue", "evergreen_bank"))
        generated_rows = records(snapshot, "queue") if generated_ids else []
        admissions, rejected = classified_generated_bank_admissions(
            generated_rows, generated_ids, account_id, sid, check,
        )
        if rejected:
            # A subprocess may have created a draft without making it
            # publishable or even visible. Count no reserve and never
            # approve a partially verified batch. Do not repeat a paid
            # provider request when a durable readback or human approval
            # is uncertain. Pure editorial rejection may use the existing
            # at-most-ten-theme quality retry budget.
            attempt = attempts[-1]
            attempt["verification_rejection_counts"] = rejected
            attempt["status"] = "READBACK_REJECTED"
            attempt["failure_category"] = (
                "GENERATED_RUNTIME_GATE_REJECTED"
                if set(rejected) == {"GENERATED_RUNTIME_GATE_REJECTED"}
                else "GENERATED_READBACK_UNVERIFIED"
            )
            if attempt["failure_category"] != "GENERATED_RUNTIME_GATE_REJECTED":
                break
            continue
        if admissions:
            # One canonical batch transaction already releases temporary
            # dates and verifies queue + reserve readback. Never rewrite
            # the same dates again with the legacy per-row mutation.
            verified_bank_admission(client, admissions, now=now, runtime_check=check)
            prime_readonly_record_cache(snapshot, ("queue", "evergreen_bank"))
        updated, deficits, by_slot = current_bank_health()
        current = updated
        # A provider failure/rate-limit must not trigger more paid attempts.
        # Editorial QUALITY_EXHAUSTED alone can try a different bounded theme.
        if hard_replenishment_blocker(result) or paid_generation_pause_required(result):
            break
    return {"status": "READY_INVENTORY_OK" if current >= minimum else "QUALITY_EXHAUSTED",
            "account_id": account_id, "usable_evergreen": current, "minimum": minimum,
            "expired_allocation_release": release_result,
            "attempts": attempts, "would_post": False}


def evergreen_bank_mode_result(
    results: list[dict[str, Any]], accounts: list[str], *, apply: bool,
) -> dict[str, Any]:
    """Bank-only status is determined by the bank, never empty text slots.

    The ordinary delivery-only path deliberately continues to fail when it
    has no scheduled text slots; don't apply that rule to evergreen reserves.
    A failed or incomplete bank top-up remains a hard operational failure.
    """
    accepted = "READY_INVENTORY_OK" if apply else "PLAN_ONLY"
    expected = set(accounts)
    observed = [
        str(item.get("account_id") or "")
        for item in results if isinstance(item, dict)
    ]
    complete = (
        len(results) == len(accounts)
        and len(set(observed)) == len(observed)
        and set(observed) == expected
        and all(isinstance(item, dict) and item.get("status") == accepted
                for item in results)
        and (not apply or all(
            type(item.get("usable_evergreen")) is int
            and type(item.get("minimum")) is int
            and item["minimum"] > 0
            and item["usable_evergreen"] >= item["minimum"]
            for item in results
        ))
    )
    status = accepted if complete else "FAILED"
    return {
        "status": "PASS" if status == "READY_INVENTORY_OK" else status,
        "mode": "EVERGREEN_BANK",
        "evergreen_bank_by_account": {
            account: next(
                ({"status": row.get("status", "UNKNOWN"),
                  "usable_evergreen": row.get("usable_evergreen"),
                  "minimum": row.get("minimum")}
                 for row in results if isinstance(row, dict)
                 and row.get("account_id") == account),
                {"status": "MISSING"},
            )
            for account in accounts
        },
        "bank_failure_reason": "" if complete else "EVERGREEN_BANK_NOT_READY",
        "results": results,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-ready-maintenance", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--horizon-hours", type=int, default=policy()["text_horizon_hours"])
    parser.add_argument("--evergreen-bank", action="store_true")
    parser.add_argument(
        "--bank-reuse-only", action="store_true",
        help="Confirmed evergreen-bank Apply using existing approved candidates only; no AI generation",
    )
    parser.add_argument(
        "--reuse-only", action="store_true",
        help="Approved bank allocations only; never create content or call paid AI",
    )
    parser.add_argument(
        "--max-bank-allocations", type=int, default=2,
        help="Maximum validated bank allocations per account per run (0 to 6)",
    )
    args = parser.parse_args()
    if args.apply and (not args.confirm_ready_maintenance or not args.use_sheets):
        print(json.dumps({"status": "BLOCKED", "reason": "apply requires confirmation and --use-sheets"}))
        return 1
    if args.apply == args.dry_run:
        print(json.dumps({"status": "BLOCKED", "reason": "choose exactly one of --dry-run or --apply"}))
        return 1
    if args.apply and args.account_id == "all":
        print(json.dumps({"status": "BLOCKED", "reason": "apply_requires_one_account", "would_post": False}))
        return 1
    if not 0 <= args.max_bank_allocations <= 6:
        print(json.dumps({"status": "BLOCKED", "reason": "max_bank_allocations_must_be_0_to_6", "would_post": False}))
        return 1
    if args.reuse_only and (not args.apply or not args.use_sheets or args.evergreen_bank):
        print(json.dumps({"status": "BLOCKED", "reason": "reuse_only_requires_single_account_apply_without_evergreen_bank", "would_post": False}))
        return 1
    if args.bank_reuse_only and not (
        args.apply and args.use_sheets and args.evergreen_bank
        and args.account_id in PREPARED_ACCOUNTS and not args.reuse_only
    ):
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "bank_reuse_only_requires_single_account_confirmed_bank_apply",
            "would_post": False,
        }))
        return 1
    if not 1 <= args.horizon_hours <= 168:
        print(json.dumps({"status": "BLOCKED", "reason": "inventory_horizon_must_be_1_to_168_hours", "would_post": False}))
        return 1
    requested = PREPARED_ACCOUNTS if args.account_id == "all" else (args.account_id,)
    accounts = [account for account in requested if account in PREPARED_ACCOUNTS]
    # A bounded manual no-post probe can legitimately have NO text slot in
    # its next few hours. Return an explicit non-coverage SKIP before even
    # constructing the Sheets writer. Do NOT weaken 24h+ monitoring (which
    # must still fail closed if a complete daily slot plan is missing).
    # Evergreen-bank mode is independent of due scheduled slots.
    if (not args.evergreen_bank and args.account_id != "all"
            and 1 <= args.horizon_hours < 24):
        now = datetime.now(JST)
        if not _required_text_slots(args.account_id, now, now + timedelta(hours=args.horizon_hours)):
            print(json.dumps({
                "status": "SKIPPED_NO_DUE_TEXT_SLOTS",
                "horizon_hours": args.horizon_hours,
                "text_delivery_coverage_72h_percent": None,
                "text_delivery_coverage_by_account": {
                    args.account_id: {"covered_slots": 0, "required_slots": 0}
                },
                "coverage_failure_reason": "NO_REQUIRED_TEXT_SLOTS",
                "reserve_status": "NOT_APPLICABLE",
                "hard_delivery_failures": [],
                "results": [],
                "would_post": False,
            }, ensure_ascii=False, indent=2))
            return 0
    queue_rows: list[dict[str, Any]] = []
    client = None
    # Bank-only apply owns its own schema and canonical queue snapshot inside
    # replenish_bank. An unconditional main() read used to load queue twice
    # and recheck bank headers twice before any work, worsening Sheets 429s.
    # Bank-only planning does not need credentials or external reads at all.
    if args.use_sheets and (not args.evergreen_bank or args.apply):
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
        if not args.evergreen_bank:
            queue_rows = [dict(row) for row in read_records_safely(client, "queue")]
            if args.apply:
                if args.reuse_only:
                    # Approval is for allocating pre-existing candidates, NOT
                    # auto-creating operational tabs or running migrations.
                    client._ws("evergreen_bank")
                else:
                    from sheets_client import TAB_DEFINITIONS
                    client._ensure_tab("evergreen_bank", TAB_DEFINITIONS["evergreen_bank"])
    results: list[dict[str, Any]] = []
    coverage_by_account: dict[str, dict[str, int]] = {}
    for account_id in accounts:
        if args.evergreen_bank:
            kwargs: dict[str, Any] = {"apply": args.apply}
            if args.bank_reuse_only:
                kwargs["reuse_only"] = True
            results.append(replenish_bank(
                client if args.use_sheets else None, account_id, **kwargs,
            ))
            continue
        now = datetime.now(JST)
        budget_blocked = False
        sheets_quota_blocked = False
        paid_generation_paused = False
        bank_allocation_count = 0
        snapshot = copy.copy(client) if args.use_sheets else None
        if snapshot is not None:
            enable_readonly_record_cache(snapshot)
            setattr(snapshot, READONLY_RECORD_CACHE_ATTR, {"queue": [dict(row) for row in queue_rows]})
        slots = _required_text_slots(account_id, now, now + timedelta(hours=args.horizon_hours))
        account_covered = 0
        for slot in slots:
            ready_rows = _publishable_ready_rows(snapshot, queue_rows, account_id, slot)
            reserve_target = int(policy()["text_candidates_per_slot"])
            delivery_missing = delivery_generation_required(len(ready_rows))
            result: dict[str, Any] = {
                "account_id": account_id,
                "slot_id": slot["slot_id"],
                "business_date_jst": slot["business_date_jst"],
                "post_type": slot["post_type"],
                "reserve_target": reserve_target,
                "initial_publishable_ready": len(ready_rows),
                "delivery_generation_required": delivery_missing,
                "would_post": False,
            }

            def refresh_queue_snapshot() -> list[dict[str, Any]]:
                if not (args.use_sheets and args.apply):
                    return queue_rows
                prime_readonly_record_cache(snapshot, ("queue",))
                updated = [dict(row) for row in read_records_safely(snapshot, "queue")]
                setattr(snapshot, READONLY_RECORD_CACHE_ATTR, {"queue": updated})
                return updated

            def allocate_bank(required: int, already_ready: int) -> list[str]:
                nonlocal bank_allocation_count
                if not (args.apply and required > 0):
                    return []
                from evergreen_inventory import allocate_bank_candidate
                from generate_threads_ideas_from_references import original_text_similarity_guard
                recovered: list[str] = []
                bank_needed = min(required, max(0, reserve_target - already_ready))
                if args.reuse_only:
                    bank_needed = min(
                        bank_needed, max(0, args.max_bank_allocations - bank_allocation_count),
                    )
                for _ in range(bank_needed):
                    allocated = allocate_bank_candidate(client, account=account_id, slot=slot, now=now, apply=True,
                        runtime_check=lambda row: hybrid_ai_gate_passed(row, build_source_context(snapshot, row))[0]
                            and final_public_post_validator(str(row.get("public_post_text", "")), account_id).get("status") == "PASS",
                        similar=lambda a, b: original_text_similarity_guard(a, b)["status"] == "BLOCKED")
                    if allocated["status"] != "ALLOCATED":
                        break
                    recovered.append(allocated["queue_id"])
                    bank_allocation_count += 1
                return recovered

            if delivery_missing and args.apply and not sheets_quota_blocked:
                # Reuse an already validated bank candidate before spending an
                # AI request; it still has to pass the exact-slot publisher check.
                bank_ids = allocate_bank(1, len(ready_rows))
                if bank_ids:
                    result["delivery_recovery_route"] = "evergreen_bank"
                    result["delivery_recovery_queue_ids"] = bank_ids
                    queue_rows = refresh_queue_snapshot()
                    ready_rows = _publishable_ready_rows(snapshot, queue_rows, account_id, slot)

            if delivery_missing and sheets_quota_blocked:
                result["delivery_generation_status"] = "SKIPPED_SHEETS_QUOTA"
                result["delivery_generation_failure_category"] = "SHEETS_QUOTA_EXHAUSTED"
            if delivery_missing and len(ready_rows) == 0 and not sheets_quota_blocked:
                if args.reuse_only:
                    result["delivery_generation_status"] = "SKIPPED_PAID_GENERATION_REUSE_ONLY"
                    result["delivery_generation_failure_category"] = "NO_VALIDATED_BANK_CANDIDATE"
                else:
                    generated = replenish(
                        account_id, slot, apply=args.apply, required=1,
                        offline_only=(budget_blocked or paid_generation_paused),
                    )
                    result["delivery_generation_status"] = generated.get("status", "")
                    result["delivery_generation_failure_category"] = generated.get("failure_category", "")
                    sheets_quota_blocked = sheets_quota_blocked or (
                        generated.get("failure_category") == "SHEETS_QUOTA_EXHAUSTED"
                    )
                    result["delivery_generation_attempts"] = generated.get("attempts", [])
                    result["delivery_recovery_queue_ids"] = list(
                        result.get("delivery_recovery_queue_ids", [])
                    ) + list(generated.get("queue_ids", []))
                    budget_blocked = budget_blocked or any(
                        attempt.get("reason") == "AI_APPROVAL_BUDGET_EXHAUSTED"
                        for attempt in generated.get("attempts", [])
                    )
                    paid_generation_paused = (
                        paid_generation_paused or paid_generation_pause_required(generated)
                    )
                    queue_rows = refresh_queue_snapshot()
                    ready_rows = _publishable_ready_rows(snapshot, queue_rows, account_id, slot)

            # A delivery-safe row is the hard requirement. Additional reserve
            # candidates are attempted only after that row is durably visible.
            reserve_missing = reserve_generation_required(len(ready_rows), reserve_target)
            if reserve_missing and not sheets_quota_blocked:
                if args.reuse_only:
                    result["reserve_generation_status"] = "BANK_REUSE_ONLY"
                    bank_ids = allocate_bank(reserve_missing, len(ready_rows))
                    if bank_ids:
                        result["reserve_queue_ids"] = bank_ids
                        queue_rows = refresh_queue_snapshot()
                else:
                    reserve_result = replenish(
                        account_id, slot, apply=args.apply,
                        required=reserve_missing,
                        offline_only=(budget_blocked or paid_generation_paused),
                    )
                    result["reserve_generation_status"] = reserve_result.get("status", "")
                    result["reserve_generation_failure_category"] = reserve_result.get("failure_category", "")
                    sheets_quota_blocked = sheets_quota_blocked or (
                        reserve_result.get("failure_category") == "SHEETS_QUOTA_EXHAUSTED"
                    )
                    result["reserve_generation_attempts"] = reserve_result.get("attempts", [])
                    result["reserve_queue_ids"] = list(reserve_result.get("queue_ids", []))
                    budget_blocked = budget_blocked or any(
                        attempt.get("reason") == "AI_APPROVAL_BUDGET_EXHAUSTED"
                        for attempt in reserve_result.get("attempts", [])
                    )
                    paid_generation_paused = (
                        paid_generation_paused or paid_generation_pause_required(reserve_result)
                    )
                    queue_rows = refresh_queue_snapshot()
                    ready_rows = _publishable_ready_rows(snapshot, queue_rows, account_id, slot)
                    bank_ids = allocate_bank(
                        max(0, reserve_target - len(ready_rows)), len(ready_rows),
                    )
                    if bank_ids:
                        result["reserve_queue_ids"] = list(result.get("reserve_queue_ids", [])) + bank_ids
                        queue_rows = refresh_queue_snapshot()

            verified_rows = _publishable_ready_rows(snapshot, queue_rows, account_id, slot)
            if (args.apply and not verified_rows
                    and result.get("delivery_generation_status") == "READY_REPLENISHED"):
                result["delivery_generation_failure_category"] = "READY_CREATED_NOT_PUBLISHABLE"
                result["generated_ready_rejection_counts"] = generated_ready_rejection_counts(
                    snapshot, queue_rows, account_id, slot,
                    list(result.get("delivery_recovery_queue_ids") or []),
                )
            reserve_state = _reserve_status(len(verified_rows), reserve_target)
            account_covered += int(len(verified_rows) >= 1)
            result.update(
                status=(reserve_state if args.apply or ready_rows else "PLAN_ONLY"),
                delivery_slo="PASS" if len(verified_rows) >= 1 else "FAIL",
                publishable_ready_count=len(verified_rows),
                reserve_status="FULL" if len(verified_rows) >= reserve_target else "RESERVE_DEGRADED",
                reserve_shortfall=max(0, reserve_target - len(verified_rows)),
                would_post=False,
                paid_generation_paused=paid_generation_paused,
            )
            results.append(result)
        coverage_by_account[account_id] = {"covered_slots": account_covered, "required_slots": len(slots)}
        if args.reuse_only:
            results.append({
                "account_id": account_id,
                "stage": "bank_reuse_budget",
                "allocation_count": bank_allocation_count,
                "allocation_limit": args.max_bank_allocations,
                "paid_ai_requests_allowed": False,
                "would_post": False,
            })
    if args.evergreen_bank:
        payload = evergreen_bank_mode_result(results, accounts, apply=args.apply)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] in ("PASS", "PLAN_ONLY") else 1
    delivery_failures = [row for row in results if row.get("delivery_slo") == "FAIL"]
    coverage_total = sum(item["required_slots"] for item in coverage_by_account.values())
    coverage_covered = sum(item["covered_slots"] for item in coverage_by_account.values())
    coverage_status, coverage_percent, coverage_failure_reason = _coverage_result(coverage_total, coverage_covered)
    payload = {
        "status": "PASS" if not delivery_failures and coverage_status == "PASS" else "FAILED",
        "text_delivery_coverage_72h_percent": coverage_percent,
        "text_delivery_coverage_by_account": coverage_by_account,
        "coverage_failure_reason": coverage_failure_reason,
        "reserve_status": "RESERVE_DEGRADED" if any(row.get("reserve_status") == "RESERVE_DEGRADED" for row in results) else "FULL",
        "hard_delivery_failures": [{"account_id": row["account_id"], "slot_id": row["slot_id"],
                                    "reason": "NO_PUBLISHABLE_READY"} for row in delivery_failures],
        "results": results,
        "would_post": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if delivery_failures or coverage_status != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
