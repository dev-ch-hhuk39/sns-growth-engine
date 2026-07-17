#!/usr/bin/env python3
"""Build bounded trend signals from already acquired source posts.

It intentionally has no network backend and never generates a publishable
caption.  Optional research tools remain analysis-only shadows configured in
``source_backend_routing.json``.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient

STOP = {"こと", "ため", "これ", "それ", "する", "いる", "です", "ます", "から", "よう", "ない", "投稿"}


def topics(rows: list[dict[str, Any]], account_id: str, limit: int) -> list[tuple[str, int]]:
    words: collections.Counter[str] = collections.Counter()
    for row in rows:
        if account_id != "all" and str(row.get("target_account_id", "")) != account_id:
            continue
        text = str(row.get("original_post_text", ""))
        for token in re.findall(r"[\wぁ-んァ-ン一-龠]{2,}", text):
            if token not in STOP:
                words[token] += 1
    return words.most_common(max(1, min(limit, 20)))


def main() -> int:
    parser = argparse.ArgumentParser(description="derive local analysis-only trend signals")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-trends", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_trends:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-trends"})); return 1
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "collection_backend": "local_trend_aggregator", "network_fetch": False,
                          "publishing": False, "would_read_source_posts": True, "would_write_trend_signals": True}, ensure_ascii=False)); return 0
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    source_ws = client._ensure_tab("source_posts", TAB_DEFINITIONS["source_posts"])
    rows = client._call_with_rate_limit_retry("get_all_records:source_posts:trends", lambda: source_ws.get_all_records())
    values = topics([dict(row) for row in rows], args.account_id, args.limit)
    trend_ws = client._ensure_tab("trend_signals", TAB_DEFINITIONS["trend_signals"])
    headers = client._call_with_rate_limit_retry("headers:trend_signals", lambda: trend_ws.row_values(1))
    now = datetime.now(timezone.utc).isoformat()
    for index, (topic, count) in enumerate(values):
        row = {"trend_signal_id": f"local_{args.account_id}_{int(datetime.now().timestamp())}_{index}", "account_id": args.account_id,
               "platform": "multi", "topic": topic, "signal_summary": "local source-post frequency signal; human-reviewed planning input only",
               "source_count": str(count), "window_days": "30", "collection_backend": "local_trend_aggregator", "status": "ANALYSIS_ONLY",
               "created_at": now, "updated_at": now}
        client._call_with_rate_limit_retry("append:trend_signals", lambda row=row: trend_ws.append_row([row.get(key, "") for key in headers], value_input_option="USER_ENTERED"))
    print(json.dumps({"status": "APPLIED", "collection_backend": "local_trend_aggregator", "signal_count": len(values),
                      "network_fetch": False, "publishing": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
