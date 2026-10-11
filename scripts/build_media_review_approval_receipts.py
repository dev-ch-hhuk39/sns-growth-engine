#!/usr/bin/env python3
"""Validate proposed media review decisions into non-authoritative audit receipts.

This module is intentionally offline. Neither a self-reported reviewer ID nor
a local receipt is an authenticated approval or permission to publish.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_media_human_review_plan import MEDIA_SLOTS

INTAKE_SCHEMA = "sns_media_review_intake_v1"
PLAN_SCHEMA = "sns_media_human_review_plan_v1"
RECEIPT_SCHEMA = "sns_media_review_receipts_v1"
ZERO_SHA256 = "0" * 64
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{3,128}\Z")
QUEUE_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
EVIDENCE_RE = re.compile(r"ev_[A-Za-z0-9_.:-]{6,120}\Z")
APPROVAL_EVIDENCE = (
    "rights_grant", "publisher_permission", "source_identity",
    "media_validation", "caption_quality", "account_fit", "asset_provenance",
)
CLIP_EVIDENCE = ("clip_lineage",)
DECISIONS = {"APPROVE", "REJECT", "REQUEST_EVIDENCE", "REVOKE"}
REASON_CODES = {
    "rights_denied", "consent_withdrawn", "rights_expired", "evidence_missing",
    "quality_failed", "source_mismatch", "account_fit_failed", "technical_failed",
    "review_reopened", "other_review_needed",
}
MAX_EVENTS_PER_BATCH = 20
MAX_LEDGER_EVENTS = 2000


class ReviewContractError(ValueError):
    """Sanitized contract failure: error strings never include supplied values."""


def _canonical(obj: Any) -> bytes:
    try:
        return json.dumps(
            obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewContractError("noncanonical_json") from exc


def _sha256(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _require_keys(obj: Any, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(obj, dict):
        raise ReviewContractError("record_not_object")
    optional = optional or set()
    if set(obj) - required - optional or required - set(obj):
        raise ReviewContractError("record_fields_invalid")


def _safe_id(value: Any) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise ReviewContractError("identifier_invalid")
    return value


def _parse_instant(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ReviewContractError("timestamp_invalid")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewContractError("timestamp_invalid") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ReviewContractError("timestamp_timezone_required")
    return dt.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _validate_plan(plan: Any) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not isinstance(plan, dict):
        raise ReviewContractError("plan_invalid")
    if (plan.get("schema_version") != PLAN_SCHEMA
            or plan.get("status") != "HUMAN_REVIEW_REQUIRED"
            or plan.get("slot_count") != 4
            or plan.get("would_post") is not False
            or plan.get("writes_performed") is not False
            or plan.get("ready_transitions_performed") is not False
            or plan.get("publish_authorized") is not False):
        raise ReviewContractError("plan_safety_invariants_invalid")
    items = plan.get("items")
    if (not isinstance(items, list) or len(items) > 20
            or plan.get("review_item_count") != len(items)):
        raise ReviewContractError("plan_items_invalid")
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    seen_slots: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ReviewContractError("plan_item_invalid")
        account = item.get("account_id")
        slot = item.get("slot_id")
        post_type = item.get("post_type")
        if not isinstance(account, str) or not isinstance(slot, str):
            raise ReviewContractError("plan_item_identity_invalid")
        if MEDIA_SLOTS.get((account, slot)) != post_type:
            raise ReviewContractError("plan_item_identity_invalid")
        seen_slots.add((account, slot))
        queue_id = item.get("queue_id")
        if not isinstance(queue_id, str):
            raise ReviewContractError("plan_queue_id_invalid")
        if queue_id and not QUEUE_ID_RE.fullmatch(queue_id):
            raise ReviewContractError("plan_queue_id_invalid")
        blockers = item.get("blockers")
        if (not isinstance(blockers, list)
                or not all(isinstance(x, str) and 1 <= len(x) <= 96 for x in blockers)
                or item.get("human_approval_required") is not True
                or item.get("publish_authorized") is not False):
            raise ReviewContractError("plan_item_safety_invalid")
        state = item.get("review_state")
        if state not in {"MISSING_EXACT_CANDIDATE", "ACTION_REQUIRED",
                         "FINAL_HUMAN_REVIEW_REQUIRED"}:
            raise ReviewContractError("plan_item_state_invalid")
        if (not queue_id) != (state == "MISSING_EXACT_CANDIDATE"):
            # A malformed queue ID can occur in ACTION_REQUIRED in 5B-1:
            # it must remain review-only, never approvable.
            if not queue_id and state == "ACTION_REQUIRED":
                pass
            else:
                raise ReviewContractError("plan_queue_binding_invalid")
        if item.get("priority") not in {"P1", "P2", "P3"}:
            raise ReviewContractError("plan_item_priority_invalid")
        key = (account, slot, queue_id)
        if key in lookup:
            raise ReviewContractError("plan_candidate_duplicate")
        lookup[key] = item
    if seen_slots != set(MEDIA_SLOTS):
        raise ReviewContractError("plan_slots_incomplete")
    return lookup


def _validate_history(
    previous: Any,
    source_plan_sha256: str,
    candidates: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if previous is None:
        return [], ZERO_SHA256
    if not isinstance(previous, dict):
        raise ReviewContractError("history_invalid")
    if (previous.get("schema_version") != RECEIPT_SCHEMA
            or previous.get("source_plan_sha256") != source_plan_sha256
            or previous.get("publish_authorized") is not False
            or previous.get("ready_transitions_performed") is not False
            or previous.get("writes_performed") is not False
            or previous.get("authenticated_approval") is not False
            or previous.get("reviewer_identity_verified") is not False
            or previous.get("status") != "DRAFT_REVIEW_EVENTS_NOT_AUTHORIZED"):
        raise ReviewContractError("history_safety_invariants_invalid")
    events = previous.get("events")
    if (not isinstance(events, list) or len(events) > MAX_LEDGER_EVENTS
            or previous.get("event_count") != len(events)):
        raise ReviewContractError("history_events_invalid")
    head = ZERO_SHA256
    for index, event in enumerate(events, start=1):
        _require_keys(event, {
            "schema_version", "sequence", "previous_event_sha256",
            "source_plan_sha256", "account_id", "slot_id", "queue_id",
            "decision", "reviewer_id", "reviewed_at", "reason_code",
            "evidence_ids", "usage_scope", "rights_valid_from",
            "rights_expires_at", "revokes_event_sha256", "review_state",
            "reviewer_identity_verified", "effective_approval",
            "publish_authorized", "event_sha256",
        })
        if (not isinstance(event["decision"], str)
                or not isinstance(event["account_id"], str)
                or not isinstance(event["slot_id"], str)
                or not isinstance(event["reason_code"], str)
                or not isinstance(event["usage_scope"], str)
                or event["schema_version"] != RECEIPT_SCHEMA
                or event["decision"] not in DECISIONS
                or not isinstance(event["queue_id"], str)
                or (event["queue_id"] and not QUEUE_ID_RE.fullmatch(event["queue_id"]))
                or (event["account_id"], event["slot_id"], event["queue_id"]) not in candidates
                or event["reason_code"] not in REASON_CODES | {""}
                or event["usage_scope"] not in {"", "THREADS_ORGANIC_ONLY"}
                or not isinstance(event["evidence_ids"], dict)
                or not all(isinstance(x, str) and EVIDENCE_RE.fullmatch(x)
                           for x in event["evidence_ids"].values())
                or (
                    set(event["evidence_ids"]) != (
                        set(APPROVAL_EVIDENCE)
                        | (set(CLIP_EVIDENCE)
                           if MEDIA_SLOTS.get((event["account_id"], event["slot_id"]))
                           == "approved_source_clip" else set())
                    ) if event["decision"] == "APPROVE" else bool(event["evidence_ids"])
                )):
            raise ReviewContractError("history_event_invalid")
        _safe_id(event["reviewer_id"])
        _parse_instant(event["reviewed_at"])
        if event["rights_valid_from"]:
            _parse_instant(event["rights_valid_from"])
        if event["rights_expires_at"]:
            _parse_instant(event["rights_expires_at"])
        if (event.get("sequence") != index
                or event.get("previous_event_sha256") != head
                or event.get("source_plan_sha256") != source_plan_sha256
                or event.get("reviewer_identity_verified") is not False
                or event.get("effective_approval") is not False
                or event.get("publish_authorized") is not False
                or event.get("review_state") not in {
                    "APPROVAL_DRAFT_AWAITING_AUTHENTICATED_REVIEW",
                    "REVOCATION_DRAFT_AWAITING_AUTHENTICATED_REVIEW",
                    "REJECTION_DRAFT_AWAITING_AUTHENTICATED_REVIEW",
                    "EVIDENCE_REQUEST_DRAFT",
                }):
            raise ReviewContractError("history_event_invariants_invalid")
        expected = _sha256({k: v for k, v in event.items() if k != "event_sha256"})
        if event.get("event_sha256") != expected:
            raise ReviewContractError("history_hash_chain_invalid")
        head = expected
    if previous.get("last_event_sha256") != head:
        raise ReviewContractError("history_head_invalid")
    return events, head


def _last_event(events: list[dict[str, Any]], key: tuple[str, str, str]) -> dict[str, Any] | None:
    for event in reversed(events):
        if (event["account_id"], event["slot_id"], event["queue_id"]) == key:
            return event
    return None


def build_receipts(
    plan: dict[str, Any],
    intake: dict[str, Any],
    *,
    as_of: datetime | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an immutable snapshot of draft, unauthenticated review events."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ReviewContractError("system_clock_timezone_required")
    now = now.astimezone(timezone.utc)
    choices = _validate_plan(plan)
    digest = _sha256(plan)
    _require_keys(intake, {"schema_version", "source_plan_sha256", "events"})
    if (intake["schema_version"] != INTAKE_SCHEMA
            or intake["source_plan_sha256"] != digest):
        raise ReviewContractError("stale_or_wrong_plan_fingerprint")
    actions = intake["events"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_EVENTS_PER_BATCH:
        raise ReviewContractError("review_batch_size_invalid")
    history, head = _validate_history(previous, digest, choices)
    if len(history) + len(actions) > MAX_LEDGER_EVENTS:
        raise ReviewContractError("history_capacity_exceeded")
    events = [dict(item) for item in history]
    seen: set[tuple[str, str, str]] = set()
    for action in actions:
        if not isinstance(action, dict) or action.get("decision") not in DECISIONS:
            raise ReviewContractError("review_decision_invalid")
        decision = action["decision"]
        base_keys = {
            "account_id", "slot_id", "queue_id", "reviewer_id", "reviewed_at", "decision",
        }
        extras = {
            "APPROVE": {"evidence_ids", "usage_scope", "rights_valid_from",
                        "rights_expires_at", "human_checks_confirmed"},
            "REJECT": {"reason_code"},
            "REQUEST_EVIDENCE": {"reason_code"},
            "REVOKE": {"reason_code", "revokes_event_sha256"},
        }[decision]
        _require_keys(action, base_keys | extras)
        account = action["account_id"]
        slot = action["slot_id"]
        if not isinstance(account, str) or not isinstance(slot, str):
            raise ReviewContractError("candidate_identity_invalid")
        queue = action["queue_id"]
        if not isinstance(queue, str) or (queue and not QUEUE_ID_RE.fullmatch(queue)):
            raise ReviewContractError("candidate_identity_invalid")
        key = (account, slot, queue)
        candidate = choices.get(key)
        if candidate is None:
            raise ReviewContractError("candidate_not_in_review_plan")
        if key in seen:
            raise ReviewContractError("duplicate_action_in_batch")
        seen.add(key)
        actor = _safe_id(action["reviewer_id"])
        reviewed = _parse_instant(action["reviewed_at"])
        if reviewed > now + timedelta(minutes=5) or reviewed < now - timedelta(days=7):
            raise ReviewContractError("review_timestamp_outside_allowed_window")
        latest = _last_event(events, key)
        reason = ""
        evidence: dict[str, str] = {}
        usage_scope = ""
        valid_from = ""
        expires_at = ""
        revokes_hash = ""
        if decision == "APPROVE":
            if (not queue or candidate.get("review_state") != "FINAL_HUMAN_REVIEW_REQUIRED"
                    or candidate.get("priority") != "P3"
                    or candidate.get("blockers") != []
                    or latest is not None and latest["decision"] == "APPROVE"):
                raise ReviewContractError("approval_blocked_by_review_plan_or_replay")
            if action["human_checks_confirmed"] is not True:
                raise ReviewContractError("explicit_human_checks_required")
            if action["usage_scope"] != "THREADS_ORGANIC_ONLY":
                raise ReviewContractError("rights_usage_scope_invalid")
            usage_scope = "THREADS_ORGANIC_ONLY"
            needed = set(APPROVAL_EVIDENCE)
            if MEDIA_SLOTS[(account, slot)] == "approved_source_clip":
                needed.update(CLIP_EVIDENCE)
            _require_keys(action["evidence_ids"], needed)
            evidence = action["evidence_ids"]
            if not all(isinstance(v, str) and EVIDENCE_RE.fullmatch(v)
                       for v in evidence.values()):
                raise ReviewContractError("evidence_reference_invalid")
            if len(set(evidence.values())) != len(evidence):
                raise ReviewContractError("evidence_reference_reused")
            start = _parse_instant(action["rights_valid_from"])
            end = _parse_instant(action["rights_expires_at"])
            if not start < end or not start <= reviewed <= end or not start <= now < end:
                raise ReviewContractError("rights_not_currently_valid")
            valid_from = _iso(start)
            expires_at = _iso(end)
            state = "APPROVAL_DRAFT_AWAITING_AUTHENTICATED_REVIEW"
        elif decision == "REVOKE":
            if (not queue or latest is None or latest["decision"] != "APPROVE"
                    or action["revokes_event_sha256"] != latest["event_sha256"]):
                raise ReviewContractError("revocation_target_invalid")
            revokes_hash = latest["event_sha256"]
            if action["reason_code"] not in REASON_CODES:
                raise ReviewContractError("review_reason_invalid")
            reason = action["reason_code"]
            state = "REVOCATION_DRAFT_AWAITING_AUTHENTICATED_REVIEW"
        else:
            if not queue and decision != "REQUEST_EVIDENCE":
                raise ReviewContractError("missing_candidate_not_rejectable")
            if action["reason_code"] not in REASON_CODES:
                raise ReviewContractError("review_reason_invalid")
            reason = action["reason_code"]
            state = ("REJECTION_DRAFT_AWAITING_AUTHENTICATED_REVIEW"
                     if decision == "REJECT" else "EVIDENCE_REQUEST_DRAFT")
        event = {
            "schema_version": RECEIPT_SCHEMA,
            "sequence": len(events) + 1,
            "previous_event_sha256": head,
            "source_plan_sha256": digest,
            "account_id": account,
            "slot_id": slot,
            "queue_id": queue,
            "decision": decision,
            "reviewer_id": actor,
            "reviewed_at": _iso(reviewed),
            "reason_code": reason,
            "evidence_ids": evidence,
            "usage_scope": usage_scope,
            "rights_valid_from": valid_from,
            "rights_expires_at": expires_at,
            "revokes_event_sha256": revokes_hash,
            "review_state": state,
            "reviewer_identity_verified": False,
            "effective_approval": False,
            "publish_authorized": False,
        }
        head = _sha256(event)
        event["event_sha256"] = head
        events.append(event)
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": "DRAFT_REVIEW_EVENTS_NOT_AUTHORIZED",
        "source_plan_sha256": digest,
        "generated_at": _iso(now),
        "event_count": len(events),
        "new_event_count": len(actions),
        "events": events,
        "last_event_sha256": head,
        "reviewer_identity_verified": False,
        "authenticated_approval": False,
        "ready_transitions_performed": False,
        "writes_performed": False,
        "publish_authorized": False,
    }


def _read_json(path: Path, *, maximum_bytes: int) -> Any:
    if path.stat().st_size > maximum_bytes:
        raise ReviewContractError("input_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True, type=Path)
    parser.add_argument("--intake-json", required=True, type=Path)
    parser.add_argument("--previous-receipts-json", type=Path)
    parser.add_argument("--output-json", type=Path,
                        help="New immutable local snapshot path; no overwrite")
    args = parser.parse_args()
    try:
        plan = _read_json(args.plan_json, maximum_bytes=2_000_000)
        intake = _read_json(args.intake_json, maximum_bytes=250_000)
        history = (_read_json(args.previous_receipts_json, maximum_bytes=5_000_000)
                   if args.previous_receipts_json else None)
        receipts = build_receipts(plan, intake, previous=history)
        output = json.dumps(receipts, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output_json:
            with args.output_json.open("x", encoding="utf-8") as stream:
                stream.write(output)
        else:
            print(output, end="")
    except (OSError, UnicodeError, json.JSONDecodeError, ReviewContractError):
        # Never echo supplied data, file paths, evidence values or raw errors.
        print("REVIEW_RECEIPT_BLOCKED")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
