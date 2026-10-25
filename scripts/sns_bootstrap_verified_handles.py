#!/usr/bin/env python3
"""Populate only missing SNS Threads handles after provider ID+username proof.

Requires the VPS global deploy lock outside this process. Does not refresh
tokens, post content, change platform IDs, or log provider/token values.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
ENV_FILE = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/shared/runtime.env")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import credential_env_names  # noqa: E402
from preflight_managed_threads_account import _NoIdentityRedirects  # noqa: E402
from publishers.threads_credentials import resolve_credentials  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
HANDLE = re.compile(r"[A-Za-z0-9_.]{1,30}\Z")
API_URL = "https://graph.threads.net/v1.0/me?" + urllib.parse.urlencode({"fields": "id,username"})


class IdentityBlocked(Exception):
    """A failed identity proof must never be represented as approval."""


def verify_live(account: str, credentials: dict) -> str:
    expected = str(credentials.get("user_id") or "")
    token = str(credentials.get("access_token") or "")
    if not expected or not token:
        raise IdentityBlocked("IDENTITY_INPUT_MISSING")
    req = urllib.request.Request(
        API_URL,
        headers={"Authorization": "Bearer " + token,
                 "User-Agent": "Chadult-SNS-Handle-Bootstrap/1"},
    )
    try:
        with urllib.request.build_opener(_NoIdentityRedirects()).open(req, timeout=20) as response:
            if response.status != 200:
                raise IdentityBlocked("IDENTITY_HTTP_FAILED")
            result = json.loads(response.read(65536))
    except Exception:
        raise IdentityBlocked("IDENTITY_PROVIDER_UNVERIFIED") from None
    if not isinstance(result, dict) or str(result.get("id") or "") != expected:
        raise IdentityBlocked("IDENTITY_USER_ID_MISMATCH")
    handle = str(result.get("username") or "").lstrip("@")
    if not HANDLE.fullmatch(handle):
        raise IdentityBlocked("IDENTITY_HANDLE_INVALID")
    return handle


def plan(existing: str, live_handles: dict[str, str]) -> tuple[str, int]:
    lines = existing.splitlines(keepends=True)
    changes = 0
    seen: set[str] = set()
    expected_keys = {credential_env_names(a)["handle"]: a for a in ACCOUNTS}
    output: list[str] = []
    for line in lines:
        key, sep, value = line.partition("=")
        if not sep or key not in expected_keys:
            output.append(line)
            continue
        if key in seen:
            raise IdentityBlocked("DUPLICATE_HANDLE_KEY")
        seen.add(key)
        current = value.strip().strip("'\"")
        observed = live_handles[expected_keys[key]]
        if current:
            if current.lower() != observed.lower():
                raise IdentityBlocked("CURRENT_HANDLE_MISMATCH")
            output.append(line)
            continue
        newline = "\n" if line.endswith("\n") else ""
        output.append(key + "=" + observed + newline)
        changes += 1
    if seen != expected_keys.keys():
        raise IdentityBlocked("HANDLE_KEYS_MISSING")
    return "".join(output), changes


def verify_file(path: Path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise IdentityBlocked("RUNTIME_ENV_NOT_REGULAR")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise IdentityBlocked("RUNTIME_ENV_MODE_INVALID")
    if st.st_uid != os.geteuid():
        raise IdentityBlocked("RUNTIME_ENV_OWNER_MISMATCH")
    return st


def bootstrap(path: Path = ENV_FILE, *, apply: bool = False) -> dict[str, object]:
    if path != ENV_FILE:
        raise IdentityBlocked("RUNTIME_ENV_PATH_INVALID")
    st = verify_file(path)
    raw = path.read_text(encoding="utf-8")
    credentials = {a: resolve_credentials(a) for a in ACCOUNTS}
    ids = [str(c.get("user_id") or "") for c in credentials.values()]
    if not all(ids) or len(set(ids)) != len(ids):
        raise IdentityBlocked("ACCOUNT_IDS_DUPLICATED_OR_MISSING")
    observed = {a: verify_live(a, c) for a, c in credentials.items()}
    if len({h.lower() for h in observed.values()}) != len(ACCOUNTS):
        raise IdentityBlocked("ACCOUNT_HANDLES_DUPLICATED")
    updated, changes = plan(raw, observed)
    report = {"status": "READY" if not apply else "PASS",
              "verified_accounts": len(ACCOUNTS), "handles_filled": changes,
              "tokens_changed": 0, "posts": 0}
    if not apply or not changes:
        return report
    if path.read_text(encoding="utf-8") != raw or path.stat().st_ino != st.st_ino:
        raise IdentityBlocked("RUNTIME_ENV_CHANGED_DURING_PROOF")
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".identity-handles.", suffix=".tmp", dir=path.parent)
        tmp = Path(tmp_name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(updated)
            f.flush()
            os.fsync(f.fileno())
        verify_file(path)
        if path.read_text(encoding="utf-8") != raw:
            raise IdentityBlocked("RUNTIME_ENV_CHANGED_BEFORE_COMMIT")
        os.replace(tmp, path)
        tmp = None
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-account-handle-bootstrap", action="store_true")
    options = parser.parse_args()
    if options.apply and not options.confirm_account_handle_bootstrap:
        print("SNS_HANDLE_BOOTSTRAP=BLOCKED reason=EXPLICIT_CONFIRMATION_REQUIRED")
        return 1
    try:
        result = bootstrap(apply=options.apply)
        print("SNS_HANDLE_BOOTSTRAP=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (IdentityBlocked, OSError, UnicodeError):
        print("SNS_HANDLE_BOOTSTRAP=BLOCKED reason=IDENTITY_OR_RUNTIME_PRECONDITION_UNVERIFIED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
