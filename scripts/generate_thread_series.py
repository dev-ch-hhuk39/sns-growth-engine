"""
generate_thread_series.py - thread_series 生成 CLI（Phase 6.2）

アカウント・プラットフォーム・テーマを指定してスレッドシリーズを生成する。
デフォルトは完全dry-run（mock LLM）。実投稿は行わない。

使い方:
  # dry-run（モック生成）
  python scripts/generate_thread_series.py --account-id night_scout --platform x --theme "夜職で稼ぐ方法"

  # 投稿数指定
  python scripts/generate_thread_series.py --account-id beauty_account --platform threads --post-count 5

  # Sheetsに書き込み（test-write）
  python scripts/generate_thread_series.py --account-id night_scout --use-sheets --test-write

  # mock LLM 明示
  python scripts/generate_thread_series.py --account-id liver_manager --mock-llm

禁止事項:
  - 実SNS投稿（ALLOW_REAL_X_POST / ALLOW_REAL_THREADS_POST は常に false）
  - beauty_account の READY 化・POSTED 化
  - posted_results の変更
  - queue.status を POSTED に変更
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

from generation.thread_series_generator import ThreadSeriesGenerator


class MockSheetsClient:
    """テスト用モックSheetsクライアント。"""

    def __init__(self) -> None:
        self._saved: list[dict] = []

    def append_thread_series(self, series: dict) -> None:
        self._saved.append(series)
        print(f"  [MockSheets] thread_series 保存: {series.get('series_id')}")

    def get_saved(self) -> list[dict]:
        return self._saved


def main() -> None:
    parser = argparse.ArgumentParser(description="thread_series 生成 CLI")
    parser.add_argument("--account-id", default="night_scout", help="アカウントID")
    parser.add_argument("--platform", default="x", choices=["x", "threads"], help="プラットフォーム")
    parser.add_argument("--theme", default="", help="シリーズテーマ")
    parser.add_argument("--post-count", type=int, default=4, help="投稿数（1-8）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="dry-run（デフォルトON）")
    parser.add_argument("--use-sheets", action="store_true", help="Sheets接続を有効化")
    parser.add_argument("--test-write", action="store_true", help="Sheetsへtest-writeを実行")
    parser.add_argument("--mock-llm", action="store_true", default=True, help="mock LLM（デフォルトON）")
    parser.add_argument("--output-json", action="store_true", help="JSON出力")
    args = parser.parse_args()

    account_id = args.account_id
    platform = args.platform
    theme = args.theme or f"{account_id} のテーマ（サンプル）"
    post_count = max(1, min(8, args.post_count))

    print(f"\n=== generate_thread_series: {account_id} / {platform} ===")
    print(f"  theme      : {theme}")
    print(f"  post_count : {post_count}")
    print(f"  mock_llm   : {args.mock_llm}")
    print(f"  use_sheets : {args.use_sheets}")
    print(f"  test_write : {args.test_write}")

    # draft_only チェック
    try:
        from accounts.account_config import load_account_config
        cfg = load_account_config(account_id)
        if cfg.is_draft_only():
            print(f"\n  [INFO] {account_id} は draft_only アカウントです。")
            print("  生成は可能ですが、全投稿は WAITING_REVIEW 状態で出力します。")
            print("  READY化・実投稿は禁止です。")
    except FileNotFoundError:
        print(f"  [WARN] {account_id} の account_config が見つかりません（seeds.py のみ使用）")

    generator = ThreadSeriesGenerator()
    series = generator.generate(
        account_id=account_id,
        platform=platform,
        theme=theme,
        post_count=post_count,
        mock_llm=args.mock_llm,
    )

    print(f"\n--- 生成結果 ---")
    print(f"  series_id    : {series.series_id}")
    print(f"  series_theme : {series.series_theme}")
    print(f"  status       : {series.status}")
    print(f"  generation   : {series.generation_mode}")
    print(f"  post_count   : {series.post_count}")
    print(f"  risk_level   : {series.risk_level}")
    if series.generation_notes:
        print(f"  notes        : {series.generation_notes}")
    print()
    for p in series.posts:
        print(f"  [{p.post_index}] ({p.post_role}) [{p.status}] {len(p.text)}文字")
        preview = p.text.replace("\n", " / ")[:60]
        print(f"      {preview}{'...' if len(p.text) > 60 else ''}")

    # Sheets test-write
    if args.test_write:
        print(f"\n--- Sheets test-write ---")
        if args.use_sheets:
            print("  [INFO] 実Sheets書き込みモード（test-write）")
            try:
                from sheets_client import SheetsClient, make_client
                sheets = make_client(dry_run=False)
                _do_sheets_write(sheets, series)
            except Exception as e:
                print(f"  [WARN] Sheets接続エラー（MockSheetsClientで代替）: {e}")
                mock_sheets = MockSheetsClient()
                mock_sheets.append_thread_series(series.to_dict())
        else:
            print("  [INFO] MockSheetsClient モード")
            mock_sheets = MockSheetsClient()
            mock_sheets.append_thread_series(series.to_dict())

    if args.output_json:
        print(f"\n--- JSON出力 ---")
        print(json.dumps(series.to_dict(), ensure_ascii=False, indent=2))

    print(f"\n[DONE] generate_thread_series 完了")


def _do_sheets_write(sheets, series) -> None:
    """Sheets への実際の書き込み（test-write）。"""
    try:
        sheets.append_thread_series(series.to_dict())
        print(f"  [OK] Sheets書き込み成功: {series.series_id}")
    except AttributeError:
        print("  [WARN] SheetsClient に append_thread_series メソッドがありません。")
        print("  スキップします（setup_sheets.py で thread_series タブを追加してください）。")
    except Exception as e:
        print(f"  [WARN] Sheets書き込みエラー: {e}")


if __name__ == "__main__":
    main()
