#!/usr/bin/env python3
"""Plan bounded direct-reference source-post discovery without media reuse."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from media_source_policy import decision

def main() -> int:
    parser = argparse.ArgumentParser(description="discover only explicitly direct-media-approved source posts")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--apply", action="store_true"); parser.add_argument("--confirm-discovery", action="store_true")
    args = parser.parse_args()
    data = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())
    selected, blocked = [], []
    for source in data.get("sources", []):
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if args.account_id not in targets: continue
        check = decision(source, "direct_media")
        (selected if check["allowed"] else blocked).append({"source_id": source.get("source_id", ""), "reason": check["reason"]})
    status = "BLOCKED" if args.apply and not args.confirm_discovery else "PLAN_ONLY"
    print(json.dumps({"status": status, "account_id": args.account_id, "selected_sources": selected, "blocked_sources": blocked[:50], "network_fetch": False, "would_save_source_posts": False}, ensure_ascii=False, indent=2))
    return 1 if status == "BLOCKED" else 0
if __name__ == "__main__": raise SystemExit(main())
