#!/usr/bin/env python3
"""Cut only owned/licensed/approved clips with ffmpeg gates."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision


def build_plan(args: argparse.Namespace) -> dict:
    allowed_env = os.environ.get("ALLOW_VIDEO_CUT", "").lower() == "true"
    decision = build_rights_decision(args.rights_status, action="cut")
    ffmpeg_cli = shutil.which("ffmpeg") is not None
    ffmpeg_python = importlib.util.find_spec("ffmpeg") is not None
    start_seconds = float(getattr(args, "start_seconds", 0) or 0)
    end_seconds = float(getattr(args, "end_seconds", 0) or 0)
    blocked = []
    if not decision.allowed:
        blocked.append(decision.reason)
    if args.cut and not args.confirm_cut:
        blocked.append("--cut requires --confirm-cut")
    if args.cut and not allowed_env:
        blocked.append("ALLOW_VIDEO_CUT=true is required")
    if args.cut and not args.input_path:
        blocked.append("input_path is required")
    if args.cut and end_seconds <= start_seconds:
        blocked.append("end_seconds must be greater than start_seconds")
    if args.cut and not ffmpeg_cli:
        blocked.append("ffmpeg CLI is not installed")
    output_path = str(ROOT / "output" / "clips" / f"clip_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.mp4")
    return {
        "status": "READY" if args.cut and not blocked else "BLOCKED" if blocked else "PLAN_ONLY",
        "adapter_status": {
            "ffmpeg_cli": "installed" if ffmpeg_cli else "not_installed",
            "ffmpeg_python": "installed" if ffmpeg_python else "not_installed",
        },
        "rights_status": decision.rights_status,
        "rights_decision": decision.as_dict(),
        "input_path": args.input_path,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": max(0, end_seconds - start_seconds),
        "output_path": output_path,
        "ffmpeg_cut": bool(args.cut and not blocked),
        "would_cut": bool(args.cut and not blocked),
        "blocked_reasons": blocked,
        "vertical_9x16": args.vertical,
        "burn_subtitles": args.burn_subtitles,
        "media_asset_result": {
            "media_asset_id": "",
            "local_path": output_path,
            "media_type": "video",
            "rights_status": decision.rights_status,
            "status": "WAITING_REVIEW",
            "upload_status": "NOT_UPLOADED",
        } if decision.allowed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="cut approved clips")
    parser.add_argument("--input-path", default="")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--confirm-cut", action="store_true")
    parser.add_argument("--start-seconds", type=float, default=0)
    parser.add_argument("--end-seconds", type=float, default=0)
    parser.add_argument("--vertical", action="store_true")
    parser.add_argument("--burn-subtitles", action="store_true")
    args = parser.parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] != "READY":
        return 0
    # Real ffmpeg execution intentionally left to the gated production runner.
    print(json.dumps({"status": "NOT_EXECUTED", "reason": "ffmpeg execution runner not invoked in this dry pipeline"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
