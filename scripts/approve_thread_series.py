"""
approve_thread_series.py - thread_series 承認 CLI（Phase 6.2）

レビュー済みスレッドシリーズを承認する。
safety_policy.requires_human_review_before_post を満たした上で、
--confirm-approve フラグが必須。

禁止事項:
  - draft_only アカウントの承認は WAITING_REVIEW のみ（READY化禁止）
  - 実SNS投稿（このスクリプトでは行わない）
  - beauty_account の queue.status = READY への変更

使い方:
  python scripts/approve_thread_series.py --series-id ts_xxxxx --confirm-approve
  python scripts/approve_thread_series.py --series-json series.json --confirm-approve
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

JST = timezone(timedelta(hours=9))


def main() -> None:
    parser = argparse.ArgumentParser(description="thread_series 承認 CLI")
    parser.add_argument("--series-id", default="", help="シリーズID")
    parser.add_argument("--series-json", default="", help="承認対象JSONファイルパス")
    parser.add_argument(
        "--confirm-approve",
        action="store_true",
        required=True,
        help="承認の明示的な確認フラグ（必須）",
    )
    args = parser.parse_args()

    if not args.confirm_approve:
        print("[ERROR] --confirm-approve フラグが必要です。")
        print("  このフラグは人間によるレビュー完了を明示するものです。")
        sys.exit(1)

    print(f"\n=== approve_thread_series ===")

    if not args.series_json:
        print("[ERROR] --series-json でJSONファイルを指定してください。")
        print("  例: python scripts/approve_thread_series.py --series-json path/to/series.json --confirm-approve")
        sys.exit(1)

    if not os.path.isfile(args.series_json):
        print(f"[ERROR] JSONファイルが見つかりません: {args.series_json}")
        sys.exit(1)

    with open(args.series_json, encoding="utf-8") as f:
        series_data = json.load(f)

    account_id = series_data.get("account_id", "")
    series_id = series_data.get("series_id", args.series_id)

    print(f"  series_id  : {series_id}")
    print(f"  account_id : {account_id}")
    print(f"  platform   : {series_data.get('platform', '')}")
    print(f"  post_count : {len(series_data.get('posts', []))}")

    # draft_only チェック（承認後も WAITING_REVIEW のまま）
    is_draft_only = False
    try:
        from accounts.account_config import load_account_config
        cfg = load_account_config(account_id)
        is_draft_only = cfg.is_draft_only()
    except FileNotFoundError:
        pass

    if is_draft_only:
        print(f"\n  [BLOCKED] {account_id} は draft_only アカウントです。")
        print("  承認操作は受け付けますが、ステータスは WAITING_REVIEW のままです。")
        print("  READY化・実投稿は禁止です。")
        approved_status = "WAITING_REVIEW"
    else:
        approved_status = "APPROVED"

    # 承認処理（ローカルJSONの更新のみ。実Sheets書き込みは行わない）
    now = datetime.now(JST).isoformat()
    series_data["status"] = approved_status
    series_data["approved_at"] = now
    series_data["approved_by"] = "human"

    for p in series_data.get("posts", []):
        if p.get("status") == "WAITING_REVIEW":
            p["status"] = approved_status

    # 承認済みJSONを保存
    output_path = args.series_json.replace(".json", "_approved.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(series_data, f, ensure_ascii=False, indent=2)

    print(f"\n  [OK] 承認処理完了")
    print(f"  status     : {approved_status}")
    print(f"  saved      : {output_path}")

    if is_draft_only:
        print(f"\n  [NOTE] draft_only アカウントのため実投稿は禁止です。")
        print("  承認済みデータはレビュー記録として保管してください。")


if __name__ == "__main__":
    main()
