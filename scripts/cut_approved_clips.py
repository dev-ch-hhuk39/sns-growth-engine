#!/usr/bin/env python3
"""Cut only owned/licensed/approved clips with ffmpeg gates."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUTTABLE_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def build_plan(args: argparse.Namespace) -> dict:
    allowed_env = os.environ.get("ALLOW_VIDEO_CUT", "").lower() == "true"
    rights_ok = args.rights_status in CUTTABLE_RIGHTS
    blocked = []
    if not rights_ok:
        blocked.append("rights_status must be owned/licensed/approved_creator_clip")
    if args.cut and not args.confirm_cut:
        blocked.append("--cut requires --confirm-cut")
    if args.cut and not allowed_env:
        blocked.append("ALLOW_VIDEO_CUT=true is required")
    return {
        "status": "READY" if args.cut and not blocked else "BLOCKED" if blocked else "PLAN_ONLY",
        "rights_status": args.rights_status,
        "input_path": args.input_path,
        "output_path": str(ROOT / "output" / "clips" / f"clip_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.mp4"),
        "ffmpeg_cut": bool(args.cut and not blocked),
        "blocked_reasons": blocked,
        "vertical_9x16": args.vertical,
        "burn_subtitles": args.burn_subtitles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="cut approved clips")
    parser.add_argument("--input-path", default="")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--confirm-cut", action="store_true")
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
