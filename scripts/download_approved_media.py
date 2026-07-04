#!/usr/bin/env python3
"""Plan/download approved individual video URLs only."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision



def is_individual_video_url(url: str) -> bool:
    parts = urlsplit(str(url or ""))
    host = parts.netloc.lower()
    path = parts.path
    if "tiktok.com" in host:
        return "/video/" in path
    if "youtube.com" in host:
        return path == "/watch" and bool(parts.query)
    if "youtu.be" in host:
        return len(path.strip("/")) > 0
    return False


def build_download_plan(args: argparse.Namespace) -> dict:
    decision = build_rights_decision(args.rights_status, action="download")
    allow_env = os.environ.get("ALLOW_VIDEO_DOWNLOAD", "").lower() == "true"
    blocked = []
    if not decision.allowed:
        blocked.append(decision.reason)
    if not is_individual_video_url(args.source_url):
        blocked.append("individual_video_url_required")
    if args.download and not args.confirm_download:
        blocked.append("--download requires --confirm-download")
    if args.download and not allow_env:
        blocked.append("ALLOW_VIDEO_DOWNLOAD=true is required")
    return {
        "status": "READY" if args.download and not blocked else "BLOCKED" if blocked else "PLAN_ONLY",
        "source_url": args.source_url,
        "rights_status": decision.rights_status,
        "rights_decision": decision.as_dict(),
        "adapter_status": {"yt_dlp": "installed" if importlib.util.find_spec("yt_dlp") else "not_installed"},
        "output_dir": str(ROOT / "output" / "downloads"),
        "download": bool(args.download),
        "confirm_download": bool(args.confirm_download),
        "allow_video_download": allow_env,
        "would_download": bool(args.download and not blocked),
        "blocked_reasons": blocked,
        "download_result": {
            "media_asset_id": "",
            "local_path": "",
            "status": "NOT_DOWNLOADED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="download approved media")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    args = parser.parse_args()
    plan = build_download_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" and args.download else 0


if __name__ == "__main__":
    raise SystemExit(main())
