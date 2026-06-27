#!/usr/bin/env python3
"""動画文字起こしの標準 CLI（薄い入口）。

内部では既存の transcribe_videos.py を再利用する。
外部文字起こし API は ALLOW_TRANSCRIPTION_API=true かつ --allow-real-transcription のときだけ。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はモック/プランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-transcribe。
  - 実 API 文字起こしは ALLOW_TRANSCRIPTION_API=true（env）かつ --allow-real-transcription の二重ゲート。
    本 CLI は env を勝手に true にしない。揃わない限り実 API フラグを委譲先に渡さない。
  - beauty_account は対象外。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLI_NAME = "transcribe_video_reference"
DELEGATE_SCRIPT = "scripts/transcribe_videos.py"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}


def build_plan(args: argparse.Namespace, env: dict[str, str] | None = None) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets/API 不要・テスト対象）。

    env を引数で渡せるようにして、ALLOW_TRANSCRIPTION_API ゲートをテスト可能にする。
    """
    env = env if env is not None else dict(os.environ)
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}

    env_allows_api = str(env.get("ALLOW_TRANSCRIPTION_API", "false")).strip().lower() == "true"
    # 実 API は env と CLI フラグの二重ゲート。
    real_api = bool(args.allow_real_transcription) and env_allows_api

    apply = bool(args.apply)
    confirm = bool(args.confirm_transcribe)
    will_run = apply and confirm

    argv = ["--account-id", args.account_id, "--limit", str(args.limit)]
    if will_run:
        argv += ["--use-sheets", "--no-dry-run"]
        if real_api:
            argv += ["--allow-real-transcription", "--confirm-api"]
        else:
            # 実 API なし → モック文字起こしで Sheets を更新（外部送信なし）。
            argv += ["--mock-sheets"]
    else:
        argv += ["--mock-sheets", "--dry-run"]

    plan = {
        "status": "WILL_RUN" if will_run else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "delegate_script": DELEGATE_SCRIPT,
        "delegate_argv": argv,
        "safety": {
            "real_transcription_api": real_api,
            "env_allow_transcription_api": env_allows_api,
            "auto_post": False,
        },
        "notes": "既定モック。実 API は ALLOW_TRANSCRIPTION_API=true + --allow-real-transcription。実行は --apply --confirm-transcribe。",
    }
    # 不変条件: 実 API フラグは二重ゲートが揃ったときだけ。
    assert ("--allow-real-transcription" in argv) == (real_api and will_run)
    if not real_api:
        assert "--allow-real-transcription" not in argv
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="transcribe video references (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true", help="run delegate (needs --confirm-transcribe)")
    parser.add_argument("--confirm-transcribe", action="store_true")
    parser.add_argument("--allow-real-transcription", action="store_true",
                        help="use external transcription API (also needs env ALLOW_TRANSCRIPTION_API=true)")
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
