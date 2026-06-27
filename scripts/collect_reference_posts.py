#!/usr/bin/env python3
"""参考投稿を収集する標準 CLI（薄い入口）。

内部では既存の collect_source_account_posts.py を再利用する。
外部からは統一 CLI 名「collect_reference_posts」で運用する。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はドライラン（PLAN_ONLY）。本番 Sheets 書き込みは --apply かつ --confirm-collect。
  - 収集対象は参考メタ情報のみ（use_status=REFERENCE_ONLY）。第三者メディアは download しない。
  - beauty_account は対象外。
  - 実 X API 呼び出しはしない（X は将来対応のみ。本 CLI からは実 API を起動しない）。
  - secret 値は出力しない。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLI_NAME = "collect_reference_posts"
DELEGATE_SCRIPT = "scripts/collect_source_account_posts.py"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
# 参考分析として収集してよい source platform（投稿先ではなく収集元）。
ALLOWED_SOURCE_PLATFORMS = {"x", "threads", "tiktok", "youtube_shorts"}
DEFAULT_USE_STATUS = "REFERENCE_ONLY"


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets 不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if args.source_platform not in ALLOWED_SOURCE_PLATFORMS:
        return {"status": "BLOCKED", "cli": CLI_NAME,
                "reason": f"source-platform は {sorted(ALLOWED_SOURCE_PLATFORMS)} のみ"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_collect)
    will_write = apply and confirm

    argv = ["--account-id", args.account_id, "--source-platform", args.source_platform,
            "--top-n", str(args.top_n)]
    if args.source_handle:
        argv += ["--source-handle", args.source_handle]
    if args.input_json:
        argv += ["--input-json", args.input_json]
    if will_write:
        # collect_source_account_posts は --use-sheets で実書き込み（既定 --dry-run True）。
        argv += ["--use-sheets"]

    plan = {
        "status": "WILL_WRITE" if will_write else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "delegate_script": DELEGATE_SCRIPT,
        "delegate_argv": argv,
        "safety": {
            "use_status": DEFAULT_USE_STATUS,
            "media_download": False,
            "real_x_api": False,
            "auto_post": False,
        },
        "notes": "参考メタ情報のみ収集。媒体 download なし。本番書き込みは --apply --confirm-collect。",
    }
    # 不変条件: 実書き込みフラグは will_write のときだけ付く。
    assert ("--use-sheets" in argv) == will_write
    assert "--use-x-api" not in argv  # 実 X API は起動しない
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="collect reference posts (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--source-platform", default="threads")
    parser.add_argument("--source-handle")
    parser.add_argument("--input-json")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--apply", action="store_true", help="write to Sheets (needs --confirm-collect)")
    parser.add_argument("--confirm-collect", action="store_true")
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
