#!/usr/bin/env python3
"""Gate direct media download/Cloudinary ingestion behind explicit evidence."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))

def _true(v: str | None) -> bool: return str(v or "").lower() in {"1", "true", "yes"}
def main() -> int:
    parser = argparse.ArgumentParser(description="ingest a direct source-post asset only with dedicated gates")
    parser.add_argument("--source-post-id", required=True); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--apply", action="store_true"); parser.add_argument("--confirm-ingest", action="store_true")
    args = parser.parse_args()
    gates = _true(os.getenv("ALLOW_VIDEO_DOWNLOAD")) and _true(os.getenv("ALLOW_CLOUDINARY_UPLOAD"))
    status = "PLAN_ONLY" if not args.apply else "BLOCKED"
    reason = "apply requires --confirm-ingest, explicit direct_media_reuse evidence, ALLOW_VIDEO_DOWNLOAD=true, and ALLOW_CLOUDINARY_UPLOAD=true"
    if args.apply and not args.confirm_ingest: reason = "--apply requires --confirm-ingest"
    print(json.dumps({"status": status, "source_post_id": args.source_post_id, "would_download": False, "would_upload": False, "gates_present": gates, "blocked_reason": reason if status == "BLOCKED" else ""}, ensure_ascii=False, indent=2))
    return 1 if status == "BLOCKED" else 0
if __name__ == "__main__": raise SystemExit(main())
