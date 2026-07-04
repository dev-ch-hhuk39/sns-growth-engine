#!/usr/bin/env python3
"""Validate media + public text before any Threads video post."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from public_post_quality import final_public_post_validator

APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def validate_media_post(plan: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    rights = str(plan.get("rights_status", "")).lower()
    account_id = str(plan.get("account_id", ""))
    platform = str(plan.get("platform", "")).lower()
    text = plan.get("public_post_text", "")
    text_result = final_public_post_validator(text, account_id)
    duration = float(plan.get("duration_seconds") or 0)
    aspect = str(plan.get("aspect_ratio", ""))
    if rights not in APPROVED_RIGHTS:
        reasons.append("rights_status_not_approved")
    if plan.get("permission_status") != "approved":
        reasons.append("permission_status_not_approved")
    if not plan.get("media_url"):
        reasons.append("media_url_missing")
    if not plan.get("media_asset_id"):
        reasons.append("media_asset_id_missing")
    if platform != "threads":
        reasons.append("platform_not_threads")
    if account_id != "liver_manager":
        reasons.append("account_not_liver_manager")
    if account_id == "beauty_account" or platform == "x":
        reasons.append("x_or_beauty_blocked")
    if str(plan.get("media_type", "video")).lower() != "video":
        reasons.append("media_type_not_video")
    if not (8 <= duration <= 45):
        reasons.append("duration_out_of_range")
    if aspect != "9:16":
        reasons.append("aspect_ratio_not_9_16")
    if text_result["status"] != "PASS":
        reasons.append("public_post_validator_blocked")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "text_validation": text_result["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="validate media post plan")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    plan = json.loads(args.json) if args.json else {}
    result = validate_media_post(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
