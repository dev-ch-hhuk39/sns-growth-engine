#!/usr/bin/env python3
"""VPS-only verified Threads refresh. Never posts or prints credentials.

Meta token refresh uses the account Bearer token over HTTPS and a fixed
grant_type URL. Verify returned identity BEFORE atomic local persistence.
Do not depend on GitHub Actions or mutate GitHub Secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import stat
import uuid
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
# Root-owned VPS helper runs from outside the immutable release. Local offline
# unit tests instead resolve the checkout; never select a writable runtime in
# production when the canonical immutable root exists.
if not (ROOT / "src" / "accounts" / "managed_accounts.py").is_file():
    ROOT = Path(__file__).resolve().parents[1]
STORE = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/shared/threads_tokens")
os.environ["THREADS_TOKEN_STORE_DIR"] = str(STORE)
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import credential_env_names  # noqa: E402
from preflight_managed_threads_account import _NoIdentityRedirects, _verify_live_identity  # noqa: E402
from publishers.threads_credentials import resolve_credentials  # noqa: E402
from threads_token_store import preflight_token_store, store_token  # noqa: E402
from sns_local_threads_expiry_watch import check_one  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
URL = "https://graph.threads.net/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "th_refresh_token"}
)
MIN_REFRESH_SECONDS = 60 * 60 * 24
MAX_REFRESH_SECONDS = 60 * 60 * 24 * 90
THRESHOLD = timedelta(days=21)
JST = timezone(timedelta(hours=9))
HANDLE = re.compile(r"[A-Za-z0-9_.]{1,30}\Z")


class TokenBlocked(Exception):
    """Fixed, secretless failure code."""


def quarantine(account: str) -> None:
    marker = STORE / (".refresh-unknown-" + account)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return
    except OSError:
        raise TokenBlocked("REFRESH_LATCH_PERSISTENCE_FAILED") from None
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write("REFRESH_OUTCOME_UNVERIFIED_MANUAL_RECONCILIATION\n")
        f.flush()
        os.fsync(f.fileno())


def renewal_due(account: str, now: datetime) -> bool:
    path = STORE / (account + ".json")
    if path.is_symlink():
        raise TokenBlocked("TOKEN_STORE_SYMLINK")
    if not path.exists():
        return True  # Legacy env-only token with unknown expiry, verify live first.
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("account_id") != account:
            raise ValueError()
        expiry = datetime.fromisoformat(str(doc["expires_at"]))
        if expiry.tzinfo is None:
            raise ValueError()
        return expiry - now <= THRESHOLD
    except (OSError, KeyError, ValueError, TypeError):
        raise TokenBlocked("TOKEN_EXPIRY_UNVERIFIED") from None


def refresh_api(current: str) -> tuple[str, int]:
    if not current:
        raise TokenBlocked("CURRENT_ACCESS_TOKEN_MISSING")
    req = urllib.request.Request(
        URL,
        headers={
            "Authorization": "Bearer " + current,
            "User-Agent": "Chadult-SNS-Local-Token-Renewal/1",
        },
    )
    try:
        opener = urllib.request.build_opener(_NoIdentityRedirects())
        with opener.open(req, timeout=30) as response:
            if response.status != 200:
                raise TokenBlocked("REFRESH_PROVIDER_HTTP_ERROR")
            raw = response.read(65537)
        if len(raw) > 65536:
            raise TokenBlocked("REFRESH_PROVIDER_RESPONSE_OVERSIZE")
        data = json.loads(raw)
    except Exception:
        raise TokenBlocked("REFRESH_PROVIDER_OUTCOME_UNVERIFIED") from None
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise TokenBlocked("REFRESH_TOKEN_MISSING")
    token = data["access_token"]
    seconds = data.get("expires_in")
    if not token.strip() or not isinstance(seconds, int) or isinstance(seconds, bool) \
            or not MIN_REFRESH_SECONDS <= seconds <= MAX_REFRESH_SECONDS:
        raise TokenBlocked("REFRESH_TOKEN_OR_EXPIRY_INVALID")
    return token, seconds


def _sync_directory() -> None:
    fd = os.open(STORE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def begin_refresh(account: str, current_token: str) -> tuple[int, int, str]:
    """Durable PREPARED before dispatch; a crash must prevent another refresh.

    Existing legacy text markers are never removed by this helper. Only the
    exact marker created by this invocation may be completed after verified
    local persistence. Marker contents contain no bearer credentials.
    """
    marker = STORE / (".refresh-unknown-" + account)
    nonce = uuid.uuid4().hex
    payload = {"schema": 1, "account_id": account, "state": "PREPARED",
               "operation_id": nonce,
               "previous_token_sha256": hashlib.sha256(current_token.encode()).hexdigest()}
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise TokenBlocked("TOKEN_REFRESH_MANUAL_RECONCILIATION_REQUIRED") from None
    except OSError:
        raise TokenBlocked("REFRESH_LATCH_PERSISTENCE_FAILED") from None
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            metadata = os.fstat(stream.fileno())
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory()
    except Exception:
        # Never remove an incomplete marker or dispatch after persistence fault.
        raise TokenBlocked("REFRESH_LATCH_PERSISTENCE_FAILED") from None
    return metadata.st_dev, metadata.st_ino, nonce


def complete_refresh(account: str, lease: tuple[int, int, str]) -> None:
    marker = STORE / (".refresh-unknown-" + account)
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="ascii") as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_mode & 0o077
                    or (metadata.st_dev, metadata.st_ino) != lease[:2]):
                raise ValueError()
            payload = json.loads(stream.read(4096))
        if (payload.get("operation_id") != lease[2]
                or payload.get("account_id") != account or payload.get("state") != "PREPARED"):
            raise ValueError()
        # This namespace is serialized by the service flock. The same lease
        # prevents completion of an earlier/manual or substituted operation.
        metadata = marker.lstat()
        if (metadata.st_dev, metadata.st_ino) != lease[:2]:
            raise ValueError()
        marker.unlink()
        _sync_directory()
    except Exception:
        raise TokenBlocked("REFRESH_COMPLETION_UNVERIFIED") from None


def inspect_current(account: str, current: dict, now: datetime) -> dict:
    try:
        metadata = check_one(account, current, clock=now, include_lifecycle=True)
    except Exception:
        raise TokenBlocked("CURRENT_TOKEN_LIFECYCLE_UNVERIFIED") from None
    return metadata


def run(*, apply: bool, account_id: str = "all") -> dict[str, object]:
    if account_id not in (*ACCOUNTS, "all"):
        raise TokenBlocked("ACCOUNT_SCOPE_INVALID")
    if os.environ.get("BUFFERED_POSTING_ENABLED") != "false":
        raise TokenBlocked("POSTING_OFF_PRECONDITION_FAILED")
    if STORE.is_symlink() or not STORE.is_dir():
        raise TokenBlocked("STORE_PATH_UNAVAILABLE")
    if STORE.stat().st_mode & 0o022:
        raise TokenBlocked("STORE_WRITABLE_BY_OTHERS")
    selected = ACCOUNTS if account_id == "all" else (account_id,)
    for account in ACCOUNTS:
        path = STORE / (account + ".json")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
            raise TokenBlocked("TOKEN_FILE_NOT_PRIVATE_REGULAR")
    credentials = {account: resolve_credentials(account) for account in ACCOUNTS}
    ids = [str(c.get("user_id") or "") for c in credentials.values() if c.get("user_id")]
    if len(set(ids)) != len(ids) or any(not credentials[a].get("user_id") for a in selected):
        raise TokenBlocked("EXPECTED_USER_IDS_MISSING_OR_DUPLICATE")
    now = datetime.now(JST)
    accounts: dict[str, str] = {}
    due_accounts: list[str] = []
    metadata_by_account = {}
    for account in selected:
        current = credentials[account]
        marker = STORE / (".refresh-unknown-" + account)
        if marker.exists() or marker.is_symlink():
            raise TokenBlocked("TOKEN_REFRESH_MANUAL_RECONCILIATION_REQUIRED")
        expected_handle = os.environ.get(credential_env_names(account)["handle"], "").strip().lstrip("@")
        if not HANDLE.fullmatch(expected_handle):
            raise TokenBlocked("EXPECTED_HANDLE_MISSING_OR_INVALID")
        identity = _verify_live_identity(account, current)
        if identity.get("status") != "PASS":
            raise TokenBlocked("CURRENT_TOKEN_IDENTITY_UNVERIFIED")
        metadata = inspect_current(account, current, now)
        metadata_by_account[account] = metadata
        # Provider expiry is authoritative; local expiry alone cannot trigger a
        # refresh of a fresh, expired, wrong-app or otherwise unverified token.
        due = metadata["expires_at"] - now.timestamp() <= THRESHOLD.total_seconds()
        if due and now.timestamp() - metadata["issued_at"] < MIN_REFRESH_SECONDS:
            raise TokenBlocked("TOKEN_NOT_OLD_ENOUGH_TO_REFRESH")
        accounts[account] = "DUE" if due else "CURRENT"
        if due:
            preflight_token_store(STORE, account)
            due_accounts.append(account)
    if not apply:
        return {"status": "DRY_RUN", "accounts": accounts,
                "refresh_due": len(due_accounts), "posts": 0}
    for account in due_accounts:
        lease = begin_refresh(account, credentials[account]["access_token"])
        # The durable marker remains even on SIGKILL/power loss/BaseException.
        # Neither an HTTP error nor a lost response permits an automatic retry.
        try:
            token, expires_in = refresh_api(credentials[account]["access_token"])
            refreshed_at = datetime.now(JST)
            new_credentials = {**credentials[account], "access_token": token}
            if _verify_live_identity(account, new_credentials).get("status") != "PASS":
                raise TokenBlocked("NEW_TOKEN_IDENTITY_UNVERIFIED")
            verified = check_one(account, new_credentials, clock=refreshed_at, include_lifecycle=True)
            previous = metadata_by_account[account]
            if (verified["expires_at"] <= previous["expires_at"]
                    or abs(verified["expires_at"] - refreshed_at.timestamp() - expires_in) > 120
                    or not set(previous["scopes"]).issubset(verified["scopes"])):
                raise TokenBlocked("NEW_TOKEN_LIFECYCLE_MISMATCH")
            data = {"account_id": account, "access_token": token,
                    "user_id": credentials[account]["user_id"],
                    "app_id": credentials[account]["app_id"],
                    "refreshed_at": refreshed_at.isoformat(),
                    "expires_at": datetime.fromtimestamp(verified["expires_at"], JST).isoformat()}
            store_token(STORE, account, data)
            saved = resolve_credentials(account)
            if saved.get("access_token") != token or saved.get("user_id") != data["user_id"]:
                raise TokenBlocked("TOKEN_SAVE_READBACK_MISMATCH")
            complete_refresh(account, lease)
            accounts[account] = "REFRESHED"
        except Exception:
            # Marker already exists before dispatch; never overwrite/delete it.
            raise TokenBlocked("TOKEN_REFRESH_MANUAL_RECONCILIATION_REQUIRED") from None
    return {"status": "PASS", "accounts": accounts, "refresh_due": len(due_accounts),
            "posts": 0, "github_secrets_changed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=(*ACCOUNTS, "all"), default="all")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-token-renewal", action="store_true")
    options = parser.parse_args()
    if options.apply and not options.confirm_token_renewal:
        print('SNS_LOCAL_THREADS_TOKENS={"status":"BLOCKED","reason":"EXPLICIT_CONFIRMATION_REQUIRED"}')
        return 1
    try:
        accounts = ACCOUNTS if options.account_id == "all" else (options.account_id,)
        results = {}
        for account in accounts:
            try:
                results[account] = run(apply=options.apply, account_id=account)
            except TokenBlocked as exc:
                results[account] = {"status": "BLOCKED", "reason": str(exc), "posts": 0}
            except Exception:
                results[account] = {"status": "BLOCKED", "reason": "UNVERIFIED_RUNTIME_FAILURE", "posts": 0}
        blocked = any(item["status"] == "BLOCKED" for item in results.values())
        report = {"status": "BLOCKED" if blocked else ("PASS" if options.apply else "DRY_RUN"),
                  "accounts": results, "posts": 0, "github_secrets_changed": False}
        print("SNS_LOCAL_THREADS_TOKENS=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 1 if report["status"] == "BLOCKED" else 0
    except TokenBlocked as exc:
        print("SNS_LOCAL_THREADS_TOKENS=" + json.dumps({
            "status": "BLOCKED", "reason": str(exc), "posts": 0,
        }, sort_keys=True, separators=(",", ":")))
        return 1
    except Exception:
        print('SNS_LOCAL_THREADS_TOKENS={"status":"BLOCKED","reason":"UNVERIFIED_RUNTIME_FAILURE","posts":0}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
