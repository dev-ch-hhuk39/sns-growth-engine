#!/usr/bin/env python3
"""Generate review-only media post queue rows from approved media assets."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

APPROVED_STATUSES = {"APPROVED", "UPLOADED", "ATTACHED"}


def build_queue_row(asset: dict[str, Any]) -> dict[str, Any] | None:
    status = str(asset.get("status", "")).upper()
    rights = str(asset.get("rights_status", "")).lower()
    if status not in APPROVED_STATUSES or rights not in {"owned", "licensed", "approved_creator_clip", "not_required"}:
        return None
    account_id = asset.get("account_id", "night_scout")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return {
        "queue_id": f"media_q_{account_id}_{stamp}",
        "draft_id": f"media_draft_{account_id}_{stamp}",
        "account_id": account_id,
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_asset_id": asset.get("media_asset_id", ""),
        "media_strategy": "approved_media",
        "auto_publish": "false",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="generate media post queue rows")
    parser.add_argument("--account-id", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-generate", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    sample_asset = {"media_asset_id": "sample_asset", "account_id": "night_scout", "status": "WAITING_REVIEW", "rights_status": "third_party_reference_only"}
    rows = [r for r in [build_queue_row(sample_asset)] if r]
    plan = {
        "status": "PLAN_ONLY" if not args.apply else "WILL_APPLY",
        "media_ratio_policy": {"text_only": 0.7, "media": 0.3},
        "candidate_count": len(rows),
        "candidate_status": "WAITING_REVIEW",
        "auto_ready": False,
        "rows": rows,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_generate or not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-generate --use-sheets"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "NO_APPROVED_MEDIA", "candidate_count": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
