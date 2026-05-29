"""
setup_sheets.py - SNS統合スプレッドシート v2 セットアップスクリプト

【使い方】
  python setup_sheets.py               # 通常実行（スプレッドシートを初期化）
  python setup_sheets.py --dry-run     # 書き込みなし確認
  DRY_RUN=true python setup_sheets.py  # 環境変数でも指定可能

【安全性】
  冪等設計：何度実行しても既存データは破壊されません。
  - タブがなければ作成（あれば触らない）
  - ヘッダーは不足列のみ右端に追加（既存列は削除・並び替えしない）
  - accounts の3行シードは account_id が存在しない場合のみ追加
"""
import argparse
import os
import sys

# スクリプト直下から src/ を参照できるようにする
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config_loader import get_config
from sheets_client import SheetsClient


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 スプレッドシートセットアップ")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="書き込みをスキップしてログだけ表示する",
    )
    args = parser.parse_args()

    try:
        cfg = get_config()
    except ValueError as e:
        print(f"[ERROR] 設定エラー: {e}")
        sys.exit(1)

    dry_run = args.dry_run or cfg["dry_run"]
    if dry_run:
        print("[INFO] DRY-RUN モードで実行します（書き込みは行いません）")

    print(f"[INFO] スプレッドシートID: {cfg['sheet_id']}")

    try:
        client = SheetsClient(
            sheet_id=cfg["sheet_id"],
            sa_dict=cfg["sa_dict"],
            dry_run=dry_run,
        )
        client.setup_all()
    except Exception as e:
        print(f"[ERROR] セットアップ失敗: {e}")
        sys.exit(1)

    print("[DONE] セットアップが完了しました")


if __name__ == "__main__":
    main()
