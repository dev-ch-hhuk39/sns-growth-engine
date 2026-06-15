#!/usr/bin/env python3
"""update_source_status.py — ソースの candidate_status / fetch_enabled / active を変更する

使い方:
  python3 scripts/update_source_status.py \
    --source-file config/source_accounts/my_sources.json \
    --source-id src_ns_x_cand_001 \
    --status active \
    [--fetch-enabled] \
    [--dry-run]  # デフォルト ON

安全制約:
  - beauty_account のソースを active / READY 化することはこのスクリプトでは行わない
  - fetch_enabled=True にするには --allow-fetch を明示指定が必要
  - active=True にするには --allow-active を明示指定が必要
  - dry_run=True がデフォルト
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_VALID_STATUSES = {"candidate", "disabled", "active", "rejected", "waiting_review"}


def _load_sources(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_sources(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="ソースステータスを更新する (dry_run=True がデフォルト)")
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--status", choices=sorted(_VALID_STATUSES), help="新しい candidate_status")
    parser.add_argument("--fetch-enabled", action="store_true", default=False, help="fetch_enabled を True に (要: --allow-fetch)")
    parser.add_argument("--allow-fetch", action="store_true", default=False,
                        help="fetch_enabled 変更を明示許可するフラグ")
    parser.add_argument("--allow-active", action="store_true", default=False,
                        help="active=True 変更を明示許可するフラグ")
    parser.add_argument("--set-active", action="store_true", default=False)
    parser.add_argument("--review-notes", default="", help="review_notes を更新する")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    if not os.path.isfile(args.source_file):
        print(f"[ERROR] ファイルが見つかりません: {args.source_file}")
        return 1

    data = _load_sources(args.source_file)
    sources = data.get("sources", [])

    target = None
    for s in sources:
        if s.get("source_id") == args.source_id:
            target = s
            break

    if target is None:
        print(f"[ERROR] source_id='{args.source_id}' が見つかりません")
        return 1

    # beauty_account の active 化を防ぐ
    if args.set_active and "beauty_account" in target.get("target_account_ids", []):
        print(f"[BLOCKED] beauty_account のソースは active 化禁止です")
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    changes: dict = {}

    if args.status:
        changes["candidate_status"] = args.status

    if args.fetch_enabled:
        if not args.allow_fetch:
            print("[BLOCKED] fetch_enabled=True には --allow-fetch フラグが必要です")
            return 1
        changes["fetch_enabled"] = True

    if args.set_active:
        if not args.allow_active:
            print("[BLOCKED] active=True には --allow-active フラグが必要です")
            return 1
        changes["active"] = True

    if args.review_notes:
        changes["review_notes"] = args.review_notes

    if not changes:
        print("[WARN] 変更なし — --status / --fetch-enabled / --set-active / --review-notes を指定してください")
        return 0

    changes["updated_at"] = now

    mode = "DRY_RUN" if dry_run else "WRITE"
    print(f"[{mode}] source_id={args.source_id} への変更:")
    for k, v in changes.items():
        old = target.get(k)
        print(f"  {k}: {old!r} → {v!r}")

    if dry_run:
        print(f"\n[DRY_RUN] 実ファイルは変更されませんでした。--no-dry-run で実行してください。")
        return 0

    target.update(changes)
    _save_sources(args.source_file, data)
    print(f"\n[WRITE] {args.source_file} を更新しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
