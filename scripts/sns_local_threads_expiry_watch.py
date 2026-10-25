#!/usr/bin/env python3
"""Read-only expiry watchdog for three owner-configured Threads accounts.

It NEVER refreshes, writes, prints, caches, or forwards token values.
Meta debug_token is called only at the fixed official HTTPS API endpoint.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
if not (ROOT / "src" / "accounts" / "managed_accounts.py").is_file():
    ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from publishers.threads_credentials import resolve_credentials  # noqa: E402
from accounts.managed_accounts import credential_env_names  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
API_URL = "https://graph.threads.net/debug_token"
WARNING_DAYS = 14


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("META_REDIRECT_NOT_ALLOWED")


def check_one(account: str, current: dict, *, clock: datetime | None = None) -> dict:
    if account not in ACCOUNTS:
        raise ValueError("ACCOUNT_SCOPE_INVALID")
    token = str(current.get("access_token") or "")
    user_id = str(current.get("user_id") or "")
    if not token or not user_id:
        raise ValueError("CREDENTIALS_NOT_CONFIGURED")
    if len(token) > 4096:
        raise ValueError("TOKEN_SIZE_INVALID")
    url = API_URL + "?" + urllib.parse.urlencode({"input_token": token})
    req = urllib.request.Request(
        url, headers={
            "Authorization": "Bearer " + token,
            "User-Agent": "Chadult-SNS-ReadOnly-Threads-Expiry-Watch/1",
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as resp:
            if resp.status != 200:
                raise ValueError("META_HTTP_NOT_SUCCESS")
            payload = resp.read(65537)
        if len(payload) > 65536:
            raise ValueError("META_RESPONSE_TOO_LARGE")
        data = json.loads(payload).get("data")
    except Exception:
        raise ValueError("META_READONLY_DEBUG_UNVERIFIED") from None
    if not isinstance(data, dict) or data.get("is_valid") is not True:
        raise ValueError("META_TOKEN_INVALID")
    if str(data.get("user_id") or "") != user_id:
        raise ValueError("META_ACCOUNT_ID_MISMATCH")
    scopes = data.get("scopes")
    if not isinstance(scopes, list) or "threads_basic" not in scopes:
        raise ValueError("META_BASIC_SCOPE_MISSING")
    expiry = data.get("expires_at")
    if type(expiry) is not int or not 1_600_000_000 < expiry < 4_100_000_000:
        raise ValueError("META_EXPIRY_INVALID")
    now = clock or datetime.now(timezone.utc)
    days_left = round((expiry - now.timestamp()) / 86400, 2)
    return {
        "account": account, "valid": True, "id_matched": True,
        "expires_in_days": days_left,
        "state": "RENEWAL_REQUIRED" if days_left <= WARNING_DAYS else "CURRENT",
    }


def run() -> dict:
    if os.environ.get("BUFFERED_POSTING_ENABLED") != "false":
        raise ValueError("POSTING_OFF_PRECONDITION_MISSING")
    records = {a: resolve_credentials(a) for a in ACCOUNTS}
    ids = [str(v.get("user_id") or "") for v in records.values()]
    if not all(ids) or len(set(ids)) != len(ACCOUNTS):
        raise ValueError("ACCOUNT_ID_ANCHOR_MISSING_OR_DUPLICATED")
    for account in ACCOUNTS:
        if not os.environ.get(credential_env_names(account)["handle"], "").strip():
            raise ValueError("ACCOUNT_HANDLE_ANCHOR_MISSING")
    checks = [check_one(a, records[a]) for a in ACCOUNTS]
    warning = [v["account"] for v in checks if v["state"] == "RENEWAL_REQUIRED"]
    return {
        "status": "RENEWAL_REQUIRED" if warning else "PASS",
        "accounts": checks, "renewal_due_accounts": warning,
        "posted": 0, "token_refreshes": 0,
        "sheets_writes": 0, "paid_api_calls": 0,
    }


def main() -> int:
    try:
        report = run()
    except Exception:
        report = {
            "status": "BLOCKED_UNVERIFIED", "posted": 0,
            "token_refreshes": 0, "sheets_writes": 0,
        }
    print("SNS_THREADS_EXPIRY_AUDIT=" + json.dumps(
        report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
