#!/usr/bin/env python3
"""参考素材から Threads 投稿案を生成する標準 CLI（薄い入口）。

内部では既存スクリプトを再利用する:
  - --source references : generate_from_references.py（参考投稿から生成）
  - --source clips      : generate_from_video_clips.py（切り抜き候補から生成）

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-generate。
  - 投稿先は threads のみ（X は将来対応のみ・本 CLI からは生成しない）。
  - 本 CLI は「生成」だけを行う。委譲先（generate_from_references.py /
    generate_from_video_clips.py）は候補を作るだけで投稿 worker を呼ばない。
  - 生成候補は WAITING_REVIEW で書き込まれる。これは worker の ELIGIBLE_STATUSES
    に含まれる（worker が拾える）ため、自動投稿されない保証は次の多層で担保する:
      1. 本 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。
      2. 実投稿には別経路 worker の三重ゲート（--confirm-real-post かつ
         PUBLISH_ENABLED=true かつ ALLOW_REAL_THREADS_POST=true）が必要。
         これら 3 つは現状すべて禁止のため実投稿は不可能。
      3. beauty_account / X は本 CLI で BLOCKED。
  - 残存アーキ懸念: Threads worker は WAITING_REVIEW を eligible 扱いし、X の
    publish_queue.py のような「項目ごとの人間 READY 昇格ゲート」を持たない。
    人間ゲートは approve_queue.py（WAITING_REVIEW → READY/REJECTED）に依存する。
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
# worker が拾うステータス（process_threads_queue.py の ELIGIBLE_STATUSES と一致）。
ELIGIBLE_STATUSES = {"WAITING_REVIEW", "PLANNED"}
# 委譲先が実際に書き込む候補ステータス（両委譲先とも WAITING_REVIEW 固定）。
CANDIDATE_STATUS = "WAITING_REVIEW"
# 実投稿に必要なゲート（現状すべて禁止 → 実投稿は不可能）。
REAL_POST_GATES = ["--confirm-real-post", "PUBLISH_ENABLED=true", "ALLOW_REAL_THREADS_POST=true"]
# 人間レビューゲート（WAITING_REVIEW → READY/REJECTED）。
HUMAN_GATE = "approve_queue.py"

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
            # 委譲先は WAITING_REVIEW で書く。これは worker eligible だが、
            # 本 CLI も委譲先も投稿処理を呼ばないため自動投稿はされない。
            "candidate_status": CANDIDATE_STATUS,
            "worker_selectable": CANDIDATE_STATUS in ELIGIBLE_STATUSES,
            # 本 CLI / 委譲先は生成専用で投稿経路を一切持たない（最重要不変条件）。
            "delegate_posts": False,
            # 実投稿は別 worker の三重ゲートが必要。現状すべて禁止 → 不可能。
            "real_post_requires": REAL_POST_GATES,
            "real_post_possible_now": False,
            "human_gate": f"{HUMAN_GATE} (WAITING_REVIEW → READY/REJECTED)",
            "platform": args.platform,
        },
        "notes": (
            "本 CLI は生成専用（投稿しない）。候補は WAITING_REVIEW で書かれ worker eligible だが、"
            "実投稿には別 worker の三重ゲート（全禁止）が必要なため自動投稿されない。"
            "threads のみ。実行は --apply --confirm-generate。"
        ),
    }
    # 最重要不変条件: 本 CLI は投稿せず生成のみ（委譲先も投稿経路を持たない）。
    assert plan["safety"]["delegate_posts"] is False
    assert plan["safety"]["real_post_possible_now"] is False
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
