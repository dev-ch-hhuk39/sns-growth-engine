#!/usr/bin/env python3
"""Report direct/clip MEDIA_READY inventory without modifying or fetching."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "src")]
from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient

def main() -> int:
    parser = argparse.ArgumentParser(description="check minimum media inventory by account")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--minimum", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(); cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"]); rows = client._ws("queue").get_all_records()
    accounts = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]
    inventory = {}
    for account in accounts:
        candidates = [r for r in rows if str(r.get("account_id", "")) == account and str(r.get("status", "")) in {"MEDIA_READY", "WAITING_REVIEW", "READY"}]
        inventory[account] = {"direct_media": sum(str(r.get("generation_mode", "")) == "direct_reference_media" for r in candidates), "generated_clip": sum("clip" in str(r.get("generation_mode", "")) for r in candidates)}
    deficits = {a: {k: args.minimum - v for k, v in kinds.items() if v < args.minimum} for a, kinds in inventory.items()}
    print(json.dumps({"status": "PLAN_ONLY", "minimum_per_type": args.minimum, "inventory": inventory, "deficits": deficits, "would_fetch": False, "would_download": False, "would_upload": False}, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
