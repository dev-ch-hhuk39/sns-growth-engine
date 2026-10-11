#!/usr/bin/env python3
"""Trusted-server integration contract for *precommit* SNS media review checks.

This module has no HTTP endpoint, identity issuer adapter, database adapter,
queue mutation, or publisher. Only a trusted backend may supply the verifier
and canonical reader. Local JSON receipts are always non-authoritative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from build_media_human_review_plan import MEDIA_SLOTS
from build_media_review_approval_receipts import (
    APPROVAL_EVIDENCE,
    CLIP_EVIDENCE,
    EVIDENCE_RE,
    QUEUE_ID_RE,
    ReviewContractError,
    _parse_instant,
    _sha256,
    _validate_history,
    _validate_plan,
)

EXPECTED_AUDIENCE = "sns-growth-media-review"
USAGE_SCOPE = "THREADS_ORGANIC_ONLY"
REVIEWER_ROLES = frozenset({"MEDIA_REVIEWER", "ADMIN"})
MAX_SESSION_AGE = timedelta(minutes=30)
MAX_MFA_AGE = timedelta(minutes=20)
MAX_DRAFT_AGE = timedelta(days=1)
MAX_EVIDENCE_VERIFICATION_AGE = timedelta(days=1)
MAX_CLOCK_SKEW = timedelta(minutes=2)
SAFE_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{3,128}\Z")
SAFE_REVISION_RE = re.compile(r"[A-Za-z0-9_.:-]{8,128}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PASS_RIGHTS = frozenset({"APPROVED", "AUTHORIZED", "GRANTED", "ALLOWED"})
REQUIRED_QUEUE_PASSES = (
    "validator_status",
    "internal_leak_status",
    "account_fit_status",
    "alignment_status",
    "hybrid_ai_status",
)


class PrecommitBlocked(ValueError):
    """Sanitized reason code, never a raw token, URL or provider exception."""


@dataclass(frozen=True)
class VerifiedReviewer:
    """Returned ONLY by a real server-side token verifier, never request JSON."""

    subject: str
    roles: frozenset[str]
    account_scopes: frozenset[str]
    issuer: str
    audience: str
    authenticated_at: datetime
    mfa_at: datetime | None
    expires_at: datetime
    disabled: bool = False


@dataclass(frozen=True)
class CanonicalReviewContext:
    """Data freshly fetched from trusted, access-controlled server-side stores."""

    plan: dict[str, Any]
    receipts: dict[str, Any]
    queue: dict[str, Any]
    evidence_by_id: Mapping[str, dict[str, Any]]


@dataclass(frozen=True)
class ReviewRequest:
    account_id: str
    slot_id: str
    queue_id: str
    expected_queue_revision: str
    expected_plan_sha256: str
    expected_receipts_head_sha256: str
    draft_event_sha256: str
    confirm_human_review: bool


class SessionVerifier(Protocol):
    def verify(self, bearer_token: str, *, now: datetime) -> VerifiedReviewer:
        """Validate signature, issuer, audience, revocation and MFA server-side."""


class CanonicalReviewReader(Protocol):
    def load_current(self, account_id: str, slot_id: str, queue_id: str) -> CanonicalReviewContext:
        """Read plan, ledger, queue revision and evidence from trusted storage."""


def _utc(value: datetime, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PrecommitBlocked(code)
    return value.astimezone(timezone.utc)


def _time(value: Any, code: str) -> datetime:
    try:
        return _parse_instant(value)
    except (ReviewContractError, TypeError, OverflowError) as exc:
        raise PrecommitBlocked(code) from exc


def _valid_window(start: Any, expires: Any, now: datetime, code: str) -> datetime:
    beginning = _time(start, code)
    ending = _time(expires, code)
    if not beginning <= now < ending:
        raise PrecommitBlocked(code)
    return ending


def _check_request(request: ReviewRequest) -> None:
    if not isinstance(request, ReviewRequest):
        raise PrecommitBlocked("review_request_invalid")
    if (MEDIA_SLOTS.get((request.account_id, request.slot_id)) is None
            or not isinstance(request.queue_id, str)
            or not QUEUE_ID_RE.fullmatch(request.queue_id)
            or not isinstance(request.expected_queue_revision, str)
            or not SAFE_REVISION_RE.fullmatch(request.expected_queue_revision)
            or not all(isinstance(v, str) and SHA256_RE.fullmatch(v) for v in (
                request.expected_plan_sha256,
                request.expected_receipts_head_sha256,
                request.draft_event_sha256,
            ))
            or request.confirm_human_review is not True):
        raise PrecommitBlocked("review_request_incomplete")


def _check_principal(
    principal: Any, request: ReviewRequest, now: datetime, trusted_issuer: str,
) -> VerifiedReviewer:
    if not isinstance(principal, VerifiedReviewer):
        raise PrecommitBlocked("reviewer_not_verified")
    if (not isinstance(principal.subject, str)
            or not SAFE_ID_RE.fullmatch(principal.subject)
            or not isinstance(principal.roles, frozenset)
            or not isinstance(principal.account_scopes, frozenset)
            or principal.disabled is not False
            or not isinstance(principal.issuer, str)
            or not trusted_issuer
            or principal.issuer != trusted_issuer
            or principal.audience != EXPECTED_AUDIENCE):
        raise PrecommitBlocked("reviewer_identity_invalid")
    if not (principal.roles & REVIEWER_ROLES) or request.account_id not in principal.account_scopes:
        raise PrecommitBlocked("reviewer_out_of_scope")
    auth_time = _utc(principal.authenticated_at, "reviewer_session_invalid")
    expiry = _utc(principal.expires_at, "reviewer_session_invalid")
    if (not auth_time <= now + MAX_CLOCK_SKEW
            or now - auth_time > MAX_SESSION_AGE
            or not now < expiry
            or expiry - now > timedelta(hours=8)):
        raise PrecommitBlocked("reviewer_session_expired")
    if principal.mfa_at is None:
        raise PrecommitBlocked("reviewer_mfa_required")
    mfa_time = _utc(principal.mfa_at, "reviewer_mfa_required")
    if not mfa_time <= now + MAX_CLOCK_SKEW or now - mfa_time > MAX_MFA_AGE:
        raise PrecommitBlocked("reviewer_mfa_required")
    return principal


def _verify_queue(queue: Any, request: ReviewRequest) -> dict[str, Any]:
    if not isinstance(queue, dict):
        raise PrecommitBlocked("canonical_queue_missing")
    if (queue.get("queue_id") != request.queue_id
            or queue.get("account_id") != request.account_id
            or queue.get("slot_id") != request.slot_id
            or queue.get("revision") != request.expected_queue_revision):
        raise PrecommitBlocked("canonical_queue_changed")
    if (queue.get("platform") != "threads"
            or queue.get("status") != "READY"
            or queue.get("rights_review_required") is not False
            or str(queue.get("rights_status") or "").upper() not in PASS_RIGHTS
            or str(queue.get("permission_status") or "").upper() not in PASS_RIGHTS):
        raise PrecommitBlocked("canonical_queue_not_safe")
    if any(queue.get(k) != "PASS" for k in REQUIRED_QUEUE_PASSES):
        raise PrecommitBlocked("canonical_queue_quality_failed")
    if (not isinstance(queue.get("media_asset_id"), str)
            or not SAFE_ID_RE.fullmatch(queue["media_asset_id"])
            or not isinstance(queue.get("source_id"), str)
            or not SAFE_ID_RE.fullmatch(queue["source_id"])):
        raise PrecommitBlocked("canonical_asset_lineage_missing")
    return queue


def _latest_draft(
    plan: Any, receipts: Any, request: ReviewRequest, principal: VerifiedReviewer,
    now: datetime,
) -> tuple[dict[str, Any], str, str]:
    try:
        choices = _validate_plan(plan)
        plan_sha = _sha256(plan)
        if plan_sha != request.expected_plan_sha256:
            raise PrecommitBlocked("review_plan_changed")
        key = (request.account_id, request.slot_id, request.queue_id)
        candidate = choices.get(key)
        if (not isinstance(candidate, dict)
                or candidate.get("review_state") != "FINAL_HUMAN_REVIEW_REQUIRED"
                or candidate.get("priority") != "P3"
                or candidate.get("blockers") != []):
            raise PrecommitBlocked("review_candidate_not_eligible")
        events, ledger_head = _validate_history(receipts, plan_sha, choices)
    except ReviewContractError as exc:
        raise PrecommitBlocked("review_draft_chain_invalid") from exc
    if ledger_head != request.expected_receipts_head_sha256:
        raise PrecommitBlocked("review_draft_changed")
    matching = [
        e for e in events
        if (e["account_id"], e["slot_id"], e["queue_id"]) == key
    ]
    if not matching:
        raise PrecommitBlocked("review_draft_missing")
    latest = matching[-1]
    if (latest["decision"] != "APPROVE"
            or latest["event_sha256"] != request.draft_event_sha256
            or latest["reviewer_id"] != principal.subject
            or latest.get("usage_scope") != USAGE_SCOPE):
        raise PrecommitBlocked("review_draft_not_authorizable")
    reviewed = _time(latest["reviewed_at"], "review_draft_timestamp_invalid")
    if reviewed > now + MAX_CLOCK_SKEW or now - reviewed > MAX_DRAFT_AGE:
        raise PrecommitBlocked("review_draft_stale")
    return latest, plan_sha, ledger_head


def _verify_evidence(
    event: dict[str, Any],
    queue: dict[str, Any],
    records: Mapping[str, dict[str, Any]],
    now: datetime,
) -> datetime:
    if not isinstance(records, Mapping):
        raise PrecommitBlocked("trusted_evidence_unavailable")
    account, slot, queue_id = event["account_id"], event["slot_id"], event["queue_id"]
    needed = set(APPROVAL_EVIDENCE)
    if MEDIA_SLOTS[(account, slot)] == "approved_source_clip":
        needed.update(CLIP_EVIDENCE)
    refs = event.get("evidence_ids")
    if (not isinstance(refs, dict) or set(refs) != needed
            or len(set(refs.values())) != len(refs)
            or any(not isinstance(v, str) or not EVIDENCE_RE.fullmatch(v)
                   for v in refs.values())):
        raise PrecommitBlocked("evidence_references_invalid")
    expiry = _valid_window(
        event.get("rights_valid_from"), event.get("rights_expires_at"),
        now, "review_rights_expired",
    )
    for kind, ref in refs.items():
        record = records.get(ref)
        if not isinstance(record, dict):
            raise PrecommitBlocked("trusted_evidence_missing")
        if (record.get("evidence_id") != ref
                or record.get("kind") != kind
                or record.get("account_id") != account
                or record.get("slot_id") != slot
                or record.get("queue_id") != queue_id
                or record.get("media_asset_id") != queue["media_asset_id"]
                or record.get("source_id") != queue["source_id"]
                or record.get("usage_scope") != USAGE_SCOPE
                or record.get("verification_status") != "VERIFIED"
                or record.get("revoked") is not False
                or record.get("original_reference_verified") is not True
                or record.get("allowed_platforms") != ["threads"]
                or not isinstance(record.get("allowed_territories"), list)
                or "JP" not in record["allowed_territories"]):
            raise PrecommitBlocked("trusted_evidence_invalid")
        verified = _time(record.get("verified_at"), "trusted_evidence_stale")
        if verified > now + MAX_CLOCK_SKEW or now - verified > MAX_EVIDENCE_VERIFICATION_AGE:
            raise PrecommitBlocked("trusted_evidence_stale")
        proof_expiry = _valid_window(
            record.get("rights_valid_from"),
            record.get("rights_expires_at"),
            now,
            "trusted_evidence_expired",
        )
        expiry = min(expiry, proof_expiry)
    return expiry


def evaluate_precommit(
    request: ReviewRequest,
    bearer_token: str,
    *,
    verifier: SessionVerifier | None,
    canonical: CanonicalReviewReader | None,
    trusted_issuer: str,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Validate for a *future* atomic commit. Never authenticates via local JSON.

    A successful result is NOT a signed approval, ledger commit, READY update,
    or permission to post. No default identity/evidence adapter is supplied.
    """
    now = _utc(as_of or datetime.now(timezone.utc), "review_clock_invalid")
    _check_request(request)
    if not verifier or not canonical:
        raise PrecommitBlocked("trusted_adapters_not_configured")
    if (not isinstance(bearer_token, str)
            or len(bearer_token) < 16 or len(bearer_token) > 4096
            or not bearer_token.startswith("Bearer ")
            or len(bearer_token.split()) != 2):
        raise PrecommitBlocked("session_token_missing")
    token = bearer_token[7:]
    try:
        principal = verifier.verify(token, now=now)
    except Exception as exc:
        raise PrecommitBlocked("session_verification_failed") from exc
    principal = _check_principal(principal, request, now, trusted_issuer)
    try:
        context = canonical.load_current(
            request.account_id, request.slot_id, request.queue_id,
        )
    except Exception as exc:
        raise PrecommitBlocked("canonical_review_unavailable") from exc
    if not isinstance(context, CanonicalReviewContext):
        raise PrecommitBlocked("canonical_review_unavailable")
    queue = _verify_queue(context.queue, request)
    event, plan_sha, ledger_head = _latest_draft(
        context.plan, context.receipts, request, principal, now,
    )
    rights_until = _verify_evidence(event, queue, context.evidence_by_id, now)
    return {
        "status": "PRECOMMIT_CHECKS_PASSED_NO_APPROVAL",
        "account_id": request.account_id,
        "slot_id": request.slot_id,
        "queue_id": request.queue_id,
        "queue_revision": request.expected_queue_revision,
        "draft_event_sha256": request.draft_event_sha256,
        "source_plan_sha256": plan_sha,
        "receipts_head_sha256": ledger_head,
        "session_subject": principal.subject,
        "rights_recheck_due_before": rights_until.isoformat(timespec="seconds"),
        "canonical_queue_checked": True,
        "trusted_evidence_checked": True,
        "session_verified_by_adapter": True,
        "requires_atomic_approval_commit": True,
        "requires_publish_time_revalidation": True,
        "effective_approval": False,
        "ready_transitions_performed": False,
        "writes_performed": False,
        "publish_authorized": False,
    }
