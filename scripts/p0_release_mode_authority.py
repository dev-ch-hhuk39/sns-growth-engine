#!/usr/bin/env python3
"""Two-stage Threads P0 release boundary: exact first canary -> signed continuous.

Default mode is CANARY. The continuous mode never activates itself and requires
an owner-signed per-account release plus a verified original canary in the
immutable host ledger AND live RAW Sheets posted-result/metric evidence.
No SNS calls, credential output, source text output, or operational mutations.
Passing only this gate does NOT replace persona, rights, duplicate, cooldown,
queue CAS, one-use ledger, provider authentication or kill-switch controls.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from metrics_collection_schedule import _parse_time
from metrics_reservations import ReservationBlocked, plan_reservations, read_table
from p0_exact_canary_approval import (
    CanaryBlocked, SHA40, SHA64, TOKEN as CANARY_TOKEN, _db_parent, _decode,
    _parse_utc, _read_private, _secret, _write_new,
    verify_current as verify_canary,
)
from p0_real_delivery_once import (
    ACCOUNTS, P0OnceBlocked, P0OnceGuard, POST_ID, QUEUES, source_fingerprint,
)
from validate_p0_once_runtime import inspect as inspect_p0

MODE_ENV = "SNS_P0_AUTONOMY_MODE"
MODE_CANARY = "canary"
MODE_CONTINUOUS = "continuous"
CONFIRM_CONTINUOUS = "OWNER_SIGNED_CONTINUOUS_AFTER_VERIFIED_CANARY_AND_EXTERNAL_EVIDENCE"
CONT_SCHEMA = "sns_p0_continuous_text_release_v1"
CONT_FIELDS = frozenset({
    "schema", "account_id", "release_sha", "approved_at_utc", "expires_at_utc",
    "approval_mode", "canary_queue_id", "canary_source_sha256",
    "canary_external_post_id", "canary_result_id", "attestations",
})
CONT_ATTESTATIONS = frozenset({
    "external_legacy_writers_frozen",
    "historic_outcomes_reconciled",
    "durable_independent_backup_restored",
    "account_identity_and_rights_approved",
    "verified_first_canary_with_3_metrics_reserved",
    "metrics_alerting_and_rollback_prepared",
    "operator_accepts_irreversible_one_use_no_retry",
    "owner_approved_bounded_continuous_text_only",
})
CONT_MAX_AGE = timedelta(days=30)
CONT_MAX_FILES_PER_ACCOUNT = 64
RESULT_ID = re.compile(r"[A-Za-z0-9_.:-]{2,160}\Z")
JSON_MAX = 8192


def _mac(payload: dict, key: bytes) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")
    return hmac.new(key, b"sns-p0-continuous-per-account-v1\0" + raw,
                    hashlib.sha256).hexdigest()


def _validate(doc: dict, *, now: datetime | None = None) -> None:
    if frozenset(doc) not in {CONT_FIELDS, CONT_FIELDS | {"signature"}}:
        raise CanaryBlocked("P0_CONTINUOUS_SCHEMA_INVALID")
    if doc.get("schema") != CONT_SCHEMA or doc.get("approval_mode") != CONFIRM_CONTINUOUS:
        raise CanaryBlocked("P0_CONTINUOUS_SCHEMA_INVALID")
    if type(doc.get("account_id")) is not str or doc["account_id"] not in ACCOUNTS:
        raise CanaryBlocked("P0_CONTINUOUS_ACCOUNT_INVALID")
    identities = (
        ("release_sha", SHA40), ("canary_source_sha256", SHA64),
        ("canary_queue_id", QUEUES), ("canary_external_post_id", POST_ID),
        ("canary_result_id", RESULT_ID),
    )
    for field, regex in identities:
        value = doc.get(field)
        if type(value) is not str or not regex.fullmatch(value):
            raise CanaryBlocked("P0_CONTINUOUS_SOURCE_IDENTITY_INVALID")
    attestations = doc.get("attestations")
    if (type(attestations) is not dict
            or frozenset(attestations) != CONT_ATTESTATIONS
            or any(attestations[key] is not True for key in CONT_ATTESTATIONS)):
        raise CanaryBlocked("P0_CONTINUOUS_OPERATOR_EVIDENCE_INCOMPLETE")
    first = _parse_utc(doc.get("approved_at_utc"))
    expiry = _parse_utc(doc.get("expires_at_utc"))
    if expiry <= first or expiry - first > CONT_MAX_AGE:
        raise CanaryBlocked("P0_CONTINUOUS_APPROVAL_DURATION_INVALID")
    if now is not None and (now < first or now >= expiry):
        raise CanaryBlocked("P0_CONTINUOUS_APPROVAL_INACTIVE")


def signed_continuous(payload: dict, *, key: bytes, now: datetime) -> dict:
    if type(payload) is not dict or type(key) is not bytes or len(key) != 32:
        raise CanaryBlocked("P0_CONTINUOUS_SIGNING_INPUT_INVALID")
    _validate(payload, now=now)
    return {**payload, "signature": _mac(payload, key)}


def _approval_name(doc: dict) -> str:
    t = _parse_utc(doc["approved_at_utc"])
    return "approved_continuous_%s_%s.json" % (
        doc["account_id"], t.strftime("%Y%m%dT%H%M%SZ"),
    )


def _load_current(*, account_id: str, release_sha: str,
                  allow_test_path: bool, now: datetime) -> dict:
    if account_id not in ACCOUNTS or type(release_sha) is not str or not SHA40.fullmatch(release_sha):
        raise CanaryBlocked("P0_CONTINUOUS_RELEASE_OR_ACCOUNT_INVALID")
    parent = _db_parent(allow_test_path=allow_test_path)
    paths = sorted(parent.glob(f"approved_continuous_{account_id}_*.json"))
    if not paths or len(paths) > CONT_MAX_FILES_PER_ACCOUNT:
        raise CanaryBlocked("P0_CONTINUOUS_OWNER_APPROVAL_UNAVAILABLE")
    active = []
    for path in paths:
        doc = _decode(_read_private(path))
        _validate(doc)
        if path.name != _approval_name(doc) or doc["account_id"] != account_id:
            raise CanaryBlocked("P0_CONTINUOUS_APPROVAL_FILE_IDENTITY_INVALID")
        sig = doc.get("signature")
        if type(sig) is not str or not SHA64.fullmatch(sig):
            raise CanaryBlocked("P0_CONTINUOUS_SIGNATURE_INVALID")
        payload = {field: doc[field] for field in CONT_FIELDS}
        if not hmac.compare_digest(sig, _mac(payload, _secret())):
            raise CanaryBlocked("P0_CONTINUOUS_SIGNATURE_INVALID")
        first = _parse_utc(doc["approved_at_utc"])
        end = _parse_utc(doc["expires_at_utc"])
        if first <= now < end and doc["release_sha"] == release_sha:
            active.append(doc)
    if len(active) != 1:
        raise CanaryBlocked("P0_CONTINUOUS_ACTIVE_APPROVAL_MISSING_OR_AMBIGUOUS")
    return active[0]


def _verify_host_canary(doc: dict, *, allow_test_path: bool) -> None:
    # An operator's checkbox alone cannot mint a synthetic successful post.
    # The verified state must already be in the authenticated irreversible
    # one-use journal, with the original accounted send attempt.
    try:
        if allow_test_path:
            ledger = P0OnceGuard(
                os.environ["SNS_P0_ONCE_DB_PATH"], _secret(),
                allow_test_path=True,
            )
        else:
            ledger = P0OnceGuard.from_env()
        inspect_p0(ledger, account_id=doc["account_id"])
        result = ledger.inspect(queue_id=doc["canary_queue_id"])
        if result["status"] != "POSTED_VERIFIED":
            raise CanaryBlocked("P0_CONTINUOUS_VERIFIED_CANARY_REQUIRED")
        path = _db_parent(allow_test_path=allow_test_path) / "once.sqlite3"
        with closing(sqlite3.connect(
            "file:" + quote(str(path), safe="/") + "?mode=ro",
            uri=True, timeout=5,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            canary = db.execute(
                "SELECT account_id,source_sha256,state,provider_post_id "
                "FROM sns_p0_once_heads WHERE queue_id=?",
                (doc["canary_queue_id"],),
            ).fetchall()
            sends = db.execute(
                "SELECT COUNT(*) FROM sns_p0_once_send_attempts WHERE queue_id=?",
                (doc["canary_queue_id"],),
            ).fetchone()[0]
            unresolved = db.execute(
                "SELECT COUNT(*) FROM sns_p0_once_heads WHERE account_id=? "
                "AND state!='POSTED_VERIFIED'", (doc["account_id"],),
            ).fetchone()[0]
        if (len(canary) != 1
                or tuple(canary[0]) != (
                    doc["account_id"], doc["canary_source_sha256"],
                    "POSTED_VERIFIED", doc["canary_external_post_id"],
                )
                or sends != 1 or unresolved):
            raise CanaryBlocked("P0_CONTINUOUS_CANARY_OR_UNCERTAIN_LEDGER_INVALID")
    except CanaryBlocked:
        raise
    except (P0OnceBlocked, sqlite3.Error, KeyError, OSError, ValueError):
        raise CanaryBlocked("P0_CONTINUOUS_HOST_PROOF_UNVERIFIABLE") from None


def _verify_live_canary(doc: dict, client: Any, *, now: datetime) -> None:
    """Require trusted RAW live posted and all 3 exact metric reservations."""
    try:
        _, posts = read_table(client, "posted_results")
        _, jobs = read_table(client, "metrics_collection_jobs")
        # Fail on global identity collisions, not only within this account.
        found = [
            r for r in posts
            if r.get("result_id") == doc["canary_result_id"]
            or r.get("queue_id") == doc["canary_queue_id"]
            or r.get("external_post_id") == doc["canary_external_post_id"]
        ]
        if len(found) != 1:
            raise CanaryBlocked("P0_CONTINUOUS_LIVE_PROVIDER_IDENTITY_AMBIGUOUS")
        post = found[0]
        url = urlparse(str(post.get("post_url", "")))
        if (post.get("account_id") != doc["account_id"]
                or post.get("queue_id") != doc["canary_queue_id"]
                or post.get("result_id") != doc["canary_result_id"]
                or post.get("external_post_id") != doc["canary_external_post_id"]
                or str(post.get("status", "")).upper() != "POSTED"
                or str(post.get("platform", "")).lower() != "threads"
                or str(post.get("verification_status", "")).upper() != "READ_AFTER_WRITE_PASS"
                or str(post.get("real_post", "")).lower() not in {"true", "1"}
                or _parse_time(post.get("posted_at")) is None
                or _parse_time(post.get("posted_at")) > now + timedelta(minutes=2)
                or url.scheme != "https"
                or url.hostname not in {"www.threads.com", "threads.com", "www.threads.net", "threads.net"}
                or url.username or url.password
                or not str(post.get("posted_text", ""))):
            raise CanaryBlocked("P0_CONTINUOUS_LIVE_PROVIDER_PROOF_INVALID")
        actual_sha = source_fingerprint(
            account_id=doc["account_id"], queue_id=doc["canary_queue_id"],
            text=post["posted_text"],
        )
        if not hmac.compare_digest(actual_sha, doc["canary_source_sha256"]):
            raise CanaryBlocked("P0_CONTINUOUS_LIVE_CANARY_TEXT_MISMATCH")
        plan = plan_reservations(
            posts, jobs, account_id=doc["account_id"],
            result_id=doc["canary_result_id"],
        )
        if plan["verified_count"] != 3 or plan["missing_count"] != 0:
            raise CanaryBlocked("P0_CONTINUOUS_THREE_METRIC_JOBS_REQUIRED")
        # Three reserved jobs are necessary but not sufficient: a permanently
        # failed collection for the initial canary blocks autonomous rollout.
        if any(
            str(job.get("status", "")).upper() == "FAILED"
            for job in jobs
            if str(job.get("result_id", "")) == doc["canary_result_id"]
        ):
            raise CanaryBlocked("P0_CONTINUOUS_CANARY_METRIC_FAILURE")
    except CanaryBlocked:
        raise
    except (ReservationBlocked, P0OnceBlocked, TypeError, ValueError, OSError):
        raise CanaryBlocked("P0_CONTINUOUS_LIVE_PROOF_UNVERIFIABLE") from None


def verify_release(
    *, account_id: str, release_sha: str,
    slot_id: str | None = None, queue_id: str | None = None,
    source_sha256: str | None = None, client: Any | None = None,
    allow_test_path: bool = False, now: datetime | None = None,
) -> dict:
    """Never conflate a host-only preflight with per-attempt live proof."""
    mode = os.environ.get(MODE_ENV, MODE_CANARY)
    if mode == MODE_CANARY:
        return verify_canary(
            account_id=account_id, release_sha=release_sha,
            slot_id=slot_id, queue_id=queue_id, source_sha256=source_sha256,
            allow_test_path=allow_test_path, now=now,
        )
    if mode != MODE_CONTINUOUS:
        raise CanaryBlocked("P0_RELEASE_UNKNOWN_MODE_BLOCKED")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise CanaryBlocked("P0_CONTINUOUS_TIME_INVALID")
    doc = _load_current(account_id=account_id, release_sha=release_sha,
                        allow_test_path=allow_test_path, now=current)
    _verify_host_canary(doc, allow_test_path=allow_test_path)
    if client is None:
        return {
            "status": "P0_CONTINUOUS_HOST_PREFLIGHT_ONLY",
            "publish_authorized": False,
            "live_provider_evidence_checked": False,
            "source_scope": "two_approved_p0_text_accounts",
        }
    _verify_live_canary(doc, client, now=current)
    return {
        "status": "P0_CONTINUOUS_PROOF_VERIFIED_ADD_ON_GATES_REQUIRED",
        "publish_authorized": False,
        "live_provider_evidence_checked": True,
        "source_scope": "two_approved_p0_text_accounts",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id")
    parser.add_argument("--release-sha", default=os.environ.get("CODE_REVISION", ""))
    parser.add_argument("--sign-private-request", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        if args.sign_private_request:
            if args.confirm != CONFIRM_CONTINUOUS:
                raise CanaryBlocked("P0_CONTINUOUS_EXPLICIT_OWNER_CONFIRMATION_REQUIRED")
            document = _decode(_read_private(args.sign_private_request))
            signed = signed_continuous(
                document, key=_secret(), now=datetime.now(timezone.utc),
            )
            # Never replace previous approvals, disable existing checks,
            # or set env flags while signing.
            target = _db_parent(allow_test_path=False) / _approval_name(signed)
            _write_new(target, signed)
            report = {"status": "CONTINUOUS_OWNER_APPROVAL_SAVED_NO_POST",
                      "publish_authorized": False}
        else:
            report = verify_release(
                account_id=args.account_id, release_sha=args.release_sha,
            )
    except CanaryBlocked as err:
        print(json.dumps({"status": "BLOCKED", "reason": str(err),
                          "publish_authorized": False}, sort_keys=True))
        return 78
    except Exception:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "P0_RELEASE_MODE_PROOF_UNVERIFIABLE",
                          "publish_authorized": False}, sort_keys=True))
        return 78
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
