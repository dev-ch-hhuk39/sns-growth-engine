#!/usr/bin/env python3
"""参考 URL を source registry に登録する標準 CLI（薄い入口）。

内部では既存の add_source_candidate.py を再利用する。
URL を登録するだけで、download / scraping は一切しない。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はドライラン（PLAN_ONLY）。本番登録は --apply かつ --confirm-import。
  - rights_status は unknown 既定 → WAITING_REVIEW 必須（許諾未確認は流用不可）。
  - 媒体 download なし（登録のみ）。
  - beauty_account 向けは対象外。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLI_NAME = "import_reference_urls"
DELEGATE_SCRIPT = "scripts/add_source_candidate.py"
ALLOWED_TARGETS = {"night_scout", "liver_manager"}


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets 不要・テスト対象）。"""
    if args.target_account == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account 向けは対象外（draft_only）"}
    if not args.url:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "--url は必須"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_import)
    will_write = apply and confirm

    argv = ["--source-file", args.source_file, "--source-id", args.source_id,
            "--platform", args.platform, "--url", args.url,
            "--target-account", args.target_account,
            "--collection-method", args.collection_method]
    if args.handle:
        argv += ["--handle", args.handle]
    if args.name:
        argv += ["--name", args.name]
    if args.category:
        argv += ["--category", args.category]
    if will_write:
        # add_source_candidate は --dry-run 既定 True。実登録は --no-dry-run。
        argv += ["--no-dry-run"]

    plan = {
        "status": "WILL_WRITE" if will_write else "PLAN_ONLY",
        "cli": CLI_NAME,
        "target_account": args.target_account,
        "delegate_script": DELEGATE_SCRIPT,
        "delegate_argv": argv,
        "safety": {
            "media_download": False,
            "rights_status_default": "unknown",
            "requires_human_review": True,
            "auto_post": False,
        },
        "notes": "URL 登録のみ。download/scraping なし。許諾未確認は WAITING_REVIEW。本番登録は --apply --confirm-import。",
    }
    assert ("--no-dry-run" in argv) == will_write
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="import reference URLs into source registry (thin wrapper, gated)")
    parser.add_argument("--source-file", default="config/source_accounts/default_sources.json")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--handle")
    parser.add_argument("--target-account", required=True,
                        choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--collection-method", default="manual_url")
    parser.add_argument("--name")
    parser.add_argument("--category")
    parser.add_argument("--apply", action="store_true", help="register for real (needs --confirm-import)")
    parser.add_argument("--confirm-import", action="store_true")
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
