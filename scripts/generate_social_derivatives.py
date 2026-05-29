"""
generate_social_derivatives.py - 派生投稿生成 CLI

使い方:
  python scripts/generate_social_derivatives.py --account-id night_scout --platforms x,threads --limit 5 --dry-run --mock-llm
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
from social_derivative_generator import generate_social_derivatives


def main() -> None:
    parser = argparse.ArgumentParser(description="v2 派生投稿生成")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platforms", default="x,threads", help="対象プラットフォーム（カンマ区切り）")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-llm", action="store_true")
    args = parser.parse_args()

    if args.mock_llm:
        os.environ["MOCK_LLM"] = "true"

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

    results = generate_social_derivatives(
        sheets=sheets,
        account_id=args.account_id,
        platforms=platforms,
        limit=args.limit,
        dry_run=dry_run,
    )
    print(f"\n[DONE] 生成件数: {len(results)}")


if __name__ == "__main__":
    main()
