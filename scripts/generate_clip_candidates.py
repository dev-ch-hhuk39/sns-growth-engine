#!/usr/bin/env python3
"""切り抜き候補を生成する標準 CLI（薄い入口）。

内部では既存の analyze_video_clips.py を再利用する（文字起こしから切り抜き候補を抽出）。
ffmpeg による実切り抜きはしない（候補化のみ）。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-generate。
  - ffmpeg 実切り抜きはしない。--cut が指定されても BLOCKED（cut_video_clips.py の領域・本 CLI では拒否）。
  - 生成物は切り抜き「候補」。自動投稿対象にはしない。
  - beauty_account は対象外。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLI_NAME = "generate_clip_candidates"
DELEGATE_SCRIPT = "scripts/analyze_video_clips.py"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets 不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if getattr(args, "cut", False):
        return {"status": "BLOCKED", "cli": CLI_NAME,
                "reason": "ffmpeg 実切り抜きは本 CLI では行わない（候補化のみ）"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_generate)
    will_write = apply and confirm

    argv = ["--account-id", args.account_id, "--limit", str(args.limit),
            "--n-candidates", str(args.n_candidates), "--transcript-status", args.transcript_status]
    if will_write:
        argv += ["--use-sheets"]

    plan = {
        "status": "WILL_WRITE" if will_write else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "delegate_script": DELEGATE_SCRIPT,
        "delegate_argv": argv,
        "safety": {
            "ffmpeg_cut": False,
            "media_download": False,
            "auto_post": False,
        },
        "notes": "切り抜き候補化のみ。ffmpeg 実切り抜きなし。本番書き込みは --apply --confirm-generate。",
    }
    assert ("--use-sheets" in argv) == will_write
    assert "--cut" not in argv and "--confirm-cut" not in argv
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="generate clip candidates (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--n-candidates", type=int, default=6)
    parser.add_argument("--transcript-status", default="done")
    parser.add_argument("--apply", action="store_true", help="write candidates to Sheets (needs --confirm-generate)")
    parser.add_argument("--confirm-generate", action="store_true")
    parser.add_argument("--cut", action="store_true",
                        help="(blocked) ffmpeg cut は本 CLI では行わない")
    return parser.parse_args()


def main() -> int:
    plan = build_plan(_parse_args())
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] != "WILL_WRITE":
        return 0
    cmd = [sys.executable, str(ROOT / plan["delegate_script"]), *plan["delegate_argv"]]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
