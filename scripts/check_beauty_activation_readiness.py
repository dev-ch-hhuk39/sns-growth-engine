#!/usr/bin/env python3
"""Read-only beauty-account readiness check.

This command never activates, approves, or publishes the beauty account.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generation.beauty_review_pipeline import build_beauty_review_batch  # noqa: E402


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def build_readiness(*, mock: bool = False) -> dict:
    account = _load("config/accounts/beauty_account.json")
    manifest = _load("config/source_accounts/owner_reference_sources_20260817.json")
    source_count = sum(len(urls) for urls in manifest["accounts"]["beauty_account"].values())
    batch = build_beauty_review_batch()
    credentials = account["threads_credentials"]
    handle_secret_name = credentials.get("handle_secret_name", "THREADS_HANDLE_BEAUTY_ACCOUNT")
    handle_present = bool(credentials.get("handle") or os.getenv(handle_secret_name))
    user_id_present = bool(credentials.get("user_id") or os.getenv(credentials["user_id_secret_name"]))
    oauth_present = bool(os.getenv(credentials["access_token_secret_name"]))
    credentials_ready = handle_present and user_id_present and oauth_present and not mock

    checks = {
        "beauty_account_configured": account["account_id"] == "beauty_account",
        "draft_only": account["status"] == "draft_only",
        "allow_real_post_false": account["safety_policy"]["allow_real_post"] is False,
        "human_review_required": account["safety_policy"]["requires_human_review_before_post"] is True,
        "declared_reference_sources_22": source_count == 22,
        "five_routes_configured": batch["candidate_count"] == 5,
        "five_routes_validator_pass": batch["all_public_validators_pass"],
        "all_waiting_review": batch["all_candidates_waiting_review"],
        "pdca_account_isolated": account["learning_policy"]["strict_account_isolation"] is True,
        "daily_schedule_one_to_two": account["posting_schedule"]["daily_target_min"] == 1 and account["posting_schedule"]["daily_target_max"] == 2,
        "scheduled_publish_disabled": account["posting_schedule"]["scheduled_publish_enabled"] is False,
        "handle_present": handle_present,
        "threads_user_id_present": user_id_present,
        "oauth_credential_present": oauth_present,
    }
    credential_keys = {"handle_present", "threads_user_id_present", "oauth_credential_present"}
    code_ready = all(value for key, value in checks.items() if key not in credential_keys)
    return {
        "account_id": "beauty_account",
        "status": "READY_FOR_CANARY" if code_ready and credentials_ready else "NOT_READY",
        "code_ready": code_ready,
        "credentials_ready": credentials_ready,
        "checks": checks,
        "missing_owner_inputs": [
            label
            for label, present in (
                ("Threads handle", handle_present),
                ("Threads user ID", user_id_present),
                ("OAuth credential", oauth_present),
            )
            if not present
        ],
        "safety": {"active_changed": False, "ready_rows_created": False, "real_post_executed": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", default="beauty_account")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    if args.account_id != "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "unsupported_account"}, ensure_ascii=False))
        return 1
    result = build_readiness(mock=args.mock)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nbeauty_account 活性化チェックリスト")
    print("- コード・22参照元・persona・human review契約")
    print("- Threads handle")
    print("- Threads user ID")
    print("- OAuth credential")
    print("- canaryの人間確認")
    print("\nこのCLIはactive化・READY化・実投稿を行いません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
