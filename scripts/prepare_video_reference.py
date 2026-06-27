#!/usr/bin/env python3
"""動画を参考素材として準備する標準 CLI（薄い入口）。

内部では既存の plan_video_reference_posts.py を再利用する（動画メタ + 切り抜き候補プラン）。
動画ファイルの download は既定で行わない（メタ情報・参考分析の準備のみ）。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-prepare。
  - 動画 download は既定 false。--allow-download かつ --confirm-download の両方がない限り download しない。
    （本 CLI 既定では download フラグを委譲先に渡さない＝参考分析・メタ準備に留める）
  - 第三者動画は参考分析・メタ情報まで。Cloudinary upload はしない。
  - beauty_account は対象外。X は将来対応のみ（投稿先は threads）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLI_NAME = "prepare_video_reference"
DELEGATE_SCRIPT = "scripts/plan_video_reference_posts.py"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads"}  # X は将来対応のみ


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets/ネットワーク不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if args.platform not in ALLOWED_PLATFORMS:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "platform は threads のみ（X は将来対応）"}
    if not args.video_url and not args.source_id:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "--video-url か --source-id のいずれかが必要"}

    # download は二重ゲート。両方そろわない限り絶対に download させない。
    download_allowed = bool(args.allow_download) and bool(args.confirm_download)

    apply = bool(args.apply)
    confirm = bool(args.confirm_prepare)
    will_run = apply and confirm

    argv = ["--account-id", args.account_id, "--platform", args.platform,
            "--source-platform", args.source_platform]
    if args.video_url:
        argv += ["--video-url", args.video_url]
    if args.source_id:
        argv += ["--source-id", args.source_id]
    if not will_run:
        # 委譲先のドライラン/モックでプランのみ確認。
        argv += ["--mock", "--dry-run"]

    plan = {
        "status": "WILL_RUN" if will_run else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "delegate_script": DELEGATE_SCRIPT,
        "delegate_argv": argv,
        "safety": {
            "media_download": download_allowed,  # 既定 false
            "cloudinary_upload": False,
            "ffmpeg_cut": False,
            "auto_post": False,
        },
        "notes": "動画メタ + 切り抜き候補プランのみ。download は --allow-download --confirm-download が必要。実行は --apply --confirm-prepare。",
    }
    # 不変条件: download は両ゲートが揃わない限り常に false。
    assert plan["safety"]["media_download"] == download_allowed
    if not will_run:
        assert "--dry-run" in argv
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prepare a video reference (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--platform", default="threads")
    parser.add_argument("--source-platform", default="youtube")
    parser.add_argument("--video-url")
    parser.add_argument("--source-id")
    parser.add_argument("--apply", action="store_true", help="run delegate (needs --confirm-prepare)")
    parser.add_argument("--confirm-prepare", action="store_true")
    parser.add_argument("--allow-download", action="store_true",
                        help="allow media download (also needs --confirm-download)")
    parser.add_argument("--confirm-download", action="store_true")
    return parser.parse_args()


def main() -> int:
    plan = build_plan(_parse_args())
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] != "WILL_RUN":
        return 0
    cmd = [sys.executable, str(ROOT / plan["delegate_script"]), *plan["delegate_argv"]]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
