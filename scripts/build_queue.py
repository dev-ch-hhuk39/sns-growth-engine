"""
build_queue.py - queue 構築 CLI

使い方:
  python scripts/build_queue.py --account-id night_scout --platforms x,threads --dry-run
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from config_loader import get_config
from sheets_client import make_client
from queue_builder import build_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 queue 構築")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platforms", default="x,threads")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
    if dry_run:
        print("[INFO] DRY-RUN モードで実行します")

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    try:
        cfg = get_config()
    except ValueError as e:
        if dry_run:
            print(f"[INFO] 設定未完了のため MockSheetsClient を使用します: {e}")
            cfg = {"sheet_id": "", "sa_dict": None, "dry_run": True,
                   "gemini_api_key": "", "discord_webhook_url": ""}
        else:
            print(f"[ERROR] 設定エラー: {e}")
            sys.exit(1)

    sheets = make_client(cfg, dry_run=dry_run)

    results = build_queue(
        sheets=sheets,
        account_id=args.account_id,
        platforms=platforms,
        dry_run=dry_run,
    )
    print(f"\n[DONE] queue 追加件数: {len(results)}")


if __name__ == "__main__":
    main()
