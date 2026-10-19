#!/usr/bin/env python3
"""Fail fast when the quality-v2 rollout explicitly requires owner review.

This is a read-only local configuration check. It makes no provider calls,
does not touch Sheets, never marks a queue READY, and cannot publish.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "content_quality_v2.json"
AUTONOMOUS_POLICY = ROOT / "config" / "autonomous_mode.json"
TEXT_ACCOUNTS = {"night_scout", "liver_manager", "beauty_account"}


def evaluate_policy(data: Any) -> tuple[str, int]:
    if not isinstance(data, dict) or data.get("schema_version") != "content_quality_v2":
        return "CONTENT_QUALITY_V2_POLICY_UNVERIFIED", 2
    flag = data.get("draft_only")
    if type(flag) is not bool:
        return "CONTENT_QUALITY_V2_POLICY_UNVERIFIED", 2
    if flag:
        return "OWNER_REVIEW_REQUIRED", 2
    return "QUALITY_ROLLOUT_PREFLIGHT_PASS", 0


def autonomous_text_policy_status(
    account_id: str, *,
    quality_policy_path: Path = DEFAULT_POLICY,
    autonomous_policy_path: Path = AUTONOMOUS_POLICY,
) -> tuple[str, int]:
    """Allow only legacy text generation/strict AUTO_READY, never V2 media or posting.

    Content Quality V2 draft-only candidates must remain non-promotable. Both
    policies are checked before any Sheets or provider interaction.
    """
    try:
        if not all(p.is_file() and p.stat().st_size <= 100_000
                   for p in (quality_policy_path, autonomous_policy_path)):
            return "AUTONOMOUS_TEXT_POLICY_UNVERIFIED", 2
        quality = json.loads(quality_policy_path.read_text(encoding="utf-8"))
        mode = json.loads(autonomous_policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return "AUTONOMOUS_TEXT_POLICY_UNVERIFIED", 2
    if not isinstance(quality, dict) or not isinstance(mode, dict):
        return "AUTONOMOUS_TEXT_POLICY_UNVERIFIED", 2
    if (quality.get("schema_version") != "content_quality_v2"
            or quality.get("draft_only") is not True
            or quality.get("publishing_enabled") is not False):
        return "QUALITY_V2_EDITORIAL_ISOLATION_NOT_PROVEN", 2
    if account_id not in TEXT_ACCOUNTS:
        return "AUTONOMOUS_TEXT_ACCOUNT_NOT_ALLOWED", 2
    accounts = mode.get("allowed_accounts")
    if (not isinstance(accounts, list) or not all(type(value) is str for value in accounts)
            or not set(accounts) <= TEXT_ACCOUNTS or account_id not in accounts):
        return "AUTONOMOUS_TEXT_ACCOUNT_NOT_ALLOWED", 2
    for flag in ("autonomous_mode_enabled", "auto_idea_generation_enabled",
                 "auto_ready_enabled", "scheduled_prepare_enabled", "media_operations_delegated"):
        if mode.get(flag) is not True:
            return "AUTONOMOUS_TEXT_POLICY_DISABLED", 2
    for flag in ("kill_switch", "allow_unknown_rights", "allow_third_party_media",
                 "allow_media_posts"):
        if mode.get(flag) is not False:
            return "AUTONOMOUS_TEXT_SAFETY_BOUNDARY_NOT_PROVEN", 2
    blocked_platforms = mode.get("blocked_platforms_for_post")
    if (mode.get("allowed_platforms_for_post") != ["threads"]
            or not isinstance(blocked_platforms, list)
            or "x" not in blocked_platforms):
        return "AUTONOMOUS_TEXT_PLATFORM_BOUNDARY_NOT_PROVEN", 2
    bounds = (("min_quality_score", 85, "min"), ("min_safety_score", 90, "min"),
              ("max_risk_score", 10, "max"), ("max_similarity_to_source", 0.45, "max"))
    for key, limit, kind in bounds:
        value = mode.get(key)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or (kind == "min" and value < limit)
                or (kind == "max" and value > limit)):
            return "AUTONOMOUS_TEXT_QUALITY_BOUNDARY_NOT_PROVEN", 2
    return "AUTONOMOUS_TEXT_ONLY_PREFLIGHT_PASS", 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--autonomous-text-only", action="store_true")
    parser.add_argument("--account-id", default="")
    args = parser.parse_args(argv)
    if args.autonomous_text_only:
        status, rc = autonomous_text_policy_status(
            args.account_id, quality_policy_path=args.policy,
        )
        if rc:
            print("[BLOCKED] " + status)
            print("REAL_POST_ALLOWED=false; QUEUE_READY_WRITES=0; PROVIDER_CALLS=0")
        else:
            print(status + "; Content Quality V2 remains draft-only; this never authorizes posting")
        return rc
    try:
        if args.policy.stat().st_size > 100_000:
            raise ValueError("oversized_policy")
        data = json.loads(args.policy.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        print("[BLOCKED] CONTENT_QUALITY_V2_POLICY_UNVERIFIED")
        return 2
    code, rc = evaluate_policy(data)
    if rc:
        print("[BLOCKED] " + code)
        print("REAL_POST_ALLOWED=false; QUEUE_READY_WRITES=0; PROVIDER_CALLS=0")
    else:
        print("QUALITY_ROLLOUT_PREFLIGHT_PASS; this does not authorize publishing")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
