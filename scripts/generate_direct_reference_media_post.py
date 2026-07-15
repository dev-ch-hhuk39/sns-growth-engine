#!/usr/bin/env python3
"""Generate new public text for a linked direct asset; never output source copy."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from public_post_quality import final_public_post_validator, generate_reader_facing_post, public_preview
def main() -> int:
    parser = argparse.ArgumentParser(description="generate a validator-safe direct-media caption")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"]); parser.add_argument("--source-post-id", required=True); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(); text = generate_reader_facing_post(args.account_id, (sum(map(ord, args.source_post_id)) % 20) + 1)
    check = final_public_post_validator(text, args.account_id)
    print(json.dumps({"status": "PLAN_ONLY" if check["status"] == "PASS" else "BLOCKED", "source_post_id": args.source_post_id, "public_post_preview": public_preview(text), "public_post_validator": check["status"], "source_post_text_exposed": False}, ensure_ascii=False, indent=2))
    return 0 if check["status"] == "PASS" else 1
if __name__ == "__main__": raise SystemExit(main())
