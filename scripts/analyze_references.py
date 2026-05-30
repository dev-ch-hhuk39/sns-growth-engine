"""
analyze_references.py — 参考投稿分析 CLI

使い方:
  # JSONフィクスチャをそのまま分析（dry-run・Sheetsへ書かない）
  python scripts/analyze_references.py \
      --account-id night_scout \
      --input-json fixtures/sample_x_posts.json \
      --dry-run

  # Sheetsの reference_posts を読み込んで分析（dry-run）
  python scripts/analyze_references.py \
      --account-id night_scout \
      --use-sheets \
      --dry-run

  # 実Sheets → reference_post_scores に保存
  python scripts/analyze_references.py \
      --account-id night_scout \
      --use-sheets --test-write

重要:
  - デフォルトは dry-run（Sheetsに書かない）
  - --use-sheets がない限り実Sheetsへ読み書きしない
  - --test-write がない限り実Sheetsに書かない
  - SNS投稿は絶対にしない
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

from analyzers.reference_post_analyzer import analyze_reference_posts, DEFAULT_THRESHOLDS
from collectors.x_reference_collector import normalize_posts, load_json_input
from sheets_client import make_client, MockSheetsClient


def _build_mock_reference_posts(account_id: str) -> list[dict]:
    return [
        {
            "id": f"mock-id-{i+1:04d}",
            "account_id": account_id,
            "platform": "x",
            "post_id": f"mock-{i+1:04d}",
            "text": f"モック投稿 {i+1}: テスト用ダミーテキストです。",
            "extracted_hook": f"モック投稿 {i+1}",
            "likes": (i + 1) * 100,
            "reply_count": (i + 1) * 5,
            "reposts": (i + 1) * 20,
            "bookmark_count": (i + 1) * 30,
            "impressions": (i + 1) * 5000,
            "media_urls": "https://example.com/img.jpg" if i == 1 else "",
            "keywords": "",
            "status": "new",
        }
        for i in range(3)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="参考投稿分析 CLI")
    parser.add_argument("--account-id", required=True, help="分析対象アカウントID")
    parser.add_argument("--input-json", help="入力JSONファイルパス（reference_posts形式 or raw X形式）")
    parser.add_argument("--raw-json", action="store_true", help="--input-json が raw X形式（正規化が必要）")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--mock", action="store_true", help="モックデータで分析（ファイル・Sheets不要）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Sheetsへ書き込まない（デフォルトON）")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.add_argument("--use-sheets", action="store_true", help="実SheetsClient を使用")
    parser.add_argument("--test-write", action="store_true", help="実Sheetsへ書き込みを実行（--use-sheetsと組み合わせる）")
    parser.add_argument("--limit", type=int, help="分析件数の上限")
    args = parser.parse_args()

    print("=" * 60)
    print("  analyze_references.py - 参考投稿分析")
    print("=" * 60)
    print(f"  account_id : {args.account_id}")
    print(f"  dry_run    : {args.dry_run}")
    print(f"  use_sheets : {args.use_sheets}")
    print(f"  test_write : {args.test_write}")
    print("=" * 60)

    write_mode = "dry-run"
    if args.use_sheets and args.test_write and not args.dry_run:
        write_mode = "real"

    # Step 1: 入力データ収集
    print("\n[Step 1] 入力データ収集")
    posts: list[dict] = []

    if args.mock:
        posts = _build_mock_reference_posts(args.account_id)
        print(f"  モックデータ: {len(posts)}件")

    elif args.input_json:
        path = args.input_json
        if not os.path.isabs(path):
            path = os.path.join(_V2_ROOT, path)
        if not os.path.exists(path):
            print(f"[ERROR] ファイルが見つかりません: {path}")
            sys.exit(1)
        raw = load_json_input(path)
        if args.raw_json:
            posts = normalize_posts(raw, account_id=args.account_id, platform=args.platform)
            print(f"  raw JSON → 正規化: {len(raw)}件 → {len(posts)}件")
        else:
            posts = raw
            print(f"  JSON読み込み: {len(posts)}件 ({path})")

    elif args.use_sheets:
        try:
            from config_loader import get_config
            cfg = get_config()
            sheets_read = make_client(cfg, dry_run=True)
            posts = sheets_read.get_reference_posts(account_id=args.account_id)
            print(f"  Sheetsから reference_posts 取得: {len(posts)}件")
        except Exception as e:
            print(f"[ERROR] Sheets読み込み失敗: {e}")
            sys.exit(1)

    else:
        posts = _build_mock_reference_posts(args.account_id)
        print(f"  デフォルト: モックデータ {len(posts)}件（--input-json または --use-sheets を指定してください）")

    if args.limit:
        posts = posts[:args.limit]
        print(f"  --limit 適用後: {len(posts)}件")

    if not posts:
        print("[WARN] 分析対象投稿が0件です。終了します。")
        sys.exit(0)

    # Step 2: 分析
    print("\n[Step 2] パフォーマンス分析")
    results = analyze_reference_posts(
        posts,
        account_id=args.account_id,
        thresholds=DEFAULT_THRESHOLDS,
    )
    print(f"  分析完了: {len(results)}件")

    for i, r in enumerate(results):
        print(
            f"  [{i+1}] perf={r['performance_score']:.1f} buzz={r['buzz_score']:.1f} "
            f"acc%={r['account_percentile']:.2f} "
            f"hook={r['hook_style']} angle={r['content_angle']} "
            f"media={r['media_label']}"
        )
        if r.get("why_it_grew"):
            print(f"       why: {r['why_it_grew']}")
        if r.get("replay_tip"):
            print(f"       tip: {r['replay_tip']}")

    # Step 3: Sheets クライアント準備
    print("\n[Step 3] Sheets クライアント準備")
    if write_mode == "real":
        try:
            from config_loader import get_config
            cfg = get_config()
            sheets = make_client(cfg, dry_run=False)
            print("  実SheetsClient を使用します")
        except Exception as e:
            print(f"[ERROR] SheetsClient 初期化失敗: {e}")
            sys.exit(1)
    else:
        sheets = MockSheetsClient(dry_run=True)
        print("  MockSheetsClient (dry-run) を使用します")

    # Step 4: 保存
    print("\n[Step 4] reference_post_scores 保存")
    if write_mode == "dry-run":
        print(f"  [dry-run] {len(results)}件を保存予定（実際には書き込みません）")
        for r in results:
            print(
                f"    → score_id={r.get('score_id','?')[:8]}... "
                f"ref_post_id={r.get('reference_post_id','?')!r} "
                f"perf={r['performance_score']:.1f}"
            )
    else:
        save_result = sheets.save_reference_post_scores(results)
        print(
            f"  保存結果: saved={save_result['saved']}件 / "
            f"skipped={save_result['skipped']}件 / errors={save_result['errors']}件"
        )

    # Step 5: ログ記録
    if write_mode != "dry-run" and hasattr(sheets, "log"):
        try:
            sheets.log(
                account_id=args.account_id,
                operation="analyze_references",
                status="OK",
                message=f"分析={len(results)}件",
            )
            print("\n  logs に analyze_references 記録を追加しました")
        except Exception as e:
            print(f"[WARN] log記録失敗: {e}")

    print("\n" + "=" * 60)
    print(f"完了: 分析={len(results)}件")
    if write_mode == "dry-run":
        print("  (dry-run: Sheetsへの書き込みはスキップされました)")
    print("=" * 60)
    print("\n[安全確認] SNS投稿は発生していません。")


if __name__ == "__main__":
    main()
