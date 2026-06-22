#!/usr/bin/env python3
"""publish_x_post.py — X (Twitter) 投稿 CLI (dry_run=True がデフォルト)

使い方:
  python3 scripts/publish_x_post.py \
    --account-id night_scout \
    --text "投稿テキスト" \
    [--dry-run]  # デフォルト ON

実投稿するには:
  PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
  python3 scripts/publish_x_post.py \
    --account-id night_scout \
    --text "投稿テキスト" \
    --no-dry-run

安全制約:
  - dry_run=True がデフォルト（実投稿しない）
  - 実投稿には PUBLISH_ENABLED=true と ALLOW_REAL_X_POST=true の両方が必要
  - beauty_account への投稿は常に blocked
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

_BEAUTY_BLOCKED = frozenset(["beauty_account"])


def main() -> int:
    parser = argparse.ArgumentParser(description="X 投稿 CLI (dry_run=True がデフォルト)")
    parser.add_argument("--account-id", required=True, help="投稿先アカウント ID")
    parser.add_argument("--text", default="Phase13 dry-run publisher safety check", help="投稿テキスト (280文字以内)")
    parser.add_argument("--image-url", default="", help="画像 URL (オプション)")
    parser.add_argument("--mock", action="store_true", help="mock publisher plan")
    parser.add_argument("--confirm-post", action="store_true", help="実投稿確認フラグ")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_true", help="dry_run を無効化 (実投稿)")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    # beauty_account は常に BLOCKED
    if args.account_id in _BEAUTY_BLOCKED:
        print(f"[BLOCKED] {args.account_id} への X 投稿は禁止されています")
        return 1

    if not dry_run and not args.confirm_post:
        print("[BLOCKED] --no-dry-run には --confirm-post が必要です")
        print("  実投稿は実行していません")
        return 1

    # X は 280文字制限
    if len(args.text) > 280:
        print(f"[ERROR] テキストが 280文字を超えています ({len(args.text)} 文字)")
        return 1

    try:
        from src.publishers.x_publisher import XPublisher
    except Exception as e:
        print(f"[ERROR] XPublisher import 失敗: {e}")
        return 1

    publisher = XPublisher()

    mode = "DRY_RUN" if dry_run else "REAL_POST"
    print(f"[{mode}] X 投稿:")
    print(f"  account_id: {args.account_id}")
    print(f"  mock: {args.mock} confirm_post: {args.confirm_post}")
    print(f"  text ({len(args.text)} chars): {args.text[:80]}{'...' if len(args.text) > 80 else ''}")
    if args.image_url:
        print(f"  image_url: {args.image_url}")

    result = publisher.publish(
        args.text,
        account={"account_id": args.account_id},
        derivative={"derivative_id": "cli_direct"},
        queue_item={"queue_id": "cli_direct"},
        dry_run=dry_run,
    )

    success = result.success
    message = result.message or ""
    status = "DRY_RUN" if result.is_dry_run_ok else ("OK" if success else "FAIL")
    print(f"\n  → status: {status}")
    if message:
        print(f"  → message: {message}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
