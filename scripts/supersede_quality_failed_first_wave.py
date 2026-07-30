#!/usr/bin/env python3
"""Exclude the explicitly reviewed first-wave rows without deleting history."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from process_threads_queue import records, update_row

TARGETS = (
    "text_canary_fresh_20260729094318_night_scout_original_text",
    "q_fresh_night_scout_30440723109_direct_image",
    "text_canary_fresh_20260729094318_liver_manager_original_text",
    "q_fresh_liver_manager_30440723109_direct_image",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-supersede", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_supersede:
        print(json.dumps({"status": "BLOCKED", "reason": "--confirm-supersede required", "would_post": False})); return 1
    from config_loader import get_config
    from sheets_client import SheetsClient, TAB_DEFINITIONS
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    existing = {str(row.get("queue_id", "")): row for row in records(client, "queue")}
    found = [item for item in TARGETS if item in existing]
    missing = [item for item in TARGETS if item not in existing]
    if args.apply:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        for queue_id in found:
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "SUPERSEDED_QUALITY",
                "blocked_reason": "superseded_by_batch_diversity_and_topic_coherence_gate",
                "excluded_from_activation": True,
                "excluded_from_metrics_baseline": True,
                "repost_prohibited": True,
                "superseded_reason": "batch_diversity_or_topic_coherence_failure",
                "updated_at": now,
            })
        after = {str(row.get("queue_id", "")): row for row in records(client, "queue")}
        failed = [
            item for item in found
            if str(after.get(item, {}).get("status", "")).upper() != "SUPERSEDED_QUALITY"
            or str(after.get(item, {}).get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
            or str(after.get(item, {}).get("excluded_from_metrics_baseline", "")).lower() not in {"true", "1", "yes"}
            or str(after.get(item, {}).get("repost_prohibited", "")).lower() not in {"true", "1", "yes"}
            or str(after.get(item, {}).get("superseded_reason", "")) != "batch_diversity_or_topic_coherence_failure"
        ]
        result = {"status": "APPLIED" if not failed else "PARTIAL_FAILURE", "superseded_queue_ids": found, "missing_queue_ids": missing, "read_after_write": "PASS" if not failed else "FAIL", "would_post": False}
    else:
        result = {"status": "PLAN_ONLY", "superseded_queue_ids": found, "missing_queue_ids": missing, "would_post": False}
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
