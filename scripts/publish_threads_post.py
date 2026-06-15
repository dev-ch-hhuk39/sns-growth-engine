#!/usr/bin/env python3
"""publish_threads_post.py — Threads 投稿 CLI (dry_run=True がデフォルト)

使い方:
  python3 scripts/publish_threads_post.py \
    --account-id night_scout \
    --text "投稿テキスト" \
    [--dry-run]  # デフォルト ON

実投稿するには:
  PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true \
  python3 scripts/publish_threads_post.py \
    --account-id night_scout \
    --text "投稿テキスト" \
    --no-dry-run

安全制約:
  - dry_run=True がデフォルト（実投稿しない）
  - 実投稿には PUBLISH_ENABLED=true と ALLOW_REAL_THREADS_POST=true の両方が必要
  - beauty_account への投稿は常に blocked
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_BEAUTY_BLOCKED = frozenset(["beauty_account"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Threads 投稿 CLI (dry_run=True がデフォルト)")
    parser.add_argument("--account-id", required=True, help="投稿先アカウント ID")
    parser.add_argument("--text", required=True, help="投稿テキスト")
    parser.add_argument("--image-url", default="", help="画像 URL (オプション)")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_true", help="dry_run を無効化 (実投稿)")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    # beauty_account は常に BLOCKED
    if args.account_id in _BEAUTY_BLOCKED:
        print(f"[BLOCKED] {args.account_id} への Threads 投稿は禁止されています")
        return 1

    try:
        from src.publishers.threads_publisher import ThreadsPublisher
    except Exception as e:
        print(f"[ERROR] ThreadsPublisher import 失敗: {e}")
        return 1

    publisher = ThreadsPublisher()

    mode = "DRY_RUN" if dry_run else "REAL_POST"
    print(f"[{mode}] Threads 投稿:")
    print(f"  account_id: {args.account_id}")
    print(f"  text: {args.text[:80]}{'...' if len(args.text) > 80 else ''}")
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
