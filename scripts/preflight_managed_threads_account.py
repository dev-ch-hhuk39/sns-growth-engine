#!/usr/bin/env python3
"""Credential-safe managed Threads account onboarding preflight; never posts."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accounts.managed_accounts import (  # noqa: E402
    account_production_enabled,
    account_status,
    credential_env_names,
    managed_account,
)
from publishers.threads_credentials import has_required_for_publish, resolve_credentials  # noqa: E402


def _verify_live_identity(account_id: str, credentials: dict[str, str]) -> dict[str, Any]:
    expected_handle = os.environ.get(credential_env_names(account_id)["handle"], "").strip().lstrip("@")
    query = urllib.parse.urlencode({
        "fields": "id,username",
        "access_token": credentials["access_token"],
    })
    request = urllib.request.Request(
        f"https://graph.threads.net/v1.0/me?{query}",
        headers={"User-Agent": "sns-growth-engine-account-preflight/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "status": "CREDENTIAL_BLOCKED",
            "reason": type(exc).__name__,
            "secret_values_exposed": False,
        }
    actual_id = str(payload.get("id") or "")
    actual_handle = str(payload.get("username") or "").lstrip("@")
    reasons: list[str] = []
    if actual_id != str(credentials.get("user_id") or ""):
        reasons.append("threads_user_id_mismatch")
    if expected_handle and actual_handle.lower() != expected_handle.lower():
        reasons.append("threads_handle_mismatch")
    return {
        "status": "PASS" if not reasons else "ACCOUNT_IDENTITY_BLOCKED",
        "reason": ",".join(reasons),
        "resolved_user_id_matches": not any(reason == "threads_user_id_mismatch" for reason in reasons),
        "resolved_handle_matches": not any(reason == "threads_handle_mismatch" for reason in reasons),
        "secret_values_exposed": False,
    }


def build_preflight(account_id: str, *, verify_live_identity: bool = False) -> dict[str, Any]:
    account = managed_account(account_id)
    credentials = resolve_credentials(account_id)
    publish_ready, publish_reason = has_required_for_publish(credentials)
    names = credential_env_names(account_id)
    credential_presence = {
        "handle": bool(os.environ.get(names["handle"], "").strip()),
        "user_id": bool(credentials.get("user_id")),
        "access_token": bool(credentials.get("access_token")),
    }
    status = account_status(account_id)
    result: dict[str, Any] = {
        "account_id": account_id,
        "managed": True,
        "account_status": status,
        "production_enabled": account_production_enabled(account_id),
        "credential_presence": credential_presence,
        "credential_names": names,
        "review_policy": account.get("review_policy", ""),
        "scheduled_routes": account.get("scheduled_routes", []),
        "x_publish_enabled": False,
        "would_post": False,
        "secret_values_exposed": False,
    }
    if not publish_ready or not credential_presence["handle"]:
        result.update({
            "status": "CREDENTIAL_PENDING" if status == "CREDENTIAL_PENDING" else "CREDENTIAL_BLOCKED",
            "reason": publish_reason or "THREADS_HANDLE is missing",
            "live_identity": {"status": "NOT_CHECKED"},
        })
        return result
    identity = (
        _verify_live_identity(account_id, credentials)
        if verify_live_identity
        else {"status": "PLAN_ONLY", "reason": "live_identity_check_not_requested"}
    )
    result["live_identity"] = identity
    result["status"] = "PASS" if identity["status"] in {"PASS", "PLAN_ONLY"} else identity["status"]
    result["reason"] = str(identity.get("reason", ""))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--verify-live-identity", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        result = build_preflight(args.account_id, verify_live_identity=args.verify_live_identity)
    except ValueError as exc:
        result = {"status": "BLOCKED", "reason": str(exc), "would_post": False, "secret_values_exposed": False}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    return 0 if result["status"] in {"PASS", "CREDENTIAL_PENDING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
