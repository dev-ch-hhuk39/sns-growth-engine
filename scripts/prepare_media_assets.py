#!/usr/bin/env python3
"""
prepare_media_assets.py — メディアアセット準備 CLI（Phase 2.12）

reference_posts の画像・動画URLから media_assets を生成・保存する。

安全ガード:
  --dry-run  (デフォルト ON): Sheetsへの書き込みをスキップ
  --upload  + ALLOW_CLOUDINARY_UPLOAD=true: Cloudinaryへの実アップロードを有効化

使い方:
  # JSONフィクスチャ → dry-run
  python scripts/prepare_media_assets.py \\
    --account-id night_scout \\
    --input-json fixtures/sample_x_posts.json \\
    --dry-run

  # Sheetsから読んで dry-run
  python scripts/prepare_media_assets.py \\
    --account-id night_scout \\
    --use-sheets \\
    --dry-run

  # Sheetsへ書き込み（Cloudinaryアップロードなし）
  python scripts/prepare_media_assets.py \\
    --account-id night_scout \\
    --use-sheets \\
    --test-write \\
    --no-dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_cloudinary_config, get_config_partial
from media.cloudinary_client import extract_media_urls, prepare_media_assets
from sheets_client import MockSheetsClient, SheetsClient, make_client


def main() -> None:
    parser = argparse.ArgumentParser(description="media_assets 準備 CLI")
    parser.add_argument("--account-id", required=True, help="v2 アカウントID")
    parser.add_argument("--input-json", help="入力JSONファイルパス（reference_posts 形式）")
    parser.add_argument("--use-sheets", action="store_true", help="実SheetsClientを使用")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Sheetsへの書き込みをスキップ（デフォルトON）")
    parser.add_argument("--no-dry-run", action="store_true", help="Sheetsへの書き込みを有効化")
    parser.add_argument("--test-write", action="store_true", help="実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる）")
    parser.add_argument("--upload", action="store_true", help="Cloudinaryアップロードを有効化（ALLOW_CLOUDINARY_UPLOAD=true 必要）")
    parser.add_argument("--limit", type=int, help="処理件数上限")
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    cloudinary_cfg = get_cloudinary_config()
    allow_upload = args.upload and cloudinary_cfg.get("allow_upload", False)

    if args.upload and not cloudinary_cfg.get("allow_upload", False):
        print("[WARN] --upload が指定されましたが ALLOW_CLOUDINARY_UPLOAD=false のためアップロードをスキップします。")

    # --- 入力データ取得 ---
    posts: list[dict] = []

    if args.input_json:
        with open(args.input_json, encoding="utf-8") as f:
            posts = json.load(f)
        print(f"[INFO] JSONフィクスチャ読み込み: {len(posts)}件")
    elif args.use_sheets:
        cfg = get_config_partial()
        client: SheetsClient | MockSheetsClient = make_client(cfg, dry_run=False)
        posts = client.get_reference_posts(account_id=args.account_id)
        print(f"[INFO] Sheets から reference_posts 読み込み: {len(posts)}件")
    else:
        print("[ERROR] --input-json または --use-sheets を指定してください。")
        sys.exit(1)

    if args.limit:
        posts = posts[:args.limit]

    # メディアURLあり投稿のみ処理
    with_media = [p for p in posts if extract_media_urls(p)]
    print(f"[INFO] メディアあり投稿: {len(with_media)}件 / 全{len(posts)}件")

    if not with_media:
        print("[INFO] メディアURLのある投稿が見つかりませんでした。終了します。")
        return

    # --- メディアアセット生成 ---
    assets = prepare_media_assets(
        posts=with_media,
        account_id=args.account_id,
        config=cloudinary_cfg if allow_upload else {},
        dry_run=dry_run or not allow_upload,
    )
    print(f"[INFO] 生成したメディアアセット: {len(assets)}件")

    for a in assets:
        print(
            f"  ref={a.get('reference_post_id', '?')!r} "
            f"url={str(a.get('original_media_url', ''))[:60]!r} "
            f"type={a.get('media_type')} risk={a.get('media_reuse_risk')} "
            f"storage={a.get('storage_provider')}"
        )

    # --- Sheets保存 ---
    if args.test_write and not dry_run:
        cfg = get_config_partial()
        write_client = make_client(cfg, dry_run=False)
        result = write_client.save_media_assets(assets)
        print(f"[INFO] save_media_assets: saved={result['saved']} skipped={result['skipped']} errors={result['errors']}")
    elif dry_run:
        print(f"[dry-run] {len(assets)}件の保存をスキップしました（--no-dry-run で有効化）。")
    else:
        print(f"[INFO] 書き込みをスキップしました（--test-write を指定すると保存されます）。")


if __name__ == "__main__":
    main()
