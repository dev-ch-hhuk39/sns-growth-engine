#!/usr/bin/env python3
"""Plan media/no-media ratio without approving third-party media."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

TARGET_TEXT_ONLY_RATIO = 0.70
TARGET_MEDIA_RATIO = 0.30


def is_media_candidate(row: dict[str, Any]) -> bool:
    if str(row.get("status", "")).upper() == "READY":
        return False
    if str(row.get("media_asset_id", "")).strip() or str(row.get("video_clip_id", "")).strip():
        reuse = str(row.get("media_reuse_risk", "")).lower()
        rights = str(row.get("rights_status", "")).lower()
        return reuse in {"low", ""} and rights in {"allowed", "not_required", ""}
    return False


def build_media_mix_plan(queue_rows: list[dict[str, Any]], account_id: str = "all") -> dict[str, Any]:
    rows = [
        r for r in queue_rows
        if (account_id == "all" or r.get("account_id") == account_id)
        and str(r.get("platform", "")).lower() == "threads"
        and str(r.get("status", "")).upper() in {"WAITING_REVIEW", "READY", "DRAFT"}
    ]
    media = [r for r in rows if is_media_candidate(r)]
    text = [r for r in rows if not is_media_candidate(r)]
    total = max(1, len(rows))
    return {
        "status": "PLAN_ONLY",
        "account_id": account_id,
        "total_candidates": len(rows),
        "text_only_count": len(text),
        "media_candidate_count": len(media),
        "current_text_only_ratio": round(len(text) / total, 2),
        "current_media_ratio": round(len(media) / total, 2),
        "target_text_only_ratio": TARGET_TEXT_ONLY_RATIO,
        "target_media_ratio": TARGET_MEDIA_RATIO,
        "auto_ready_policy": "text_only_only_initially",
        "media_policy": "third_party_media_never_reused; only self_generated/approved_company_asset/approved_creator_clip after gate",
        "media_queue_ids": [r.get("queue_id", "") for r in media],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="plan media/no-media mix")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account is outside media mix autopilot"}, ensure_ascii=False))
        return 1
    if args.use_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        rows = [dict(r) for r in client._ws("queue").get_all_records()]
    else:
        rows = []
    print(json.dumps(build_media_mix_plan(rows, args.account_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
