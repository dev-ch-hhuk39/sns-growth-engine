#!/usr/bin/env python3
"""Read one owner source's download permission; no credentials leave the host."""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import sys

RUNTIME_ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
DEPLOY_LOCK = Path("/run/lock/chadult-production-deploy.lock")
ACCOUNTS = {"night_scout", "liver_manager"}
CONNECTION_KEYS = {"SNS_MASTER_SHEET_ID", "NOTE_MASTER_SHEET_ID", "SPREADSHEET_ID",
                   "SA_JSON_BASE64", "GCP_SA_JSON_BASE64", "GCP_SA_JSON"}


def validate_request(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"account_id", "source_id", "source_handle", "canonical_url", "revision"}:
        raise ValueError("request_schema_invalid")
    if (not isinstance(value["account_id"], str) or value["account_id"] not in ACCOUNTS or not isinstance(value["source_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value["source_id"])
            or not isinstance(value["source_handle"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value["source_handle"])
            or not isinstance(value["canonical_url"], str) or not 1 <= len(value["canonical_url"]) <= 2048
            or not isinstance(value["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["revision"])):
        raise ValueError("request_scope_invalid")
    return dict(value)


def request_hash(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _protected_text(path: Path, uid: int, *, maximum: int, exact_mode: int | None = None) -> str:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid or before.st_nlink != 1
            or before.st_mode & 0o022 or not 0 < before.st_size <= maximum
            or (exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode)):
        raise ValueError("protected_file_unverified")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if os.fstat(stream.fileno()) != before:
            raise ValueError("protected_file_changed")
        encoded = stream.read(maximum + 1)
    after = path.lstat()
    if any(getattr(before, key) != getattr(after, key) for key in (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")):
        raise ValueError("protected_file_changed")
    return encoded.decode("utf-8")


def _sheet_configuration(uid: int) -> tuple[str, dict]:
    # Parse only existing connection aliases. Never execute shell, discover
    # credential files, or export provider/publishing variables to the Mac.
    text = _protected_text(RUNTIME_ROOT / "shared/runtime.env", uid, maximum=131072, exact_mode=0o600)
    values = {}
    for line in text.splitlines():
        key, separator, raw = line.strip().removeprefix("export ").partition("=")
        if not separator or key not in CONNECTION_KEYS:
            continue
        if key in values:
            raise ValueError("ambiguous_connection_key")
        parsed = shlex.split(raw, comments=False)
        if len(parsed) != 1:
            raise ValueError("invalid_connection_value")
        values[key] = parsed[0]
    sheet = next((values[key] for key in ("SNS_MASTER_SHEET_ID", "NOTE_MASTER_SHEET_ID", "SPREADSHEET_ID") if values.get(key)), "")
    encoded = next((values[key] for key in ("SA_JSON_BASE64", "GCP_SA_JSON_BASE64", "GCP_SA_JSON") if values.get(key)), "")
    if not sheet or not encoded:
        raise ValueError("protected_connection_missing")
    raw = encoded if encoded.lstrip().startswith("{") else base64.b64decode(encoded, validate=True).decode("utf-8")
    credential = json.loads(raw)
    if not isinstance(credential, dict) or credential.get("type") != "service_account":
        raise ValueError("service_account_required")
    return sheet, credential


def _permission_verdict(release: Path, request: dict, uid: int) -> tuple[dict, list[str]]:
    sys.path[:0] = [str(release / "src"), str(release / "scripts")]
    from media.golden_evidence import validate_registered_binding
    from media.permission_ledger import account_source_permission_reasons, evaluate_permission
    from reference.source_registry import load_registry
    from sheets_client import SheetsClient
    from sheets_record_reader import read_records_safely

    decision = validate_registered_binding({"account_id": request["account_id"], "source_id": request["source_id"],
        "source_handle": request["source_handle"], "url": request["canonical_url"]}, load_registry(preserve_duplicates=True))
    if decision["status"] != "PASS" or decision["binding"]["platform"] not in {"x", "youtube"}:
        raise ValueError("registered_owner_source_required")
    binding = decision["binding"]
    if binding["canonical_url"] != request["canonical_url"]:
        raise ValueError("exact_canonical_request_required")
    sheet, credential = _sheet_configuration(uid)
    client = SheetsClient(sheet, credential, dry_run=False)
    if type(client) is not SheetsClient or client.dry_run is not False:
        raise ValueError("real_client_required")
    rows = read_records_safely(client, "media_permissions", preserve_strings=True)
    permission = evaluate_permission(rows, request["source_id"], account_id=request["account_id"],
        source_handle=binding["source_handle"], required_flags=("allow_download",))
    reasons = [*permission["reasons"], *account_source_permission_reasons(permission["row"],
        account_id=request["account_id"], source_handle=binding["source_handle"])]
    if not permission["allowed"] and not reasons:
        reasons.append("download_permission_denied")
    return binding, sorted(set(reasons))


def read_current_permission(request: dict) -> dict:
    request = validate_request(request)
    result = {"status": "BLOCKED", "allowed": False, "operation": "download",
              "request_sha256": request_hash(request), "reasons": ["permission_authority_unverified"],
              "credentials_exported": False, "production_writes": False, "publish_authorized": False}
    descriptors = []
    try:
        if sys.platform != "linux":
            return result
        uid = pwd.getpwnam("snsrunner").pw_uid
        if os.geteuid() != uid:
            return result
        for directory in (RUNTIME_ROOT, RUNTIME_ROOT / "releases", RUNTIME_ROOT / "shared"):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
                return result
        for path in (DEPLOY_LOCK, RUNTIME_ROOT / "shared/locks/sheets-io.lock"):
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in (0, uid):
                return result
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        release = RUNTIME_ROOT / "releases" / request["revision"]
        if (RUNTIME_ROOT / "current").resolve(strict=True) != release or release.resolve(strict=True) != release:
            return result
        for directory in (release, release / "src", release / "scripts"):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
                return result
        marker = _protected_text(release / ".production-release", uid, maximum=41)
        if marker not in (request["revision"], request["revision"] + "\n"):
            return result
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            binding, reasons = _permission_verdict(release, request, uid)
        if (RUNTIME_ROOT / "current").resolve(strict=True) != release:
            return result
        result.update(status="ALLOW" if not reasons else "DENY", allowed=not reasons, reasons=reasons,
                      binding={key: binding[key] for key in ("account_id", "source_id", "canonical_url", "external_post_id", "platform", "source_handle")},
                      revision=request["revision"], verified_at=datetime.now(timezone.utc).isoformat())
    except Exception:
        pass  # No provider details or protected connection values cross SSH.
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--read-current", action="store_true")
    args = parser.parse_args()
    request = validate_request(json.loads(args.request_json))
    if not args.read_current:
        print(json.dumps({"status": "PLAN_ONLY", "request_sha256": request_hash(request), "would_connect": False}))
        return 0
    if sys.platform == "linux":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = read_current_permission(request)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ALLOW", "DENY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
