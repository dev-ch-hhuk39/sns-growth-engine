#!/usr/bin/env python3
"""参考素材から Threads 投稿案を生成する標準 CLI（薄い入口）。

内部では既存スクリプトを再利用する:
  - --source references : generate_from_references.py（参考投稿から生成）
  - --source clips      : generate_from_video_clips.py（切り抜き候補から生成）

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-generate。
  - 投稿先は threads のみ（X は将来対応のみ・本 CLI からは生成しない）。
  - 生成投稿案は DRAFT / WAITING_REVIEW で止める。worker の ELIGIBLE_STATUSES に入れない。
    → 自動投稿されない。
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

CLI_NAME = "generate_threads_ideas_from_references"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads"}
# worker が拾うステータス。生成物はここに入れない。
ELIGIBLE_STATUSES = {"WAITING_REVIEW", "PLANNED"}
NON_POSTABLE_STATUS = "DRAFT"

DELEGATES = {
    "references": "scripts/generate_from_references.py",
    "clips": "scripts/generate_from_video_clips.py",
}


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets/LLM 不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if args.platform not in ALLOWED_PLATFORMS:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "platform は threads のみ（X は将来対応）"}
    if args.source not in DELEGATES:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "source は references / clips のみ"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_generate)
    will_run = apply and confirm
    delegate = DELEGATES[args.source]

    if args.source == "references":
        argv = ["--account-id", args.account_id, "--platform", args.platform, "--top-n", str(args.top_n)]
        if not will_run:
            argv += ["--mock", "--dry-run"]
    else:  # clips
        argv = ["--account-id", args.account_id, "--limit", str(args.top_n)]
        if will_run:
            argv += ["--use-sheets"]
        else:
            argv += ["--mock-llm"]

    plan = {
        "status": "WILL_RUN" if will_run else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "platform": args.platform,
        "source": args.source,
        "delegate_script": delegate,
        "delegate_argv": argv,
        "safety": {
            "candidate_status": NON_POSTABLE_STATUS,
            "in_eligible_statuses": NON_POSTABLE_STATUS in ELIGIBLE_STATUSES,
            "auto_post": False,
            "platform": args.platform,
        },
        "notes": "生成案は DRAFT/WAITING_REVIEW で停止（worker 非対象）。threads のみ。実行は --apply --confirm-generate。",
    }
    # 不変条件: 生成候補ステータスは worker の投稿対象に含まれない。
    assert NON_POSTABLE_STATUS not in ELIGIBLE_STATUSES
    assert plan["safety"]["in_eligible_statuses"] is False
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="generate Threads ideas from references (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--platform", default="threads")
    parser.add_argument("--source", default="references", choices=["references", "clips"])
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="run delegate (needs --confirm-generate)")
    parser.add_argument("--confirm-generate", action="store_true")
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
