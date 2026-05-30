"""
collect_references.py — X 参考投稿収集 CLI

使い方:
  # JSON入力（dry-run・Sheetsへ書かない）
  python scripts/collect_references.py --account-id night_scout --platform x \
      --input-json fixtures/sample_x_posts.json --dry-run

  # JSON入力 → MockSheetsClient に保存（実Sheets不使用）
  python scripts/collect_references.py --account-id night_scout --platform x \
      --input-json fixtures/sample_x_posts.json --mock --dry-run

  # JSON入力 → 実Sheets test-write（1件だけ試し書き）
  python scripts/collect_references.py --account-id night_scout --platform x \
      --input-json fixtures/sample_x_posts.json --use-sheets --test-write

  # X API収集（--use-x-api が必要。現在は NotImplementedError）
  python scripts/collect_references.py --account-id night_scout --platform x \
      --use-x-api --dry-run

重要:
  - デフォルトは dry-run（Sheetsに書かない）
  - --use-sheets がない限り実Sheetsへ書かない
  - --test-write がない限り実Sheetsに書かない
  - --use-x-api がない限りX APIを呼ばない
  - SNS投稿は絶対にしない
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from collectors.x_reference_collector import (
    normalize_posts,
    load_json_input,
    classify_media,
    make_dedup_key,
    bearer_token_from_env,
    fetch_account_posts,
)
from sheets_client import make_client, MockSheetsClient


def build_mock_posts(account_id: str, count: int = 3) -> list[dict]:
    """モックデータを生成する。"""
    import uuid
    return [
        {
            "post_id": f"mock-{i+1:04d}",
            "post_url": f"https://x.com/mock_user/status/mock-{i+1:04d}",
            "account_handle": "mock_user",
            "account_name": "モックユーザー",
            "posted_at": "2026-05-30T12:00:00+09:00",
            "text": f"モック投稿 {i+1}: テスト用ダミーテキストです。{i+1}番目の投稿。",
            "image_urls": ["https://example.com/img.jpg"] if i == 1 else [],
            "video_urls": ["https://example.com/vid.mp4"] if i == 2 else [],
            "like_count": (i + 1) * 100,
            "reply_count": (i + 1) * 5,
            "repost_count": (i + 1) * 20,
            "bookmark_count": (i + 1) * 30,
            "impression_count": (i + 1) * 5000,
            "source_type": "account_monitor",
            "matched_keywords": [],
        }
        for i in range(count)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="X 参考投稿収集 CLI")
    parser.add_argument("--account-id", required=True, help="収集対象アカウントID")
    parser.add_argument("--platform", default="x", choices=["x", "threads"], help="収集元プラットフォーム")
    parser.add_argument("--input-json", help="入力JSONファイルパス")
    parser.add_argument("--mock", action="store_true", help="モックデータで収集（ファイル不要）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Sheetsへ書き込まない（デフォルトON）")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="dry-runを無効化")
    parser.add_argument("--use-sheets", action="store_true", help="実SheetsClient を使用")
    parser.add_argument("--test-write", action="store_true", help="実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる）")
    parser.add_argument("--use-x-api", action="store_true", help="X APIを使って収集（現在は未実装）")
    args = parser.parse_args()

    print("=" * 60)
    print("  collect_references.py - 参考投稿収集")
    print("=" * 60)
    print(f"  account_id : {args.account_id}")
    print(f"  platform   : {args.platform}")
    print(f"  mode       : {'mock' if args.mock else ('x-api' if args.use_x_api else 'json')}")
    print(f"  dry_run    : {args.dry_run}")
    print(f"  use_sheets : {args.use_sheets}")
    print(f"  test_write : {args.test_write}")
    print("=" * 60)

    # X API モードは現在未実装
    if args.use_x_api:
        print("\n[WARN] --use-x-api は Phase 2.10 で実装予定のため、現在は実行できません。")
        print("  JSONファイル入力 (--input-json) またはモック (--mock) を使用してください。")
        sys.exit(1)

    # 書き込み先の決定
    if args.use_sheets and args.test_write:
        if args.dry_run:
            print("[WARN] --dry-run と --test-write の両方が指定されています。dry-runを優先します。")
            write_mode = "dry-run"
        else:
            write_mode = "real"
    elif args.use_sheets:
        write_mode = "dry-run"  # --use-sheetsのみは読み取りのみ
        print("[INFO] --test-write がないため、Sheetsへは書き込みません（確認のみ）")
    else:
        write_mode = "dry-run"

    # 1. 入力データ収集
    print("\n[Step 1] 投稿データ収集")
    raw_posts: list[dict] = []

    if args.mock:
        raw_posts = build_mock_posts(args.account_id, count=3)
        print(f"  モックデータ生成: {len(raw_posts)}件")

    elif args.input_json:
        path = args.input_json
        if not os.path.isabs(path):
            path = os.path.join(_V2_ROOT, path)
        if not os.path.exists(path):
            print(f"[ERROR] ファイルが見つかりません: {path}")
            sys.exit(1)
        raw_posts = load_json_input(path)
        print(f"  JSON読み込み: {len(raw_posts)}件 ({path})")

    else:
        # デフォルト: data/x_posts.json または環境変数
        json_path = os.environ.get("X_POSTS_JSON", os.path.join(_V2_ROOT, "data", "x_posts.json"))
        if os.path.exists(json_path):
            raw_posts = load_json_input(json_path)
            print(f"  JSON読み込み: {len(raw_posts)}件 ({json_path})")
        else:
            print("[ERROR] 入力ソースを指定してください: --input-json / --mock / 環境変数 X_POSTS_JSON")
            sys.exit(1)

    # 2. 正規化
    print("\n[Step 2] 正規化")
    normalized = normalize_posts(raw_posts, account_id=args.account_id, platform=args.platform)
    print(f"  正規化完了: {len(normalized)}件")

    # 詳細表示
    for i, post in enumerate(normalized):
        media = classify_media(raw_posts[i] if i < len(raw_posts) else {})
        media_str = " [画像]" if media["has_image"] else (" [動画]" if media["has_video"] else "")
        print(f"  [{i+1}] post_id={post.get('post_id', '?')} likes={post.get('likes', 0)} "
              f"views={post.get('impressions', 0)}{media_str}")

    # 3. 重複キー確認
    print("\n[Step 3] 重複チェック")
    dedup_keys = [make_dedup_key(p) for p in normalized]
    unique_keys = set(dedup_keys)
    print(f"  収集件数: {len(normalized)}件 / ユニーク: {len(unique_keys)}件")

    # 4. Sheets クライアント準備
    print("\n[Step 4] Sheets クライアント準備")
    if args.use_sheets and write_mode == "real":
        try:
            from config_loader import get_config
            cfg = get_config()
            sheets = make_client(cfg, dry_run=False)
            print("  実SheetsClient を使用します")
        except Exception as e:
            print(f"[ERROR] SheetsClient 初期化失敗: {e}")
            sys.exit(1)
    else:
        sheets = MockSheetsClient(dry_run=(write_mode == "dry-run"))
        client_type = "MockSheetsClient (dry-run)" if write_mode == "dry-run" else "MockSheetsClient"
        print(f"  {client_type} を使用します")

    # 5. 保存
    print("\n[Step 5] 保存")
    if write_mode == "dry-run":
        print(f"  [dry-run] {len(normalized)}件を保存予定（実際には書き込みません）")
        for post in normalized:
            print(f"    → reference_posts: post_id={post.get('post_id', '?')!r} "
                  f"likes={post.get('likes', 0)}")
    else:
        result = sheets.save_reference_posts(normalized)
        print(f"  保存結果: 追加={result['added']}件 / スキップ={result['skipped']}件 / エラー={result['errors']}件")

    # 6. ログ記録
    if write_mode != "dry-run" and hasattr(sheets, "log"):
        try:
            sheets.log(
                account_id=args.account_id,
                operation="collect_references",
                status="OK",
                message=f"収集={len(raw_posts)}件 正規化={len(normalized)}件",
            )
            print("\n  logsにcollect_references記録を追加しました")
        except Exception as e:
            print(f"[WARN] log記録失敗: {e}")

    print("\n" + "=" * 60)
    print(f"完了: 収集={len(raw_posts)}件 / 正規化={len(normalized)}件 / 保存予定={len(normalized)}件")
    if write_mode == "dry-run":
        print("  (dry-run: Sheetsへの書き込みはスキップされました)")
    print("=" * 60)
    print("\n[安全確認] SNS投稿は発生していません。")


if __name__ == "__main__":
    main()
