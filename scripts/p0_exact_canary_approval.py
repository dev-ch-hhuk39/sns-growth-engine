#!/usr/bin/env python3
"""Extra, owner-signed, short-lived exact-text canary barrier.

Never confuses operator attestations with independent production evidence:
this is an additional necessary condition, NOT a posting authorization.
No Sheets, SNS or other network calls; no operational SQLite writes.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from p0_real_delivery_once import ACCOUNTS, P0OnceBlocked, QUEUES, _safe_path

SCHEMA = "sns_p0_exact_text_canary_approval_v1"
FILENAME = "approved_text_canary.json"
TOKEN = "OWNER_SIGNED_EXACT_TEXT_CANARY_AFTER_EXTERNAL_EVIDENCE"
ATTESTATIONS = frozenset({
    "external_legacy_writers_frozen",
    "historic_outcomes_reconciled",
    "durable_backup_restored",
    "account_identity_and_rights_approved",
    "exact_text_and_queue_owner_approved",
    "metrics_alerting_and_rollback_prepared",
    "operator_accepts_one_use_no_retry",
})
DOC_FIELDS = frozenset({
    "schema", "account_id", "slot_id", "queue_id", "source_sha256",
    "release_sha", "approved_at_utc", "expires_at_utc",
    "approval_mode", "attestations",
})
SIGNED_FIELDS = DOC_FIELDS | {"signature"}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SLOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,159}\Z")
MAX_BYTES = 8192
MAX_AGE = timedelta(minutes=30)
CLOCK_SKEW = timedelta(minutes=1)


class CanaryBlocked(RuntimeError):
    """Fixed public code only, never secrets, paths or queue identifiers."""


def _pairs(rows: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in rows:
        if key in result:
            raise CanaryBlocked("P0_CANARY_JSON_DUPLICATE_KEYS")
        result[key] = value
    return result


def _secret() -> bytes:
    hex_key = os.environ.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", hex_key):
        raise CanaryBlocked("P0_CANARY_SIGNING_KEY_UNAVAILABLE")
    return bytes.fromhex(hex_key)


def _db_parent(*, allow_test_path: bool) -> Path:
    try:
        candidate = _safe_path(
            os.environ.get("SNS_P0_ONCE_DB_PATH", ""),
            allow_test_path=allow_test_path,
        )
    except P0OnceBlocked:
        raise CanaryBlocked("P0_CANARY_PRIVATE_DIRECTORY_INVALID") from None
    if candidate.name != "once.sqlite3":
        raise CanaryBlocked("P0_CANARY_LEDGER_NAME_INVALID")
    return candidate.parent


def _filename(*, allow_test_path: bool, account_id: str | None = None,
              allow_legacy: bool = False) -> Path:
    parent = _db_parent(allow_test_path=allow_test_path)
    if type(account_id) is not str or account_id not in ACCOUNTS:
        raise CanaryBlocked("P0_CANARY_ACCOUNT_SCOPE_INVALID")
    per_account = parent / f"approved_text_canary_{account_id}.json"
    # Read-only legacy fallback for an operator who signed before the
    # account-separated release. New approvals are always account-specific.
    if allow_legacy and not per_account.exists() and not per_account.is_symlink():
        old = parent / FILENAME
        if old.exists() or old.is_symlink():
            return old
    return per_account


def _read_private(path: Path) -> bytes:
    try:
        # Keep symlink checking and reading on one descriptor.
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                    or st.st_mode & 0o077 or st.st_nlink != 1
                    or st.st_size < 2 or st.st_size > MAX_BYTES):
                raise CanaryBlocked("P0_CANARY_PRIVATE_FILE_UNSAFE")
            raw = os.read(fd, MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise CanaryBlocked("P0_CANARY_PRIVATE_FILE_OVERSIZE")
            return raw
        finally:
            os.close(fd)
    except (OSError, ValueError):
        raise CanaryBlocked("P0_CANARY_PRIVATE_FILE_UNAVAILABLE") from None


def _decode(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except CanaryBlocked:
        raise
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        raise CanaryBlocked("P0_CANARY_MANIFEST_INVALID") from None
    if type(value) is not dict:
        raise CanaryBlocked("P0_CANARY_MANIFEST_INVALID")
    return value


def _parse_utc(value: Any) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise CanaryBlocked("P0_CANARY_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise CanaryBlocked("P0_CANARY_TIME_INVALID") from None
    if parsed.tzinfo is None:
        raise CanaryBlocked("P0_CANARY_TIME_INVALID")
    return parsed


def _validate_fields(doc: dict, *, now: datetime) -> None:
    if frozenset(doc) != DOC_FIELDS and frozenset(doc) != SIGNED_FIELDS:
        raise CanaryBlocked("P0_CANARY_SCHEMA_MISMATCH")
    if doc.get("schema") != SCHEMA or doc.get("approval_mode") != TOKEN:
        raise CanaryBlocked("P0_CANARY_SCHEMA_MISMATCH")
    if type(doc.get("account_id")) is not str or doc["account_id"] not in ACCOUNTS:
        raise CanaryBlocked("P0_CANARY_ACCOUNT_SCOPE_INVALID")
    if (type(doc.get("queue_id")) is not str
            or not QUEUES.fullmatch(doc["queue_id"])
            or type(doc.get("slot_id")) is not str
            or not SLOT.fullmatch(doc["slot_id"])
            or type(doc.get("source_sha256")) is not str
            or not SHA64.fullmatch(doc["source_sha256"])
            or type(doc.get("release_sha")) is not str
            or not SHA40.fullmatch(doc["release_sha"])):
        raise CanaryBlocked("P0_CANARY_EXACT_IDENTITY_INVALID")
    attest = doc.get("attestations")
    if (type(attest) is not dict
            or frozenset(attest) != ATTESTATIONS
            or any(attest[key] is not True for key in ATTESTATIONS)):
        raise CanaryBlocked("P0_CANARY_OPERATOR_ATTESTATION_INCOMPLETE")
    start = _parse_utc(doc.get("approved_at_utc"))
    end = _parse_utc(doc.get("expires_at_utc"))
    if (end <= start or end - start > MAX_AGE
            or now < start - CLOCK_SKEW or now >= end
            or now - start > MAX_AGE):
        raise CanaryBlocked("P0_CANARY_APPROVAL_EXPIRED_OR_NOT_YET_VALID")


def _mac(payload: dict, key: bytes) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")
    return hmac.new(key, b"sns-p0-canary-owner-consent-v1\0" + raw,
                    hashlib.sha256).hexdigest()


def signed_manifest(payload: dict, *, key: bytes, now: datetime) -> dict:
    """Offline signer primitive; never an independent proof of attestations."""
    if type(key) is not bytes or len(key) != 32 or type(payload) is not dict:
        raise CanaryBlocked("P0_CANARY_SIGNING_INPUT_INVALID")
    _validate_fields(payload, now=now)
    signed = {**payload, "signature": _mac(payload, key)}
    return signed


def verify_current(
    *, account_id: str, release_sha: str,
    slot_id: str | None = None, queue_id: str | None = None,
    source_sha256: str | None = None,
    allow_test_path: bool = False, now: datetime | None = None,
) -> dict:
    """Fail closed before Sheets mutation and before one-use network entry."""
    if type(account_id) is not str or account_id not in ACCOUNTS:
        raise CanaryBlocked("P0_CANARY_ACCOUNT_SCOPE_INVALID")
    if type(release_sha) is not str or not SHA40.fullmatch(release_sha):
        raise CanaryBlocked("P0_CANARY_RELEASE_UNVERIFIED")
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise CanaryBlocked("P0_CANARY_TIME_INVALID")
    doc = _decode(_read_private(_filename(
        allow_test_path=allow_test_path, account_id=account_id, allow_legacy=True,
    )))
    _validate_fields(doc, now=current)
    signature = doc.get("signature")
    if type(signature) is not str or not SHA64.fullmatch(signature):
        raise CanaryBlocked("P0_CANARY_SIGNATURE_INVALID")
    payload = {key: doc[key] for key in DOC_FIELDS}
    if not hmac.compare_digest(signature, _mac(payload, _secret())):
        raise CanaryBlocked("P0_CANARY_SIGNATURE_INVALID")
    if doc["account_id"] != account_id:
        raise CanaryBlocked("P0_CANARY_ACCOUNT_MISMATCH")
    if doc["release_sha"] != release_sha:
        raise CanaryBlocked("P0_CANARY_RELEASE_MISMATCH")
    for field, value in (("slot_id", slot_id), ("queue_id", queue_id),
                         ("source_sha256", source_sha256)):
        if value is not None and doc[field] != value:
            raise CanaryBlocked("P0_CANARY_EXACT_SOURCE_MISMATCH")
    return {
        "status": "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY",
        "scope": "night_liver_exact_text_only",
        "operator_attestation_present": True,
        "independent_provider_evidence_verified": False,
        "automated_publish_authorized": False,
        "production_cutover_authorized": False,
    }


def _write_new(path: Path, document: dict) -> None:
    raw = (json.dumps(document, ensure_ascii=True,
                      sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if len(raw) > MAX_BYTES:
        raise CanaryBlocked("P0_CANARY_PRIVATE_FILE_OVERSIZE")
    flags = os.O_WRONLY | os.O_EXCL | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        raise CanaryBlocked("P0_CANARY_APPROVAL_FILE_ALREADY_EXISTS") from None
    except OSError:
        raise CanaryBlocked("P0_CANARY_APPROVAL_FILE_WRITE_FAILED") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=False)
    parser.add_argument("--release-sha", default=os.environ.get("CODE_REVISION", ""))
    parser.add_argument("--sign-private-request", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        if args.sign_private_request:
            if args.confirm != TOKEN:
                raise CanaryBlocked("P0_CANARY_SIGNER_EXPLICIT_OWNER_CONFIRMATION_REQUIRED")
            # This creates a new signed private approval; does NOT change switches.
            request = _decode(_read_private(args.sign_private_request))
            now = datetime.now(timezone.utc)
            doc = signed_manifest(request, key=_secret(), now=now)
            target = _filename(allow_test_path=False, account_id=doc["account_id"])
            _write_new(target, doc)
            result = {"status": "SIGNED_PRIVATE_ATTESTATION_SAVED_NO_POST",
                      "publish_authorized": False}
        else:
            result = verify_current(account_id=args.account_id,
                                    release_sha=args.release_sha)
    except CanaryBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "publish_authorized": False}, sort_keys=True))
        return 78
    except Exception:
        print(json.dumps({"status": "BLOCKED", "reason": "P0_CANARY_UNVERIFIED",
                          "publish_authorized": False}, sort_keys=True))
        return 78
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
